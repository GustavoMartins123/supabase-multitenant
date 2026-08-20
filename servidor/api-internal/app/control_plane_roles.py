"""Provisionamento das identidades de banco do control plane.

Este modulo executa DDL de role e por isso pertence ao comando privilegiado
`python -m app.schema_migrations`, nunca ao processo que atende requisicoes.
Ele evita dependencias do runtime da API para que o container de migracao
precise apenas do DSN administrativo e da senha do papel provisionado.
"""

from __future__ import annotations

import re

import asyncpg


KEY_AUTHORIZER_ROLE = "key_authorizer"
KEY_AUTHORIZER_PASSWORD_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


async def ensure_key_authorizer_role(
    pool: asyncpg.Pool, *, password: str
) -> None:
    """Provision the fixed least-privilege data-plane database identity."""

    if not KEY_AUTHORIZER_PASSWORD_RE.fullmatch(password):
        raise RuntimeError(
            "KEY_AUTHORIZER_DB_PASSWORD must contain 32-128 URL-safe characters"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'key_authorizer'
                    ) THEN
                        CREATE ROLE key_authorizer WITH
                            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
                            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 40;
                    END IF;
                END
                $$;

                ALTER ROLE key_authorizer WITH
                    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
                    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 40;
                ALTER ROLE key_authorizer SET search_path = public, pg_catalog;
                ALTER ROLE key_authorizer SET statement_timeout = '3s';
                ALTER ROLE key_authorizer SET lock_timeout = '1s';
                ALTER ROLE key_authorizer SET idle_in_transaction_session_timeout = '3s';

                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM key_authorizer;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM key_authorizer;
                REVOKE CREATE ON SCHEMA public FROM key_authorizer;
                GRANT USAGE ON SCHEMA public TO key_authorizer;

                GRANT SELECT (
                    id, name, api_gateway_token_hash, api_keyset_version,
                    opaque_keys_activated_at
                ) ON projects TO key_authorizer;
                GRANT SELECT (
                    id, project_id, kind, allowed_services, status
                ) ON project_api_key_slots TO key_authorizer;
                GRANT SELECT (
                    id, slot_id, secret_hash, status, activated_at,
                    activate_at, expires_at, last_used_at, confirmed_at
                ) ON project_api_keys TO key_authorizer;
                GRANT UPDATE (last_used_at)
                    ON project_api_keys TO key_authorizer;
                """
            )
            password_statement = await conn.fetchval(
                "SELECT format('ALTER ROLE key_authorizer PASSWORD %L', $1::text)",
                password,
            )
            await conn.execute(password_statement)
            grant_connect = await conn.fetchval(
                """
                SELECT format(
                    'GRANT CONNECT ON DATABASE %I TO key_authorizer',
                    current_database()
                )
                """
            )
            await conn.execute(grant_connect)
