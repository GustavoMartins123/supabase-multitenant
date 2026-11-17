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
RESERVED_SLUGS = frozenset({
    "main", "secrets", "logs", "gc", "config", "health", "versions",
    "templates", "quotas", "alerts", "schedules",
})
ENVIRONMENT = {"SUPABASE_URL", "SUPABASE_PUBLIC_URL", "SUPABASE_ANON_KEY",
               "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_URL"}
SECRET_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
MAX_SECRETS = 64
MAX_SECRET_VALUE_BYTES = 8192
MAX_SECRETS_TOTAL_BYTES = 65536
CONTEXT_MAX_BYTES = 262144
RUNTIME_LIMIT_KEYS = ("memory_limit_mb", "worker_timeout_ms", "max_concurrent_project")
QUOTA_SPECS: dict[str, dict[str, int]] = {
    "max_functions": {"default": 128, "min": 1, "max": 256},
    "max_files": {"default": 64, "min": 1, "max": 128},
    "max_bytes": {"default": 1_000_000, "min": 10_000, "max": 5_000_000},
    "memory_limit_mb": {"default": 150, "min": 64, "max": 512},
    "worker_timeout_ms": {"default": 60_000, "min": 1_000, "max": 120_000},
    "max_concurrent_project": {"default": 2, "min": 1, "max": 4},
    "max_secrets": {"default": MAX_SECRETS, "min": 1, "max": 128},
    "max_secrets_total_bytes": {"default": MAX_SECRETS_TOTAL_BYTES, "min": 1024, "max": 131_072},
    "alert_threshold_pct": {"default": 80, "min": 50, "max": 99},
}
PLATFORM_MAX_CONCURRENT_GLOBAL = 4
RESERVED_SECRET_NAMES = frozenset({
    "PATH", "HOME", "USER", "SHELL", "PWD", "LANG", "LC_ALL", "TZ", "HOST", "PORT", "HOSTNAME", "VERIFY_JWT",
})
RESERVED_SECRET_PREFIXES = (
    "SUPABASE_", "PROJECT_", "TECHNICAL_", "JWT_", "POSTGRES_", "PG_", "DENO_",
    "EDGE_RUNTIME_", "TMP", "XDG_", "NODE_", "LD_", "HOST_AGENT_", "KEY_AUTHORIZER_",
    "FERNET_", "ENCRYPTION_", "ALLOCATOR_",
)


def validate_secret_name(name: str) -> str:
    if not isinstance(name, str) or not SECRET_NAME.fullmatch(name):
        raise ValueError("Invalid secret name")
    upper = name.upper()
    if upper in RESERVED_SECRET_NAMES or upper.startswith(RESERVED_SECRET_PREFIXES):
        raise ValueError(f"Secret name '{name}' is reserved by the platform")
    return name


def validate_secret_value(value: str) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise ValueError("Invalid secret value")
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > MAX_SECRET_VALUE_BYTES:
        raise ValueError(f"Secret value must be 1 to {MAX_SECRET_VALUE_BYTES} bytes")
    return value


def default_quotas() -> dict[str, int]:
    """Return baseline platform quota settings for an Edge Functions project."""
    return {key: spec["default"] for key, spec in QUOTA_SPECS.items()}


def quota_bounds() -> dict[str, dict[str, int]]:
    """Return allowed min/max/default specifications for each quota key."""
    return {key: dict(spec) for key, spec in QUOTA_SPECS.items()}


def validate_quotas(raw: dict | str | None, *, is_global_admin: bool = True, check_elevation: bool = False) -> dict[str, int]:
    """Merge and validate optional per-project quota overrides within platform ceilings."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    merged = default_quotas()
    if raw is None:
        return merged
    if not isinstance(raw, dict):
        raise ValueError("Invalid quotas configuration")
    unknown = set(raw) - set(QUOTA_SPECS)
    if unknown:
        raise ValueError(f"Unsupported quota fields: {', '.join(sorted(unknown))}")
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Quota '{key}' must be an integer")
        spec = QUOTA_SPECS[key]
        if value < spec["min"] or value > spec["max"]:
            raise ValueError(f"Quota '{key}' must be between {spec['min']} and {spec['max']}")
        if check_elevation and key != "alert_threshold_pct" and not is_global_admin and value > spec["default"]:
            raise PermissionError(f"Only platform administrators can raise '{key}' above {spec['default']}")
        merged[key] = value
    return merged


def runtime_limits_override(quotas: dict[str, int] | None) -> dict[str, int] | None:
    """Extract non-default runtime limits for the Deno supervisor context."""
    if not quotas:
        return None
    normalized = validate_quotas(quotas)
    if all(normalized[key] == QUOTA_SPECS[key]["default"] for key in RUNTIME_LIMIT_KEYS):
        return None
    return {key: normalized[key] for key in RUNTIME_LIMIT_KEYS}


def validate_runtime_limits(raw: dict | None) -> dict[str, int]:
    """Validate optional supervisor limits stored in the tenant runtime JSON."""
    if not isinstance(raw, dict) or set(raw) != set(RUNTIME_LIMIT_KEYS):
        raise ValueError("Invalid runtime limits")
    result: dict[str, int] = {}
    for key in RUNTIME_LIMIT_KEYS:
        val = raw.get(key)
        spec = QUOTA_SPECS[key]
        if isinstance(val, bool) or not isinstance(val, int) or val < spec["min"] or val > spec["max"]:
            raise ValueError(f"Invalid runtime limit '{key}'")
        result[key] = val
    return result


def validate_secrets(
    secrets: dict[str, str] | None,
    *,
    max_secrets: int = MAX_SECRETS,
    max_total_bytes: int = MAX_SECRETS_TOTAL_BYTES,
) -> dict[str, str]:
    if not secrets:
        return {}
    if not isinstance(secrets, dict) or len(secrets) > max_secrets:
        raise ValueError(f"A project may configure at most {max_secrets} secrets")
    total_bytes = 0
    cleaned: dict[str, str] = {}
    for key in sorted(secrets):
        name = validate_secret_name(key)
        value = validate_secret_value(secrets[key])
        total_bytes += len(name.encode("utf-8")) + len(value.encode("utf-8"))
        if total_bytes > max_total_bytes:
            raise ValueError("Total Edge Function secrets size exceeds project limit")
        cleaned[name] = value
    return cleaned


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
        state = json.loads(regular_bytes(context, CONTEXT_MAX_BYTES))
        revision = state.get("revision", "")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            return
        previous = runtime_directory(root) / "code" / project_uuid(state["uuid"]) / revision
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


def validate_public_functions(values: list[str] | tuple[str, ...] | None, *, files: dict[str, bytes] | None = None) -> list[str]:
    if not values:
        return []
    if not isinstance(values, (list, tuple)) or len(values) > 128:
        raise ValueError("Invalid public functions list")
    cleaned: list[str] = []
    for item in values:
        if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", item) or item in RESERVED_SLUGS:
            raise ValueError("Invalid public function name")
        if files is not None and f"{item}/index.ts" not in files:
            raise ValueError("Unpublished function cannot bypass JWT verification")
        cleaned.append(item)
    if len(set(cleaned)) != len(cleaned) or cleaned != sorted(cleaned):
        return sorted(set(cleaned))
    return list(cleaned)


def context_value(name: str, identity: str, secret: str, environment: dict[str, str],
                  files: dict[str, bytes], network_allowlist: list[str] | None = None,
                  secrets: dict[str, str] | None = None,
                  public_functions: list[str] | tuple[str, ...] | None = None,
                  limits: dict[str, int] | None = None) -> dict:
    name = project_name(name)
    if (str(UUID(identity)) != identity or set(environment) != ENVIRONMENT
            or not isinstance(secret, str) or not secret
            or not all(isinstance(value, str) and value for value in environment.values())):
        raise ValueError("Incomplete tenant Functions credentials")
    state: dict = {"project": name, "uuid": identity, "jwt_secret": secret, "env": environment}
    if network_allowlist is not None:
        state["network_allowlist"] = network_hosts(network_allowlist)
    validated_secrets = validate_secrets(secrets, max_secrets=QUOTA_SPECS["max_secrets"]["max"],
                                         max_total_bytes=QUOTA_SPECS["max_secrets_total_bytes"]["max"])
    if validated_secrets:
        state["secrets"] = validated_secrets
    validated_public = validate_public_functions(public_functions, files=files)
    if validated_public:
        state["public_functions"] = validated_public
    if limits is not None:
        state["limits"] = validate_runtime_limits(limits)
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode())
    for relative, data in sorted(files.items()):
        if Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise ValueError("Invalid published function path")
        digest.update(relative.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return {**state, "revision": digest.hexdigest()}


def read_context(root: Path, name: str, identity: str) -> dict | None:
    from app.edge_function_store import regular_bytes
    try:
        state = json.loads(regular_bytes(runtime_directory(root) / "tenants" / (project_name(name) + ".json"), CONTEXT_MAX_BYTES))
    except FileNotFoundError:
        return None
    required_keys = {"project", "uuid", "jwt_secret", "env", "revision"}
    allowed_keys = required_keys | {"network_allowlist", "secrets", "public_functions", "limits"}
    if (not isinstance(state, dict) or not required_keys.issubset(state)
            or not set(state).issubset(allowed_keys)
            or state["project"] != name or state["uuid"] != identity
            or not isinstance(state["jwt_secret"], str) or not state["jwt_secret"]
            or not isinstance(state["env"], dict) or set(state["env"]) != ENVIRONMENT
            or not all(isinstance(value, str) and value for value in state["env"].values())
            or not isinstance(state["revision"], str) or not re.fullmatch(r"[0-9a-f]{64}", state["revision"])):
        raise RuntimeError("Invalid runtime project context")
    if "network_allowlist" in state and network_hosts(state["network_allowlist"]) != state["network_allowlist"]:
        raise RuntimeError("Invalid runtime network policy")
    if "secrets" in state:
        try:
            if (not isinstance(state["secrets"], dict) or not state["secrets"]
                    or validate_secrets(state["secrets"], max_secrets=QUOTA_SPECS["max_secrets"]["max"],
                                        max_total_bytes=QUOTA_SPECS["max_secrets_total_bytes"]["max"]) != state["secrets"]):
                raise RuntimeError("Invalid runtime secrets")
        except ValueError as error:
            raise RuntimeError("Invalid runtime secrets") from error
    if "public_functions" in state:
        try:
            if (not isinstance(state["public_functions"], list) or not state["public_functions"]
                    or validate_public_functions(state["public_functions"]) != state["public_functions"]):
                raise RuntimeError("Invalid runtime public functions")
        except ValueError as error:
            raise RuntimeError("Invalid runtime public functions") from error
    if "limits" in state:
        try:
            if validate_runtime_limits(state["limits"]) != state["limits"]:
                raise RuntimeError("Invalid runtime limits")
        except ValueError as error:
            raise RuntimeError("Invalid runtime limits") from error
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
                    files: dict[str, bytes], network_allowlist: list[str] | None = None,
                    secrets: dict[str, str] | None = None,
                    public_functions: list[str] | tuple[str, ...] | None = None,
                    limits: dict[str, int] | None = None) -> dict:
    state = context_value(name, identity, secret, environment, files, network_allowlist, secrets=secrets, public_functions=public_functions, limits=limits)
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
            *, files: dict[str, bytes] | None = None, network_allowlist: list[str] | None = None,
            secrets: dict[str, str] | None = None,
            public_functions: list[str] | tuple[str, ...] | None = None,
            limits: dict[str, int] | None = None) -> None:
    if files is None:
        from app.edge_function_store import published_files
        files = published_files(root, name, identity)
    if not files:
        withdraw(root, name)
        return
    state = prepare_context(root, name, identity, secret, environment, files, network_allowlist, secrets=secrets, public_functions=public_functions, limits=limits)
    activate_context(root, state)


