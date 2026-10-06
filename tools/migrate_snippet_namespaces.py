"""Offline, transactional migration of Studio snippet directories to project UUIDs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from migration_files import (atomic_write, canonical_path, digest, plain_tree,
                             remove_owned, sync_directory, sync_tree)


UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
JOURNAL = ".snippet-namespace-migration"


def mapping(catalog: list[dict]) -> dict[str, str]:
    names: dict[str, str] = {}
    identities = set()
    for project in catalog:
        identity = project["id"]
        if str(uuid.UUID(identity)) != identity or identity in identities:
            raise ValueError("Unique canonical project UUIDs are required")
        identities.add(identity)
        if not re.fullmatch(r"[a-z]{20}", project["public_ref"]):
            raise ValueError("Canonical public references are required")
        for name in [project["name"], *project["legacy_names"]]:
            if not re.fullmatch(r"[a-z_][a-z0-9_]{2,39}", name):
                raise ValueError("Invalid historical technical name")
            if name in names and names[name] != identity:
                raise ValueError("Historical name has ambiguous project ownership")
            names[name] = identity
    return names


def plan(directory: Path, catalog: list[dict]) -> dict[str, list[str]]:
    plain_tree(directory)
    if (directory / JOURNAL).exists():
        raise RuntimeError("Unfinished snippet migration requires explicit rollback")
    names = mapping(catalog)
    groups: dict[str, list[str]] = {}
    for child in directory.iterdir():
        if not child.is_dir():
            continue
        user, separator, scope = child.name.partition("__")
        if not separator or not UUID.fullmatch(user):
            raise RuntimeError("Cannot attribute snippet directory: " + child.name)
        matches = [(name, identity) for name, identity in names.items()
                   if scope == name or scope.startswith(name + "__")]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous snippet namespace: " + child.name)
        if not matches:
            stable = scope.split("__", 1)[0]
            if UUID.fullmatch(stable) and stable in {p["id"] for p in catalog}:
                continue
            raise RuntimeError("Unknown snippet namespace: " + child.name)
        name, identity = matches[0]
        target = user + "__" + identity + scope[len(name):]
        groups.setdefault(target, []).append(child.name)
    for target, sources in groups.items():
        if (directory / target).exists():
            sources.insert(0, target)
        files: dict[str, tuple] = {}
        directories = set()
        for source in sources:
            for child in (directory / source).rglob("*"):
                relative = str(child.relative_to(directory / source))
                if child.is_dir():
                    if relative in files:
                        raise RuntimeError("Conflicting snippet file and directory")
                    directories.add(relative)
                if child.is_file():
                    if relative in directories:
                        raise RuntimeError("Conflicting snippet directory and file")
                    relative = str(child.relative_to(directory / source))
                    content = (child.read_bytes(), child.stat().st_mode & 0o777)
                    if relative in files and files[relative] != content:
                        raise RuntimeError("Conflicting SQL files; originals unchanged: " + relative)
                    files[relative] = content
    return groups


def valid_namespace(name: str) -> bool:
    if not isinstance(name, str) or name in {".", ".."} or Path(name).name != name:
        return False
    user, separator, scope = name.partition("__")
    return bool(separator and UUID.fullmatch(user) and scope and "/" not in name and "\\" not in name)


def rollback(directory: Path) -> None:
    directory = canonical_path(directory)
    journal = directory / JOURNAL
    plain_tree(journal)
    manifest = journal / "manifest.json"
    if not manifest.exists():
        remove_owned(journal, directory)
        return
    data = json.loads(manifest.read_text())
    if data["directory"] != str(directory.resolve()):
        raise RuntimeError("Migration journal directory mismatch")
    for name, expected in data["backups"].items():
        if not valid_namespace(name) or digest(journal / "backup" / name) != expected:
            raise RuntimeError("Migration backup integrity failure")
    sources = {name for group in data["groups"].values() for name in group}
    if sources != set(data["backups"]):
        raise RuntimeError("Migration backup coverage mismatch")
    for target in data["groups"]:
        if not valid_namespace(target):
            raise RuntimeError("Invalid migration target")
        if (directory / target).exists():
            plain_tree(directory / target)
    for target in data["groups"]:
        if not (journal / "stage" / target).exists() and (directory / target).exists():
            remove_owned(directory / target, directory)
    for name in data["backups"]:
        target = directory / name
        if target.exists():
            remove_owned(target, directory)
        shutil.copytree(journal / "backup" / name, target)
        sync_tree(target)
    remove_owned(journal, directory)


def migrate(directory: Path, catalog: list[dict], *, apply: bool = False) -> dict[str, list[str]]:
    directory = canonical_path(directory)
    groups = plan(directory, catalog)
    if not apply or not groups:
        return groups
    journal = directory / JOURNAL
    journal.mkdir(mode=0o700)
    backups = {}
    try:
        for name in ("backup", "stage", "moved"):
            (journal / name).mkdir(mode=0o700)
        for target, sources in groups.items():
            stage = journal / "stage" / target
            for source in sources:
                shutil.copytree(directory / source, journal / "backup" / source)
                backups[source] = digest(journal / "backup" / source)
                shutil.copytree(directory / source, stage, dirs_exist_ok=True)
        sync_tree(journal)
        manifest = {"directory": str(directory.resolve()), "groups": groups, "backups": backups}
        atomic_write(journal / "manifest.json", json.dumps(manifest).encode())
        for source in backups:
            if digest(directory / source) != backups[source]:
                raise RuntimeError("Snippets changed after migration preflight")
    except BaseException:
        remove_owned(journal, directory)
        raise
    try:
        for target, sources in groups.items():
            for source in sources:
                os.replace(directory / source, journal / "moved" / source)
                sync_directory(directory)
                sync_directory(journal / "moved")
            os.replace(journal / "stage" / target, directory / target)
            sync_directory(directory)
            sync_directory(journal / "stage")
    except BaseException:
        rollback(directory)
        raise
    remove_owned(journal, directory)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snippets-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--studio-container", default="nginx")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.apply or args.rollback:
        state = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", args.studio_container],
                               check=True, capture_output=True, text=True).stdout.strip()
        if state != "false":
            raise RuntimeError("Stop the Studio gateway before snippet migration")
    if args.rollback:
        rollback(args.snippets_dir)
    else:
        if args.catalog is None:
            parser.error("--catalog is required")
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        print(json.dumps(migrate(args.snippets_dir, catalog, apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
