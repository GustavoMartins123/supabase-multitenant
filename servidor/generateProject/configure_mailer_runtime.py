#!/usr/bin/env python3
"""Provision independent mailer credentials; never print their values."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess

KEYS = (
    "MAILER_TEMPLATE_URL_SECRET",
    "MAILER_TEMPLATE_ADMIN_KEY",
    "MAILER_TEMPLATE_PUBLISH_KEY",
    "MAILER_TEMPLATE_DB_PASSWORD",
)


def prepare(root):
    root = Path(root)
    if not (root / ".env").is_file():
        raise RuntimeError("Arquivo .env canônico ausente")
    directory = root / "secrets/mailer"
    if directory.is_symlink():
        raise RuntimeError("Diretório privado inválido")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    configured = directory / ".configured"
    values = {}
    for key in KEYS:
        name = key.removeprefix("MAILER_TEMPLATE_")
        path = directory / name
        if path.is_symlink():
            raise RuntimeError("Arquivo de credencial inválido")
        if configured.exists() and not path.exists():
            raise RuntimeError(
                "Credencial configurada ausente; restaure o backup: " + key
            )
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as output:
                output.write(secrets.token_hex(32) + "\n")
        value = path.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise RuntimeError("Credencial inválida: " + key)
        values[key] = value
    if len(set(values.values())) != len(values):
        raise RuntimeError("As credenciais do mailer devem ser distintas")
    if not configured.exists():
        fd = os.open(configured, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write("mailer credentials initialized\n")
    return values


def role_sql(password):
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        raise ValueError("Senha inválida do mailer")
    return (
        """DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='mailer_template_service') THEN
        CREATE ROLE mailer_template_service; END IF; END $$;
    ALTER ROLE mailer_template_service WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD '%s';
    ALTER ROLE mailer_template_service SET search_path = public,pg_catalog;
    ALTER ROLE mailer_template_service SET statement_timeout = '5s';
    ALTER ROLE mailer_template_service SET lock_timeout = '2s';
    ALTER ROLE mailer_template_service SET idle_in_transaction_session_timeout = '10s';
    DO $$ DECLARE parent_role text; BEGIN
        FOR parent_role IN SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
            WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='mailer_template_service') LOOP
            EXECUTE format('REVOKE %%I FROM mailer_template_service',parent_role);
        END LOOP;
    END $$;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mailer_template_service;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mailer_template_service;
    REVOKE CREATE ON SCHEMA public FROM mailer_template_service;
    GRANT USAGE ON SCHEMA public TO mailer_template_service;
    GRANT SELECT(id,tenant_uuid,name) ON public.projects TO mailer_template_service;
    GRANT SELECT,INSERT,UPDATE ON public.mailer_template TO mailer_template_service;
    GRANT SELECT,INSERT ON public.mailer_template_version TO mailer_template_service;
    GRANT SELECT,INSERT ON public.mailer_template_default TO mailer_template_service;
    GRANT SELECT,INSERT,DELETE ON public.mailer_template_publication_grant TO mailer_template_service;
    DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %%I TO mailer_template_service',current_database()); END $$;
    """
        % password
    )


def database(root, values):
    # IDR initializes its control-plane schema at boot; multi-tenant uses the
    # privileged versioned migration runner and imports role_sql there instead.
    root = Path(root)
    sql = (root / "api-internal/app/mailer_templates_schema.sql").read_text()
    sql += "\n" + (root / "api-internal/app/mailer_templates_security.sql").read_text()
    sql += "\n" + role_sql(values["MAILER_TEMPLATE_DB_PASSWORD"])
    settings = {}
    for line in (root / ".env").read_text().splitlines():
        match = re.fullmatch(r"(?:export\s+)?(POSTGRES_DB|POSTGRES_USER)=(.*)", line.strip())
        if match:
            parts = shlex.split(match[2], comments=True)
            if len(parts) != 1:
                raise RuntimeError("Configuração PostgreSQL inválida para o mailer")
            settings[match[1]] = parts[0]
    user = settings.get("POSTGRES_USER", "supabase_admin")
    database_name = settings.get("POSTGRES_DB", "postgres")
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "supabase-db",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            user,
            "-d",
            database_name,
        ],
        input=sql,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode:
        raise RuntimeError(
            "Falha ao provisionar o schema ou a identidade do mailer; nenhum segredo foi exibido"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--database", action="store_true")
    args = parser.parse_args()
    values = prepare(args.server_root)
    if args.database:
        database(args.server_root, values)
    print(
        "Credenciais próprias do mailer preparadas; valores preservados em arquivo privado."
    )
