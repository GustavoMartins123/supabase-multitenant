"""Exact Functions credential projection. Linux lifecycle locks are mandatory."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

REF = re.compile(r"[a-z_][a-z0-9_]{2,39}\Z")
FIELDS = ("PROJECT_ID", "PROJECT_UUID", "PROJECT_PUBLIC_REF", "ANON_KEY_PROJETO", "SERVICE_ROLE_KEY_PROJETO", "JWT_SECRET_PROJETO")


def canonical_ref(ref: str) -> str:
    if not REF.fullmatch(ref):
        raise ValueError("noncanonical project ref")
    return ref


def plain_directory(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("symlink directory refused")
    path.mkdir(mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise ValueError("directory required")
    return path


def projection(root: Path, ref: str) -> dict[str, str]:
    directory = root / "projects" / canonical_ref(ref)
    if (root / "projects").is_symlink() or directory.is_symlink():
        raise ValueError("symlink project refused")
    path = directory / ".env"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("regular environment file required")
        values: dict[str, str] = {}
        for line in stream.read().splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if not match or match[1] not in FIELDS:
                continue
            key = match[1]
            value = line[len(key) + 1:]
            if key in values or not line.startswith(key + "=") or not value or value != value.strip() or any(c in value for c in "\"'\x00"):
                raise ValueError("noncanonical Functions credential")
            values[key] = value
    if set(values) != set(FIELDS) or values["PROJECT_ID"] != ref:
        raise ValueError("incomplete or divergent project identity")
    if str(uuid.UUID(values["PROJECT_UUID"])) != values["PROJECT_UUID"]:
        raise ValueError("noncanonical project UUID")
    if not re.fullmatch(r"[a-z]{20}", values["PROJECT_PUBLIC_REF"]):
        raise ValueError("noncanonical public project reference")
    return {"project_ref": values["PROJECT_PUBLIC_REF"], "technical_name": ref, "project_uuid": values["PROJECT_UUID"],
            "anon_key": values["ANON_KEY_PROJETO"], "service_role_key": values["SERVICE_ROLE_KEY_PROJETO"],
            "jwt_secret": values["JWT_SECRET_PROJETO"]}


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def withdraw(root: Path, ref: str) -> None:
    directory = plain_directory(root / ".functions-tenants")
    locks = plain_directory(root / ".functions-locks")
    marker = locks / (canonical_ref(ref) + ".withdrawn")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b"lifecycle-in-progress\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(locks)
    path = directory / (ref + ".json")
    path.unlink(missing_ok=True)  # unlink, never follow a symlink
    fsync_directory(directory)


def publish(root: Path, ref: str) -> None:
    data = projection(root, ref)
    directory = plain_directory(root / ".functions-tenants")
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / (ref + ".json"))
        fsync_directory(directory)
        locks = plain_directory(root / ".functions-locks")
        (locks / (ref + ".withdrawn")).unlink(missing_ok=True)
        fsync_directory(locks)
    finally:
        Path(name).unlink(missing_ok=True)


def validate_lock(fd: int | None, path: Path) -> None:
    if fd is None or path.is_symlink():
        raise ValueError("lifecycle lock required")
    held, expected = os.fstat(fd), path.stat()
    if not stat.S_ISREG(held.st_mode) or (held.st_dev, held.st_ino) != (expected.st_dev, expected.st_ino):
        raise ValueError("invalid lifecycle lock descriptor")
    import fcntl
    fcntl.flock(fd, (fcntl.LOCK_SH if path.name == "global" else fcntl.LOCK_EX) | fcntl.LOCK_NB)


def sync(root: Path) -> None:
    import fcntl
    locks = plain_directory(root / ".functions-locks")
    with os.fdopen(os.open(locks / "global", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        directory = plain_directory(root / ".functions-tenants")
        # Withdraw before parsing: invalid canonical state must not retain stale credentials.
        unexpected_directory = False
        for path in directory.iterdir():
            if path.is_dir() and not path.is_symlink():
                unexpected_directory = True
            else:
                path.unlink()
        fsync_directory(directory)
        if unexpected_directory:
            raise ValueError("unexpected directory in Functions projection")
        projects = root / "projects"
        if projects.is_symlink() or not projects.is_dir():
            raise ValueError("canonical projects directory required")
        refs = [canonical_ref(p.name) for p in projects.iterdir() if p.name != ".gitkeep"]
        try:
            for ref in refs:
                marker = locks / (ref + ".withdrawn")
                if marker.exists() or marker.is_symlink():
                    raise ValueError("unfinished lifecycle requires explicit physical-state recovery")
            for ref in refs:
                publish(root, ref)
        except Exception:
            for ref in refs:
                (directory / (ref + ".json")).unlink(missing_ok=True)
            fsync_directory(directory)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--lock-fd", type=int)
    parser.add_argument("--tenant-lock-fd", type=int)
    parser.add_argument("action", choices=("sync", "publish", "withdraw"))
    parser.add_argument("ref", nargs="?")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if args.action == "sync":
        if args.ref is not None:
            parser.error("sync does not accept a tenant")
        sync(root)
    else:
        ref = canonical_ref(args.ref or "")
        validate_lock(args.lock_fd, root / ".functions-locks/global")
        validate_lock(args.tenant_lock_fd, root / f".functions-locks/{ref}")
        {"publish": publish, "withdraw": withdraw}[args.action](root, ref)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Functions projection failed: {error}") from error
