#!/usr/bin/env python3
"""Rotate the public path without changing the project's physical identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host-agent"))
from hostagent.envfile import read_canonical_env_value  # noqa: E402
from hostagent.templates import _build_replacements, _render_template  # noqa: E402
from project_env_urls import render_project_url_values  # noqa: E402


class ReferenceRotation:
    def __init__(
        self,
        root: Path,
        project: str,
        project_id: str,
        tenant_uuid: str,
        old_ref: str,
        new_ref: str,
        lock_fd: int,
        tenant_lock_fd: int,
    ):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{2,39}", project):
            raise ValueError("Invalid technical project name")
        for ref in (old_ref, new_ref):
            if not re.fullmatch(r"[a-z]{20}", ref):
                raise ValueError("Invalid public project reference")
        if old_ref == new_ref:
            raise ValueError("Public reference must change")
        self.project_id = str(uuid.UUID(project_id))
        self.tenant_uuid = str(uuid.UUID(tenant_uuid))
        if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
            raise RuntimeError("Canonical installation path must not use symbolic links")
        self.root, self.project = root.resolve(), project
        self.scripts = self.root / "generateProject"
        self.directory = self.root / "projects" / project
        if (
            self.directory.parent.is_symlink()
            or self.directory.is_symlink()
            or not self.directory.is_dir()
        ):
            raise RuntimeError("Canonical project directory is required")
        self.old_ref, self.new_ref = old_ref, new_ref
        self.lock_fd, self.tenant_lock_fd = lock_fd, tenant_lock_fd
        self.journal = self.directory / f".reference-rotation-{new_ref}"
        self.files = (".env", "Dockerfile", "docker-compose.yml", f"nginx/nginx_{project}.conf")
        self.running: list[str] = []
        self.backups: dict[str, dict[str, str | int]] = {}
        self.database = read_canonical_env_value(self.root / ".env", "POSTGRES_DB")
        if not self.database:
            raise RuntimeError("Control-plane database is required")

    def run(
        self, args: list[str], *, input: str | None = None, pass_fds: tuple[int, ...] = ()
    ) -> str:
        result = subprocess.run(
            args, input=input, text=True, capture_output=True, timeout=240, pass_fds=pass_fds
        )
        if result.returncode:
            raise RuntimeError(f"Canonical {args[0]} operation failed ({result.returncode})")
        return result.stdout.strip()

    def sql(self, query: str) -> str:
        return self.run(
            [
                "docker",
                "exec",
                "-i",
                "supabase-db",
                "psql",
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "supabase_admin",
                "-d",
                self.database,
            ],
            input=query,
        )

    def compose(self, *args: str) -> str:
        return self.run(
            [
                "docker",
                "compose",
                "--project-directory",
                str(self.directory),
                "-p",
                self.project,
                "--env-file",
                str(self.root / ".env"),
                "--env-file",
                str(self.directory / ".env"),
                *args,
            ]
        )

    def functions(self, action: str) -> None:
        self.run(
            [
                sys.executable,
                str(self.scripts / "functions_config.py"),
                "--root",
                str(self.root),
                "--lock-fd",
                str(self.lock_fd),
                "--tenant-lock-fd",
                str(self.tenant_lock_fd),
                action,
                self.project,
            ],
            pass_fds=(self.lock_fd, self.tenant_lock_fd),
        )

    def identity(self) -> dict[str, str]:
        result = self.sql(
            "SELECT json_build_object('name',name,'public_ref',public_ref,'tenant_uuid',tenant_uuid)::text "
            f"FROM projects WHERE id='{self.project_id}'::uuid;"
        )
        data = json.loads(result)
        if (
            not isinstance(data, dict)
            or data.get("name") != self.project
            or data.get("tenant_uuid") != self.tenant_uuid
        ):
            raise RuntimeError("Canonical project identity changed")
        return data

    def swap(self, old: str, new: str) -> None:
        changed = self.sql(
            "BEGIN; "
            f"UPDATE projects SET public_ref='{new}' WHERE id='{self.project_id}'::uuid "
            f"AND name='{self.project}' AND tenant_uuid='{self.tenant_uuid}'::uuid AND public_ref='{old}' "
            "RETURNING public_ref; COMMIT;"
        )
        if changed != new:
            raise RuntimeError("Public reference compare-and-swap failed")

    def checkpoint(self, state: str) -> None:
        data = json.dumps(
            {
                "state": state,
                "project_id": self.project_id,
                "tenant_uuid": self.tenant_uuid,
                "project": self.project,
                "old_ref": self.old_ref,
                "new_ref": self.new_ref,
                "running": self.running,
                "backups": self.backups,
            }
        )
        self.atomic_write(self.journal / "manifest.json", data.encode(), 0o600)

    @staticmethod
    def sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def atomic_write(path: Path, content: bytes, mode: int) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=path.name + ".rotation-", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as file:
                os.fchmod(file.fileno(), mode)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            ReferenceRotation.sync_directory(path.parent)
        finally:
            if temporary.exists():
                temporary.unlink()

    def validate_build_context(self) -> None:
        ignore = self.directory / ".dockerignore"
        if (
            ignore.is_symlink()
            or ignore.read_bytes() != (self.scripts / ".dockerignore").read_bytes()
        ):
            raise RuntimeError("Canonical Docker build context exclusions are required")

    def preflight(self) -> dict[str, str]:
        if any(self.directory.glob(".reference-rotation-*")):
            raise RuntimeError("Unresolved reference rotation requires explicit recovery")
        self.validate_build_context()
        for relative in self.files:
            path = self.directory / relative
            if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
                raise RuntimeError("Canonical generated project files are required")
        env = self.directory / ".env"
        raw_lines = env.read_text(encoding="utf-8").splitlines()
        for key, expected in (
            ("PROJECT_ID", self.project),
            ("PROJECT_UUID", self.tenant_uuid),
            ("PROJECT_PUBLIC_REF", self.old_ref),
        ):
            if (
                read_canonical_env_value(env, key) != expected
                or raw_lines.count(f"{key}={expected}") != 1
            ):
                raise RuntimeError("Physical project identity does not match the signed rotation")
        if self.identity().get("public_ref") != self.old_ref:
            raise RuntimeError("Canonical public reference changed")
        reservation = self.sql(
            "SELECT count(*) FROM project_reference_history h JOIN jobs j ON j.job_id=h.job_id "
            f"WHERE h.project_id='{self.project_id}'::uuid AND h.old_ref='{self.old_ref}' "
            f"AND h.new_ref='{self.new_ref}' AND h.status IN ('queued','running') "
            "AND j.action='rename' AND j.status IN ('queued','running') "
            "AND j.project_uuid=h.project_id AND j.created_by=h.actor_user_id "
            f"AND j.project='{self.project}' "
            "AND j.payload->>'actor_user_id'=h.actor_user_id::text "
            "AND j.payload->>'old_ref'=h.old_ref AND j.payload->>'new_ref'=h.new_ref;"
        )
        if reservation != "1":
            raise RuntimeError("Durable reference reservation is required")
        replacements = _build_replacements(self.root, self.directory, self.project)
        if (
            read_canonical_env_value(env, "API_EXTERNAL_URL")
            != replacements["project_auth_external_url"]
        ):
            raise RuntimeError("Auth external URL does not match the canonical project path")
        return replacements

    def render(self, replacements: dict[str, str]) -> None:
        url = replacements["public_base_url"] + "/" + self.new_ref
        updates = {"PROJECT_PUBLIC_REF": self.new_ref, "API_EXTERNAL_URL": url + "/auth/v1"}
        env = self.directory / ".env"
        configured = {}
        for key in ("API_EXTERNAL_URL", "SITE_URL", "ADDITIONAL_REDIRECT_URLS"):
            value = read_canonical_env_value(env, key)
            if value is not None:
                configured[key] = value
        updates.update(render_project_url_values(configured, {"project_public_url": url}))
        lines = env.read_text(encoding="utf-8").splitlines()
        for key, value in updates.items():
            matches = [i for i, line in enumerate(lines) if line.startswith(key + "=")]
            if len(matches) != 1:
                raise RuntimeError("Canonical URL entries are required")
            original = lines[matches[0]].partition("=")[2]
            if key in configured and configured[key] == value:
                continue
            if any(c in value for c in "\r\n\x00"):
                raise RuntimeError("Invalid Auth URL value")
            if original.startswith("'"):
                if "'" in value:
                    raise RuntimeError("Auth URL requires unambiguous quoting")
                value = "'" + value + "'"
            elif original.startswith('"'):
                if any(c in value for c in '\\"$`'):
                    raise RuntimeError("Auth URL requires unambiguous quoting")
                value = '"' + value + '"'
            lines[matches[0]] = key + "=" + value
        self.atomic_write(env, ("\n".join(lines) + "\n").encode(), env.stat().st_mode & 0o777)
        replacements = _build_replacements(self.root, self.directory, self.project)
        for template, relative in (
            ("nginxtemplate", self.files[3]),
            ("Dockerfile", "Dockerfile"),
            ("dockercomposetemplate", "docker-compose.yml"),
        ):
            _render_template(self.scripts / template, self.directory / relative, replacements)
            self.sync_directory((self.directory / relative).parent)

    def restart(self) -> None:
        if self.running:
            self.compose(
                "up",
                "-d",
                "--build",
                "--force-recreate",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                *self.running,
            )

    def rollback(self) -> None:
        self.functions("withdraw")
        self.compose("stop", "nginx", "auth")
        current = self.identity().get("public_ref")
        if current == self.new_ref:
            self.swap(self.new_ref, self.old_ref)
        elif current != self.old_ref:
            raise RuntimeError("Rollback cannot prove the canonical reference")
        for relative in self.files:
            backup = self.journal / relative
            self.atomic_write(
                self.directory / relative, backup.read_bytes(), backup.stat().st_mode & 0o777
            )
        self.restart()
        self.functions("publish")
        self.checkpoint("rolled_back")
        print("ROLLBACK_COMPLETE", flush=True)
        shutil.rmtree(self.journal)
        self.sync_directory(self.directory)

    def recover_rollback(self) -> None:
        self.validate_build_context()
        if self.journal.is_symlink() or not self.journal.is_dir():
            raise RuntimeError("Canonical rotation journal is required")
        manifest = self.journal / "manifest.json"
        if manifest.is_symlink():
            raise RuntimeError("Rotation manifest must not be a symbolic link")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        expected = {
            "project_id": self.project_id,
            "tenant_uuid": self.tenant_uuid,
            "project": self.project,
            "old_ref": self.old_ref,
            "new_ref": self.new_ref,
        }
        if any(data.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Rotation journal identity does not match the requested rollback")
        if data.get("state") not in {
            "prepared",
            "stopping_gateway",
            "files_rendered",
            "reference_committed",
            "completed",
            "rolled_back",
        }:
            raise RuntimeError("Unknown rotation recovery state")
        running = data.get("running")
        if (
            not isinstance(running, list)
            or len(set(running)) != len(running)
            or not set(running) <= {"auth", "nginx"}
        ):
            raise RuntimeError("Invalid rotation service state")
        backups = data.get("backups")
        if not isinstance(backups, dict) or set(backups) != set(self.files):
            raise RuntimeError("Complete rotation backups are required")
        for relative in self.files:
            backup = self.journal / relative
            target = self.directory / relative
            if (
                backup.is_symlink()
                or backup.parent.is_symlink()
                or target.is_symlink()
                or target.parent.is_symlink()
            ):
                raise RuntimeError("Rotation recovery files must not use symbolic links")
            record = backups[relative]
            if (
                hashlib.sha256(backup.read_bytes()).hexdigest() != record["sha256"]
                or backup.stat().st_mode & 0o777 != record["mode"]
            ):
                raise RuntimeError("Rotation backup integrity check failed")
        if any(path.is_symlink() for path in self.journal.rglob("*")):
            raise RuntimeError("Rotation journal must not contain symbolic links")
        if self.identity().get("public_ref") not in {self.old_ref, self.new_ref}:
            raise RuntimeError("Recovery cannot prove the canonical reference")
        self.running, self.backups = running, backups
        self.rollback()

    def rotate(self) -> None:
        print("HOST_AGENT_PROGRESS=reference:validate", flush=True)
        replacements = self.preflight()
        print("HOST_AGENT_PROGRESS=reference:prepare_transaction", flush=True)
        self.running = [
            name
            for name in self.compose("ps", "--status", "running", "--services").splitlines()
            if name in {"nginx", "auth"}
        ]
        self.journal.mkdir(mode=0o700)
        self.sync_directory(self.directory)
        for relative in self.files:
            target = self.journal / relative
            target.parent.mkdir(exist_ok=True, mode=0o700)
            shutil.copy2(self.directory / relative, target)
            with target.open("rb") as file:
                os.fsync(file.fileno())
            self.backups[relative] = {
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "mode": target.stat().st_mode & 0o777,
            }
            self.sync_directory(target.parent)
        self.checkpoint("prepared")
        try:
            self.functions("withdraw")
            print("HOST_AGENT_PROGRESS=reference:stop_services", flush=True)
            self.checkpoint("stopping_gateway")
            self.compose("stop", "nginx", "auth")
            print("HOST_AGENT_PROGRESS=reference:render_files", flush=True)
            self.render(replacements)
            self.checkpoint("files_rendered")
            print("HOST_AGENT_PROGRESS=reference:commit_reference", flush=True)
            self.swap(self.old_ref, self.new_ref)
            self.checkpoint("reference_committed")
            print("HOST_AGENT_PROGRESS=reference:restart_services", flush=True)
            self.restart()
            print("HOST_AGENT_PROGRESS=reference:publish_configuration", flush=True)
            self.functions("publish")
            self.checkpoint("completed")
        except BaseException:
            try:
                self.rollback()
            except BaseException as error:
                self.compose("stop", "nginx", "auth")
                raise RuntimeError(
                    "Rotation failed; rollback unconfirmed, gateway remains stopped"
                ) from error
            raise
        shutil.rmtree(self.journal)
        self.sync_directory(self.directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("project", "project_id", "tenant_uuid", "old_ref", "new_ref"):
        parser.add_argument(key)
    parser.add_argument("--lock-fd", required=True, type=int)
    parser.add_argument("--tenant-lock-fd", required=True, type=int)
    parser.add_argument("--recover-rollback", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)

    def interrupted(signum, frame):
        raise RuntimeError("Reference rotation interrupted")

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    rotation = ReferenceRotation(
        Path(__file__).resolve().parents[1],
        args.project,
        args.project_id,
        args.tenant_uuid,
        args.old_ref,
        args.new_ref,
        args.lock_fd,
        args.tenant_lock_fd,
    )
    if args.recover_rollback:
        rotation.recover_rollback()
    else:
        rotation.rotate()
        print("REFERENCE_ROTATED", flush=True)


if __name__ == "__main__":
    main()
