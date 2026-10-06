"""Prepare an offline installation for canonical public project paths."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "servidor/host-agent"))
sys.path.insert(0, str(REPO / "servidor/generateProject"))
from hostagent.envfile import read_canonical_env_value  # noqa: E402
from hostagent.templates import _build_replacements, _normalize_public_base_url, sync_project_generated_files  # noqa: E402
from project_env_urls import render_project_url_values  # noqa: E402
from migrate_snippet_namespaces import mapping  # noqa: E402
from migration_files import (atomic_write, canonical_path, file_digest, plain_tree,
                             remove_owned, sync_tree)  # noqa: E402

JOURNAL = ".public-reference-cutover"


def catalog(root: Path) -> list[dict]:
    database = read_canonical_env_value(root / ".env", "POSTGRES_DB")
    if not database:
        raise RuntimeError("Canonical control-plane database is required")
    query = """SELECT COALESCE(json_agg(row_to_json(p)), '[]'::json)::text FROM (
      SELECT p.id, p.tenant_uuid, p.name, p.public_ref,
        ARRAY(SELECT DISTINCT unnest(ARRAY[h.old_name,h.new_name])
              FROM project_name_history h WHERE h.project_id=p.id AND h.status='succeeded') AS legacy_names
      FROM projects p ORDER BY p.id
    ) p;"""
    result = subprocess.run(["docker", "exec", "-i", "supabase-db", "psql", "-X", "-qAt",
                             "-v", "ON_ERROR_STOP=1", "-U", "supabase_admin", "-d", database],
                            input=query, text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    mapping(data)
    return data


def require_stopped(projects: list[dict]) -> None:
    api = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", "projects-api"],
                         text=True, capture_output=True, check=True).stdout.strip()
    agent = subprocess.run(["systemctl", "show", "supabase-host-agent.service", "--property=ActiveState", "--value"],
                           text=True, capture_output=True, check=True).stdout.strip()
    functions = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", "supabase-edge-functions"],
                               text=True, capture_output=True, check=True).stdout.strip()
    if api != "false" or agent != "inactive" or functions != "false":
        raise RuntimeError("Stop Projects API, host-agent and Functions supervisor before offline cutover")
    for project in projects:
        for service in ("nginx", "auth"):
            state = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}",
                                    f"supabase-{service}-{project['name']}"],
                                   text=True, capture_output=True, check=True).stdout.strip()
            if state != "false":
                raise RuntimeError("Stop project Auth and gateways before cutover")


def prepare(root: Path, projects: list[dict], *, apply: bool = False) -> list[str]:
    root = canonical_path(root)
    mapping(projects)
    if root.is_symlink() or (root / "projects").is_symlink():
        raise RuntimeError("Canonical installation directories are required")
    journal = root / JOURNAL
    if journal.exists():
        raise RuntimeError("Unfinished cutover requires explicit rollback")
    raw_base = read_canonical_env_value(root / ".env", "SERVER_URL")
    if not raw_base:
        raise RuntimeError("Canonical SERVER_URL is required")
    base = _normalize_public_base_url(raw_base, read_canonical_env_value(root / ".env", "SERVER_PROTO"))
    updates = {}
    files = []
    projections = {}
    for project in projects:
        directory = root / "projects" / project["name"]
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("Physical project directory is required")
        env = directory / ".env"
        if read_canonical_env_value(env, "PROJECT_ID") != project["name"] or read_canonical_env_value(env, "PROJECT_UUID") != project["tenant_uuid"]:
            raise RuntimeError("Catalog and physical tenant identity diverge")
        existing = read_canonical_env_value(env, "PROJECT_PUBLIC_REF")
        if existing is not None and existing != project["public_ref"]:
            raise RuntimeError("Physical public reference diverges from the catalog")
        configured = {key: read_canonical_env_value(env, key) for key in
                      ("API_EXTERNAL_URL", "SITE_URL", "ADDITIONAL_REDIRECT_URLS")}
        source_names = {project["name"], *project["legacy_names"]}
        allowed_auth_urls = {base + "/" + name + "/auth/v1" for name in source_names}
        allowed_auth_urls.add(base + "/" + project["public_ref"] + "/auth/v1")
        if configured["API_EXTERNAL_URL"] not in allowed_auth_urls:
            raise RuntimeError("Existing Auth URL is not canonical")
        values = render_project_url_values(configured, {"project_public_url": base + "/" + project["public_ref"]})
        values["PROJECT_PUBLIC_REF"] = project["public_ref"]
        values["API_EXTERNAL_URL"] = base + "/" + project["public_ref"] + "/auth/v1"
        lines = env.read_text(encoding="utf-8").splitlines()
        for key, value in values.items():
            indexes = [i for i, line in enumerate(lines) if line.startswith(key + "=")]
            if key == "PROJECT_PUBLIC_REF" and not indexes:
                lines.append(key + "=" + value)
                continue
            if len(indexes) != 1:
                raise RuntimeError("Exactly one canonical environment entry is required")
            if key in configured and configured[key] == value:
                continue
            if any(char in value for char in "\n\r\x00'\"$`\\"):
                raise RuntimeError("URL cannot be represented unambiguously in the environment")
            lines[indexes[0]] = key + "=" + value
        updates[project["name"]] = ("\n".join(lines) + "\n").encode()
        for name in (".env", ".dockerignore", "Dockerfile", "docker-compose.yml", f"nginx/nginx_{project['name']}.conf"):
            path = directory / name
            if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
                raise RuntimeError("Canonical generated project files are required")
            files.append(path)
        projection = canonical_path(root / ".functions-tenants" / (project["name"] + ".json"))
        if projection.exists():
            data = json.loads(projection.read_text(encoding="utf-8"))
            if (data.get("project_uuid") != project["tenant_uuid"]
                    or data.get("project_ref") not in {project["name"], project["public_ref"]}
                    or ("technical_name" in data and data["technical_name"] != project["name"])):
                raise RuntimeError("Functions projection identity diverges from catalog")
            files.append(projection)
            projections[project["name"]] = projection
    if not apply:
        return sorted(updates)
    require_stopped(projects)
    journal.mkdir(mode=0o700)
    snapshots = {}
    try:
        for path in files:
            backup = journal / path.relative_to(root)
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, backup)
            snapshots[path.relative_to(root).as_posix()] = {
                "sha256": file_digest(backup), "mode": backup.stat().st_mode & 0o777,
            }
        sync_tree(journal)
        manifest = {"root": str(root.resolve()), "files": snapshots}
        atomic_write(journal / "manifest.json", json.dumps(manifest).encode())
        for path in files:
            if file_digest(path) != snapshots[path.relative_to(root).as_posix()]["sha256"]:
                raise RuntimeError("Project configuration changed after preflight")
    except BaseException:
        remove_owned(journal, root)
        raise
    try:
        for project in projects:
            directory = root / "projects" / project["name"]
            env = directory / ".env"
            atomic_write(env, updates[project["name"]], env.stat().st_mode & 0o777)
            sync_project_generated_files(root=root, scripts_dir=root / "generateProject", project_dir=directory, project=project["name"])
            atomic_write(directory / ".dockerignore", (root / "generateProject/.dockerignore").read_bytes(),
                         (directory / ".dockerignore").stat().st_mode & 0o777)
            if project["name"] in projections:
                material = _build_replacements(root, directory, project["name"])
                data = {"project_ref": project["public_ref"], "technical_name": project["name"],
                        "project_uuid": project["tenant_uuid"], "anon_key": material["anon_key"],
                        "service_role_key": material["service_role_key"], "jwt_secret": material["jwt_secret"]}
                atomic_write(projections[project["name"]], json.dumps(data, sort_keys=True).encode(), 0o600)
    except BaseException:
        restore(root)
        raise
    remove_owned(journal, root)
    return sorted(updates)


def restore(root: Path) -> None:
    root = canonical_path(root)
    journal = root / JOURNAL
    plain_tree(journal)
    manifest = journal / "manifest.json"
    if not manifest.exists():
        remove_owned(journal, root)
        return
    data = json.loads(manifest.read_text())
    if data["root"] != str(root.resolve()):
        raise RuntimeError("Cutover journal identity mismatch")
    for relative, metadata in data["files"].items():
        target = canonical_path(root / relative)
        backup = canonical_path(journal / relative)
        if (Path(relative).is_absolute() or ".." in Path(relative).parts
                or not (target.resolve().is_relative_to((root / "projects").resolve())
                        or (target.parent == root / ".functions-tenants" and target.suffix == ".json"))
                or not backup.resolve().is_relative_to(journal.resolve())
                or file_digest(backup) != metadata["sha256"]
                or backup.stat().st_mode & 0o777 != metadata["mode"]):
            raise RuntimeError("Cutover recovery integrity failure")
    for relative, metadata in data["files"].items():
        atomic_write(root / relative, (journal / relative).read_bytes(), metadata["mode"])
    remove_owned(journal, root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--export-catalog", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.export_catalog and (args.apply or args.rollback):
        parser.error("--export-catalog cannot be combined with apply or rollback")
    os.umask(0o077)
    projects = catalog(args.root)
    if args.rollback:
        require_stopped(projects)
        restore(args.root)
        return
    if args.export_catalog:
        atomic_write(args.export_catalog, json.dumps(projects, indent=2).encode(), 0o600)
        return
    print(json.dumps(prepare(args.root, projects, apply=args.apply)))


if __name__ == "__main__":
    main()
