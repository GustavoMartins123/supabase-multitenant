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

HOST_AGENT_ROLE = "host_agent_rw"
HOST_AGENT_PASSWORD_RE = KEY_AUTHORIZER_PASSWORD_RE


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


async def ensure_host_agent_rw_role(
    pool: asyncpg.Pool, *, password: str
) -> None:
    """Provision the least-privilege identity used by the host-agent.

    O agent precisa apenas de lease/heartbeat/resultado nas tabelas
    host_agent_* e do inventario de containers. Nenhuma outra tabela do
    control plane, nenhum database de tenant.
    """

    if not HOST_AGENT_PASSWORD_RE.fullmatch(password):
        raise RuntimeError(
            "HOST_AGENT_DB_PASSWORD must contain 32-128 URL-safe characters"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'host_agent_rw'
                    ) THEN
                        CREATE ROLE host_agent_rw WITH
                            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
                            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
                    END IF;
                END
                $$;

                ALTER ROLE host_agent_rw WITH
                    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
                    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
                ALTER ROLE host_agent_rw SET search_path = public, pg_catalog;
                ALTER ROLE host_agent_rw SET statement_timeout = '5s';
                ALTER ROLE host_agent_rw SET lock_timeout = '2s';
                ALTER ROLE host_agent_rw SET idle_in_transaction_session_timeout = '15s';

                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM host_agent_rw;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM host_agent_rw;
                REVOKE CREATE ON SCHEMA public FROM host_agent_rw;
                GRANT USAGE ON SCHEMA public TO host_agent_rw;

                GRANT SELECT, INSERT, UPDATE ON host_agent_workers TO host_agent_rw;
                GRANT SELECT, INSERT, UPDATE ON host_agent_commands TO host_agent_rw;
                GRANT SELECT, INSERT, UPDATE, DELETE ON project_container_state
                    TO host_agent_rw;
                """
            )
            password_statement = await conn.fetchval(
                "SELECT format('ALTER ROLE host_agent_rw PASSWORD %L', $1::text)",
                password,
            )
            await conn.execute(password_statement)
            grant_connect = await conn.fetchval(
                """
                SELECT format(
                    'GRANT CONNECT ON DATABASE %I TO host_agent_rw',
                    current_database()
                )
                """
            )
            await conn.execute(grant_connect)


async def ensure_platform_app_role(
    pool: asyncpg.Pool, *, password: str
) -> None:
    """Provision the Projects API application identity.

    DML completo apenas nas tabelas do schema public do control plane.
    Nenhum direito de administracao de cluster, nenhum database de tenant.
    """

    if not HOST_AGENT_PASSWORD_RE.fullmatch(password):
        raise RuntimeError(
            "PLATFORM_APP_DB_PASSWORD must contain 32-128 URL-safe characters"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'platform_app'
                    ) THEN
                        CREATE ROLE platform_app WITH
                            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
                            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 100;
                    END IF;
                END
                $$;

                ALTER ROLE platform_app WITH
                    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
                    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 100;
                ALTER ROLE platform_app SET search_path = public, pg_catalog;
                ALTER ROLE platform_app SET idle_in_transaction_session_timeout = '60s';

                GRANT USAGE ON SCHEMA public TO platform_app;
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON ALL TABLES IN SCHEMA public TO platform_app;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
                    TO platform_app;
                """
            )
            await conn.execute(
                "SELECT format('ALTER ROLE platform_app PASSWORD %L', $1::text)",
                password,
            )


async def ensure_platform_meta_admin_role(
    pool: asyncpg.Pool, *, password: str
) -> None:
    """Provision the dedicated identity used exclusively by Postgres-Meta.

    Membro de supabase_admin: direitos equivalentes dentro dos databases de
    tenant, mas credencial propria, revogavel e auditavel — o superuser em si
    nunca chega ao ambiente da Projects API.
    """

    if not HOST_AGENT_PASSWORD_RE.fullmatch(password):
        raise RuntimeError(
            "META_ADMIN_DB_PASSWORD must contain 32-128 URL-safe characters"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles
                        WHERE rolname = 'platform_meta_admin'
                    ) THEN
                        CREATE ROLE platform_meta_admin WITH
                            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
                            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20;
                    END IF;
                END
                $$;

                ALTER ROLE platform_meta_admin WITH
                    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
                    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20;
                ALTER ROLE platform_meta_admin SET statement_timeout = '30s';
                ALTER ROLE platform_meta_admin SET lock_timeout = '10s';

                GRANT supabase_admin TO platform_meta_admin;
                """
            )
            await conn.execute(
                "SELECT format('ALTER ROLE platform_meta_admin PASSWORD %L', $1::text)",
                password,
            )
