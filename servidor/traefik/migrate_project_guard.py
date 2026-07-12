from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def desired_labels(project_ref: str, project_uuid: str) -> list[str]:
    prefix = f"traefik.http.middlewares.supabase-guard-{project_ref}.plugin.supabaseguard"
    return [
        f'      - "{prefix}.profile=project"',
        f'      - "{prefix}.mode=${{TRAEFIK_GUARD_PROJECT_MODE:-observe}}"',
        f'      - "{prefix}.scope={project_uuid}"',
        f'      - "{prefix}.maxTrackedClients=${{TRAEFIK_GUARD_MAX_TRACKED_CLIENTS:-10000}}"',
        f'      - "{prefix}.cleanupInterval=${{TRAEFIK_GUARD_CLEANUP_INTERVAL:-5m}}"',
        f'      - "{prefix}.authThreshold=${{TRAEFIK_GUARD_AUTH_THRESHOLD:-12}}"',
        f'      - "{prefix}.authWindow=${{TRAEFIK_GUARD_AUTH_WINDOW:-10m}}"',
        f'      - "{prefix}.authBanTime=${{TRAEFIK_GUARD_AUTH_BAN_TIME:-15m}}"',
        f'      - "{prefix}.scannerThreshold=${{TRAEFIK_GUARD_SCANNER_THRESHOLD:-2}}"',
        f'      - "{prefix}.scannerWindow=${{TRAEFIK_GUARD_SCANNER_WINDOW:-2m}}"',
        f'      - "{prefix}.scannerBanTime=${{TRAEFIK_GUARD_SCANNER_BAN_TIME:-1h}}"',
    ]


def migrate_compose(compose_path: Path, project_ref: str, project_uuid: str, apply: bool) -> bool:
    source = compose_path.read_text(encoding="utf-8")
    middleware_name = f"supabase-guard-{project_ref}@docker"
    labels = desired_labels(project_ref, project_uuid)
    labels_present = all(label in source for label in labels)

    route_pattern = re.compile(
        rf'(^\s*-\s*"traefik\.http\.routers\.supabase-nginx-{re.escape(project_ref)}\.middlewares=)([^"]*)("\s*$)',
        re.MULTILINE,
    )
    match = route_pattern.search(source)
    if match is None:
        raise RuntimeError(f"router middleware label not found in {compose_path}")

    middlewares = [item.strip() for item in match.group(2).split(",") if item.strip()]
    route_present = middleware_name in middlewares
    if labels_present and route_present:
        return False
    if not apply:
        return True

    if not route_present:
        insert_at = 1 if middlewares and middlewares[0] == "rate-limit@file" else 0
        middlewares.insert(insert_at, middleware_name)
        replacement = match.group(1) + ",".join(middlewares) + match.group(3)
        source = source[: match.start()] + replacement + source[match.end() :]

    if not labels_present:
        anchor = (
            f'      - "traefik.http.middlewares.nginx-{project_ref}-stripprefix.'
            f'stripprefix.prefixes=/{project_ref}"'
        )
        if anchor not in source:
            raise RuntimeError(f"strip prefix label not found in {compose_path}")
        source = source.replace(anchor, "\n".join(labels + [anchor]), 1)

    backup = compose_path.with_suffix(compose_path.suffix + ".before-supabaseguard")
    if not backup.exists():
        shutil.copy2(compose_path, backup)

    fd, temp_name = tempfile.mkstemp(prefix=compose_path.name + ".", dir=compose_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, compose_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


def migrate_projects(projects_dir: Path, apply: bool) -> list[Path]:
    changed: list[Path] = []
    if not projects_dir.exists():
        return changed
    for project_dir in sorted(path for path in projects_dir.iterdir() if path.is_dir()):
        env_path = project_dir / ".env"
        compose_path = project_dir / "docker-compose.yml"
        if not env_path.exists() or not compose_path.exists():
            continue
        env = read_env(env_path)
        project_ref = env.get("PROJECT_ID") or project_dir.name
        project_uuid = env.get("PROJECT_UUID", "")
        if not project_uuid:
            raise RuntimeError(f"PROJECT_UUID missing in {env_path}")
        if migrate_compose(compose_path, project_ref, project_uuid, apply):
            changed.append(compose_path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "projects",
    )
    args = parser.parse_args()

    try:
        changed = migrate_projects(args.projects_dir, args.apply)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not changed:
        print("all projects already use Supabase Guard")
        return 0

    for path in changed:
        action = "updated" if args.apply else "needs migration"
        print(f"{action}: {path}")
    return 0 if args.apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
