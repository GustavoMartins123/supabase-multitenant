from __future__ import annotations

import os
import urllib.parse


def get_project_meta_connection_string(project_ref: str) -> str:
    meta_dsn = (os.getenv("META_ADMIN_DSN") or "").strip()
    if not meta_dsn:
        raise RuntimeError("META_ADMIN_DSN ausente no ambiente da Projects API")
    dsn = urllib.parse.urlparse(meta_dsn)
    if dsn.scheme not in {"postgres", "postgresql"} or not dsn.hostname or not dsn.username:
        raise RuntimeError("DB_DSN inválido para construir a conexão administrativa do projeto")

    db_name = f"_supabase_{project_ref}"
    return urllib.parse.urlunparse(
        dsn._replace(
            path=f"/{urllib.parse.quote(db_name, safe='')}",
            params="",
            query="",
            fragment="",
        )
    )


def get_project_reader_connection_string(project_ref: str) -> str:
    meta_dsn = (os.getenv("META_ADMIN_DSN") or "").strip()
    reader_password = (os.getenv("PLATFORM_READER_DB_PASSWORD") or "").strip()
    if not meta_dsn or not reader_password or reader_password == "pass":
        raise RuntimeError(
            "platform_reader indisponivel para consulta de usuarios no projeto"
        )
    dsn = urllib.parse.urlparse(meta_dsn)
    if dsn.scheme not in {"postgres", "postgresql"} or not dsn.hostname:
        raise RuntimeError("META_ADMIN_DSN invalido para conectar o platform_reader")

    db_name = f"_supabase_{project_ref}"
    netloc = (
        f"platform_reader:{urllib.parse.quote(reader_password, safe='')}"
        f"@{dsn.hostname}:{dsn.port or 5432}"
    )
    return urllib.parse.urlunparse(
        dsn._replace(
            netloc=netloc,
            path=f"/{urllib.parse.quote(db_name, safe='')}",
            params="",
            query="",
            fragment="",
        )
    )
