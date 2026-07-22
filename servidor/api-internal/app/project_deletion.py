"""Primitivas canônicas para exclusão física de projetos.

Este módulo concentra a geração dos tokens internos, remoção de tenants e drop
do banco. Não há caminho alternativo via host-agent ou SQL sem autenticação: uma
falha interrompe o fluxo para que o job possa ser diagnosticado e retomado.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import time
import urllib.parse
from collections.abc import Mapping

import asyncpg
import httpx
from dotenv import dotenv_values

from app.runtime_config import REALTIME_INTERNAL_URL, SUPAVISOR_INTERNAL_URL


class ProjectDeletionError(RuntimeError):
    """Falha explícita em uma etapa obrigatória da exclusão."""


def _base64url_no_padding(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _create_hs256_jwt(payload: Mapping[str, object], secret: str) -> str:
    header_b64 = _base64url_no_padding(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload_b64 = _base64url_no_padding(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signature = hmac.new(
        secret.encode(),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_base64url_no_padding(signature)}"


def _build_short_lived_jwt(secret: str, issuer: str) -> str:
    now = int(time.time())
    return _create_hs256_jwt(
        {"role": "anon", "iss": issuer, "iat": now, "exp": now + 3600},
        secret,
    )


def load_project_environment(
    projects_root: pathlib.Path,
    project_name: str,
) -> dict[str, str]:
    """Carrega o ambiente canônico e rejeita projeto incompleto ou fora da raiz."""

    resolved_root = projects_root.resolve()
    project_dir = (resolved_root / project_name).resolve()
    if project_dir.parent != resolved_root:
        raise ProjectDeletionError("diretório do projeto está fora da raiz permitida")

    env_path = project_dir / ".env"
    if not env_path.is_file():
        raise ProjectDeletionError(f"ambiente do projeto {project_name} não existe")

    raw_values = dotenv_values(env_path, interpolate=False)
    values = {
        str(key): str(value)
        for key, value in raw_values.items()
        if key is not None and value is not None
    }
    for required in ("PROJECT_UUID", "ANON_KEY_PROJETO"):
        if not values.get(required, "").strip():
            raise ProjectDeletionError(
                f"ambiente do projeto {project_name} não contém {required}"
            )
    return values


def build_realtime_delete_token(project_env: Mapping[str, str]) -> str:
    """Retorna exclusivamente a chave anon persistida para o tenant."""

    token = project_env.get("ANON_KEY_PROJETO", "").strip()
    if not token:
        raise ProjectDeletionError("ANON_KEY_PROJETO ausente para excluir tenant Realtime")
    return token


def build_global_delete_token(issuer: str) -> str:
    """Gera o token dos serviços globais a partir do secret injetado no processo."""

    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        raise ProjectDeletionError("JWT_SECRET não foi injetado na Projects API")
    return _build_short_lived_jwt(secret, issuer)


async def delete_tenant(
    *,
    service_label: str,
    base_url: str,
    tenant_id: str,
    token: str,
) -> None:
    encoded_tenant = urllib.parse.quote(tenant_id, safe="")
    url = f"{base_url}/api/tenants/{encoded_tenant}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.delete(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise ProjectDeletionError(
            f"{service_label}: falha de transporte ao remover tenant {tenant_id}"
        ) from exc

    if response.status_code not in {200, 202, 204, 404}:
        raise ProjectDeletionError(
            f"{service_label}: HTTP {response.status_code} ao remover tenant {tenant_id}"
        )


async def delete_realtime_tenant(tenant_id: str, token: str) -> None:
    await delete_tenant(
        service_label="Realtime",
        base_url=REALTIME_INTERNAL_URL,
        tenant_id=tenant_id,
        token=token,
    )


async def delete_supavisor_tenant(tenant_id: str, token: str) -> None:
    await delete_tenant(
        service_label="Supavisor",
        base_url=SUPAVISOR_INTERNAL_URL,
        tenant_id=tenant_id,
        token=token,
    )


async def terminate_supavisor_pools(tenant_id: str, token: str) -> None:
    encoded_tenant = urllib.parse.quote(tenant_id, safe="")
    url = f"{SUPAVISOR_INTERNAL_URL}/api/tenants/{encoded_tenant}/terminate"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise ProjectDeletionError(
            f"Supavisor: falha de transporte ao encerrar pools de {tenant_id}"
        ) from exc

    if response.status_code not in {200, 204, 404}:
        raise ProjectDeletionError(
            f"Supavisor: HTTP {response.status_code} ao encerrar pools de {tenant_id}"
        )


async def drain_database_connections(
    conn: asyncpg.Connection,
    db_name: str,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    """Encerra conexões e falha se um pool continuar reconectando."""

    deadline = time.monotonic() + timeout_seconds
    quiet_since: float | None = None
    while True:
        active_connections = await conn.fetchval(
            """
            SELECT count(*)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        now = time.monotonic()
        if active_connections:
            quiet_since = None
            await conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
                """,
                db_name,
            )
        elif quiet_since is None:
            quiet_since = now
        elif now - quiet_since >= 2.0:
            return

        if now >= deadline:
            raise ProjectDeletionError(
                f"conexões continuaram sendo abertas no banco {db_name}"
            )
        await asyncio.sleep(0.5)


async def drop_database_force(conn: asyncpg.Connection, db_name: str) -> None:
    quoted_db = '"' + db_name.replace('"', '""') + '"'
    await conn.execute(f"DROP DATABASE IF EXISTS {quoted_db} WITH (FORCE)")
