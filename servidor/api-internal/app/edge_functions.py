"""Publish private tenant contexts for the shared Edge Runtime."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from uuid import UUID

from app.functions_network import network_hosts

PROJECT = re.compile(r"[a-z_][a-z0-9_]{2,39}\Z")
ENVIRONMENT = {"SUPABASE_URL", "SUPABASE_PUBLIC_URL", "SUPABASE_ANON_KEY",
               "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_URL"}


def project_name(name: str) -> str:
    if not PROJECT.fullmatch(name):
        raise ValueError("Invalid project name")
    return name


def private_directory(path: Path) -> Path:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise RuntimeError("Refusing a symlinked Functions directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def runtime_directory(root: Path) -> Path:
    return private_directory(root / ".functions-runtime")


def project_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Invalid project UUID")
    return value


@asynccontextmanager
async def configuration_lock(root: Path, name: str):
    # Share the host-agent lifecycle locks, always global before tenant.
    locks = private_directory(root / ".functions-locks")
    descriptors = []
    try:
        for file, mode in (("global", fcntl.LOCK_SH), (project_name(name), fcntl.LOCK_EX)):
            descriptor = os.open(locks / file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            descriptors.append(descriptor)
            while True:
                try:
                    fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.05)
        yield
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def retire_current(root: Path, name: str) -> None:
    """Start retention at deactivation, rather than at generation creation."""
    context = runtime_directory(root) / "tenants" / (project_name(name) + ".json")
    try:
        from app.edge_function_store import regular_bytes
        revision = json.loads(regular_bytes(context, 65536)).get("revision", "")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            return
        previous = runtime_directory(root) / "code" / project_uuid(json.loads(regular_bytes(context, 65536))["uuid"]) / revision
        if previous.is_dir() and not previous.is_symlink():
            os.utime(previous, follow_symlinks=False)
    except (OSError, RuntimeError, ValueError, AttributeError, KeyError, TypeError):
        # Invalid old context must never prevent an administrative withdrawal.
        pass


def withdraw(root: Path, name: str) -> None:
    directory = private_directory(runtime_directory(root) / "tenants")
    retire_current(root, name)
    (directory / (project_name(name) + ".json")).unlink(missing_ok=True)
    sync_directory(directory)



def code_files(directory: Path):
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise RuntimeError("Refusing symlinked function code")
    for path in sorted(directory.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise RuntimeError("Function code must contain regular files and directories")
        if stat.S_ISREG(mode):
            yield path, path.relative_to(directory)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def context_value(name: str, identity: str, secret: str, environment: dict[str, str],
                  files: dict[str, bytes], network_allowlist: list[str] | None = None) -> dict:
    name = project_name(name)
    if (str(UUID(identity)) != identity or set(environment) != ENVIRONMENT
            or not isinstance(secret, str) or not secret
            or not all(isinstance(value, str) and value for value in environment.values())):
        raise ValueError("Incomplete tenant Functions credentials")
    state = {"project": name, "uuid": identity, "jwt_secret": secret, "env": environment}
    if network_allowlist is not None:
        state["network_allowlist"] = network_hosts(network_allowlist)
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode())
    for relative, data in sorted(files.items()):
        if Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise ValueError("Invalid published function path")
        digest.update(relative.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return {**state, "revision": digest.hexdigest()}


def read_context(root: Path, name: str, identity: str) -> dict | None:
    from app.edge_function_store import regular_bytes
    try:
        state = json.loads(regular_bytes(runtime_directory(root) / "tenants" / (project_name(name) + ".json"), 65536))
    except FileNotFoundError:
        return None
    if (not isinstance(state, dict) or set(state) not in ({"project", "uuid", "jwt_secret", "env", "revision"},
            {"project", "uuid", "jwt_secret", "env", "revision", "network_allowlist"})
            or state["project"] != name or state["uuid"] != identity
            or not isinstance(state["jwt_secret"], str) or not state["jwt_secret"]
            or not isinstance(state["env"], dict) or set(state["env"]) != ENVIRONMENT
            or not all(isinstance(value, str) and value for value in state["env"].values())
            or not isinstance(state["revision"], str) or not re.fullmatch(r"[0-9a-f]{64}", state["revision"])):
        raise RuntimeError("Invalid runtime project context")
    if "network_allowlist" in state and network_hosts(state["network_allowlist"]) != state["network_allowlist"]:
        raise RuntimeError("Invalid runtime network policy")
    return state


def verify_generation(root: Path, context: dict, files: dict[str, bytes]) -> None:
    target = runtime_directory(root) / "code" / project_uuid(context["uuid"]) / context["revision"]
    try:
        actual = {relative.as_posix(): path.read_bytes() for path, relative in code_files(target)}
        if not target.is_dir() or actual != files:
            raise RuntimeError("Immutable function generation integrity check failed")
    except (OSError, RuntimeError):
        withdraw(root, context["project"])
        raise


def prepare_context(root: Path, name: str, identity: str, secret: str, environment: dict[str, str],
                    files: dict[str, bytes], network_allowlist: list[str] | None = None) -> dict:
    state = context_value(name, identity, secret, environment, files, network_allowlist)
    revision = state["revision"]
    code = private_directory(runtime_directory(root) / "code" / project_uuid(identity))
    target = code / revision
    if target.is_symlink():
        withdraw(root, name)
        raise RuntimeError("Refusing symlinked function generation")
    if not target.exists():
        temporary = Path(tempfile.mkdtemp(prefix=".publish-", dir=code))
        try:
            for relative, data in sorted(files.items()):
                destination = temporary / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with destination.open("wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                destination.chmod(0o400)
            actual = {relative.as_posix(): path.read_bytes() for path, relative in code_files(temporary)}
            if actual != files:
                raise RuntimeError("Function code changed during publication; retry")
            for directory in sorted((p for p in temporary.rglob("*") if p.is_dir()), reverse=True):
                sync_directory(directory)
            sync_directory(temporary)
            temporary.rename(target)
            sync_directory(code)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    verify_generation(root, state, files)
    return state


def activate_context(root: Path, state: dict) -> None:
    from app.edge_function_store import atomic_json
    name = project_name(state["project"])
    directory = private_directory(runtime_directory(root) / "tenants")
    retire_current(root, name)
    atomic_json(directory / (name + ".json"), state)
    # Older workers have a 60s lifetime; retain their code while they finish.
    code = runtime_directory(root) / "code" / project_uuid(state["uuid"])
    target = code / state["revision"]
    for previous in code.iterdir():
        if previous != target and not previous.is_symlink() and previous.is_dir() and time.time() - previous.stat().st_mtime > 120:
            shutil.rmtree(previous)


def publish(root: Path, name: str, identity: str, secret: str, environment: dict[str, str],
            *, files: dict[str, bytes] | None = None, network_allowlist: list[str] | None = None) -> None:
    if files is None:
        from app.edge_function_store import published_files
        files = published_files(root, name, identity)
    if not files:
        withdraw(root, name)
        return
    state = prepare_context(root, name, identity, secret, environment, files, network_allowlist)
    activate_context(root, state)


