"""Configuracao do host-agent, derivada do .env canonico do servidor."""

from __future__ import annotations

import os
import socket
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path

from .envfile import read_env_file


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    root: Path
    projects_root: Path
    scripts_dir: Path
    backups_root: Path
    dsn: str
    hmac_secret: str
    worker_id: str
    poll_interval: float
    heartbeat_interval: float
    lease_seconds: int
    state_refresh_interval: float
    max_parallel_commands: int
    shutdown_grace: int
    schema_wait_timeout: float


def _float_env(env: dict[str, str], key: str, default: float) -> float:
    raw = (os.environ.get(key) or env.get(key) or "").strip()
    return float(raw) if raw else default


def _int_env(env: dict[str, str], key: str, default: int) -> int:
    raw = (os.environ.get(key) or env.get(key) or "").strip()
    return int(raw) if raw else default


def _env_lookup(env: dict[str, str], key: str) -> str:
    return (os.environ.get(key) or env.get(key) or "").strip()


def build_db_dsn_from_env(env: dict[str, str]) -> str:
    """Resolve o DSN do agent: HOST_AGENT_DB_DSN explicito > host_agent_rw.

    Fail-closed: sem DSN explicito e sem HOST_AGENT_DB_PASSWORD util, o agent
    recusa iniciar — nao existe mais derivacao por POSTGRES_USER.
    """

    dsn = _env_lookup(env, "HOST_AGENT_DB_DSN")
    if dsn:
        return dsn

    agent_user = _env_lookup(env, "HOST_AGENT_DB_USER") or "host_agent_rw"
    agent_password = _env_lookup(env, "HOST_AGENT_DB_PASSWORD")
    if not agent_password or agent_password == "pass":
        raise ConfigError(
            "HOST_AGENT_DB_PASSWORD ausente ou placeholder; o fallback pelo "
            "POSTGRES_USER foi removido. Gere a senha e aplique as migrations "
            "(role host_agent_rw) antes de iniciar o agent."
        )
    db_name = (
        _env_lookup(env, "HOST_AGENT_DB_NAME")
        or env.get("POSTGRES_DB")
        or "postgres"
    )
    if not env.get("POSTGRES_HOST") or not env.get("POSTGRES_PORT"):
        raise ConfigError("POSTGRES_HOST/POSTGRES_PORT ausentes no .env")
    return (
        "postgresql://"
        f"{urllib.parse.quote(agent_user, safe='')}"
        f":{urllib.parse.quote(agent_password, safe='')}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{db_name}"
    )

def load_config(root: str | Path) -> AgentConfig:
    root_path = Path(root).resolve()
    env_path = root_path / ".env"
    if not env_path.is_file():
        raise ConfigError(f".env do servidor nao encontrado em {env_path}")
    env = read_env_file(env_path)

    projects_root = (root_path / "projects").resolve()
    scripts_dir = (root_path / "generateProject").resolve()
    backups_root = (root_path / "backups").resolve()
    if not projects_root.is_dir():
        raise ConfigError(f"diretorio de projetos ausente: {projects_root}")
    if not scripts_dir.is_dir():
        raise ConfigError(f"diretorio de scripts ausente: {scripts_dir}")
    backups_root.mkdir(exist_ok=True)

    hmac_secret = (
        os.environ.get("HOST_AGENT_HMAC_SECRET")
        or env.get("HOST_AGENT_HMAC_SECRET")
        or ""
    ).strip()
    if not hmac_secret or hmac_secret == "pass":
        raise ConfigError("HOST_AGENT_HMAC_SECRET ausente ou placeholder")

    dsn = build_db_dsn_from_env(env)

    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    return AgentConfig(
        root=root_path,
        projects_root=projects_root,
        scripts_dir=scripts_dir,
        backups_root=backups_root,
        dsn=dsn,
        hmac_secret=hmac_secret,
        worker_id=worker_id,
        poll_interval=_float_env(env, "HOST_AGENT_POLL_INTERVAL", 2.0),
        heartbeat_interval=_float_env(env, "HOST_AGENT_HEARTBEAT_INTERVAL", 15.0),
        lease_seconds=_int_env(env, "HOST_AGENT_LEASE_SECONDS", 60),
        state_refresh_interval=_float_env(env, "HOST_AGENT_STATE_REFRESH_INTERVAL", 10.0),
        max_parallel_commands=_int_env(env, "HOST_AGENT_MAX_PARALLEL_COMMANDS", 3),
        shutdown_grace=_int_env(env, "HOST_AGENT_SHUTDOWN_GRACE", 300),
        schema_wait_timeout=_float_env(env, "HOST_AGENT_SCHEMA_WAIT_TIMEOUT", 180.0),
    )
