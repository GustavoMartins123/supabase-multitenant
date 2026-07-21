#!/usr/bin/env python3
"""Render current project config from one extracted legacy project.

The migration is intentionally configuration-only. It reads the legacy
project ``.env`` but does not inspect or copy Storage files, database data,
backups, certificates or archives.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from migrate_legacy_studio import (
    ASSIGNMENT,
    EnvDocument,
    MigrationError,
    clean_value,
    is_placeholder,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ENV = REPO_ROOT / "servidor" / ".env"
TEMPLATE_ROOT = REPO_ROOT / "servidor" / "generateProject"
PROJECTS_ROOT = REPO_ROOT / "servidor" / "projects"
PROJECT_ID_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
CONFIG_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRESERVED_SETTINGS = {
    "ADDITIONAL_REDIRECT_URLS",
    "DISABLE_SIGNUP",
    "ENABLE_ANONYMOUS_USERS",
    "ENABLE_EMAIL_AUTOCONFIRM",
    "ENABLE_EMAIL_SIGNUP",
    "ENABLE_IMAGE_TRANSFORMATION",
    "ENABLE_PHONE_AUTOCONFIRM",
    "ENABLE_PHONE_SIGNUP",
    "FILE_SIZE_LIMIT",
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED",
    "GOTRUE_MAILER_OTP_EXP",
    "GOTRUE_PASSWORD_MIN_LENGTH",
    "IMGPROXY_ENABLE_WEBP_DETECTION",
    "JWT_EXPIRY",
    "MAILER_SUBJECTS_CONFIRMATION",
    "MAILER_SUBJECTS_EMAIL_CHANGE",
    "MAILER_SUBJECTS_INVITE",
    "MAILER_SUBJECTS_MAGIC_LINK",
    "MAILER_SUBJECTS_RECOVERY",
    "MAILER_URLPATHS_CONFIRMATION",
    "MAILER_URLPATHS_EMAIL_CHANGE",
    "MAILER_URLPATHS_INVITE",
    "MAILER_URLPATHS_MAGIC_LINK",
    "MAILER_URLPATHS_RECOVERY",
    "PGRST_DB_MAX_ROWS",
    "PGRST_DB_POOL",
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT",
    "PGRST_DB_POOL_TIMEOUT",
    "PGRST_DB_SCHEMAS",
    "SMTP_ADMIN_EMAIL",
    "SMTP_HOST",
    "SMTP_PASS",
    "SMTP_PORT",
    "SMTP_SENDER_NAME",
    "SMTP_USER",
}
OBSOLETE_KEYS = {"LOGFLARE_API_KEY"}
TEMPLATE_FILES = {
    "docker-compose.yml": "dockercomposetemplate",
    "pooler/pooler.exs": "poolertemplate",
    "Dockerfile": "Dockerfile",
    ".dockerignore": ".dockerignore",
}


@dataclass(frozen=True)
class TokenAudit:
    role: str
    issuer: str
    issuer_matches_project_uuid: bool


@dataclass(frozen=True)
class ProjectMigration:
    project_id: str
    project_uuid: str
    target: Path
    files: dict[str, str]
    preserved: tuple[str, ...]
    generated: tuple[str, ...]
    obsolete: tuple[str, ...]
    unresolved: tuple[str, ...]
    token_audits: tuple[TokenAudit, ...]


def decode_segment(segment: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (ValueError, UnicodeEncodeError) as exc:
        raise MigrationError("JWT legado possui Base64URL invalido") from exc


def audit_jwt(token: str, secret: str, expected_role: str, project_uuid: str) -> TokenAudit:
    parts = token.split(".")
    if len(parts) != 3:
        raise MigrationError(f"JWT {expected_role} legado possui formato invalido")
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, decode_segment(parts[2])):
        raise MigrationError(f"JWT {expected_role} nao corresponde ao JWT_SECRET_PROJETO")
    try:
        payload = json.loads(decode_segment(parts[1]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"payload do JWT {expected_role} e invalido") from exc
    role = str(payload.get("role") or "")
    if role != expected_role:
        raise MigrationError(f"JWT esperado para {expected_role} declara role {role or 'ausente'}")
    issuer = str(payload.get("iss") or "")
    return TokenAudit(
        role=role,
        issuer=issuer,
        issuer_matches_project_uuid=issuer.lower() == project_uuid.lower(),
    )


def normalize_public_base(server_url: str, server_proto: str) -> tuple[str, str]:
    raw_url = clean_value(server_url).rstrip("/")
    proto = clean_value(server_proto).lower()
    if raw_url.startswith(("http://", "https://")):
        scheme, host = raw_url.split("://", 1)
        return raw_url, host
    if proto not in {"http", "https"} or not raw_url:
        raise MigrationError("SERVER_URL/SERVER_PROTO invalidos no servidor/.env")
    return f"{proto}://{raw_url}", raw_url


def replace_placeholders(text: str, values: dict[str, str], template_name: str) -> str:
    rendered = text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    pending = sorted(set(re.findall(r"\{\{([^}]+)\}\}", rendered)))
    if pending:
        raise MigrationError(
            f"placeholders sem valor em {template_name}: " + ", ".join(pending)
        )
    return rendered


def env_document_from_text(text: str) -> EnvDocument:
    lines = tuple(text.splitlines(keepends=True))
    values: dict[str, str] = {}
    for line in lines:
        match = ASSIGNMENT.match(line.rstrip("\r\n"))
        if match:
            values[match.group(1)] = match.group(2)
    return EnvDocument(lines=lines, values=values)


def build_project_migration(
    legacy_project: Path,
    *,
    server_env: Path = SERVER_ENV,
    template_root: Path = TEMPLATE_ROOT,
    projects_root: Path = PROJECTS_ROOT,
) -> ProjectMigration:
    legacy_project = legacy_project.resolve()
    if not legacy_project.is_dir():
        raise MigrationError("legacy_project deve ser uma pasta descompactada")
    legacy = EnvDocument.read(legacy_project / ".env")
    server = EnvDocument.read(server_env)

    project_id = clean_value(legacy.values.get("PROJECT_ID"))
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise MigrationError("PROJECT_ID legado ausente ou invalido")
    if legacy_project.name != project_id:
        raise MigrationError("nome da pasta legada diverge de PROJECT_ID")
    try:
        project_uuid = str(uuid.UUID(clean_value(legacy.values.get("PROJECT_UUID"))))
    except (ValueError, AttributeError) as exc:
        raise MigrationError("PROJECT_UUID legado ausente ou invalido") from exc

    required_project = {
        "ANON_KEY_PROJETO",
        "SERVICE_ROLE_KEY_PROJETO",
        "CONFIG_TOKEN_PROJETO",
        "JWT_SECRET_PROJETO",
    }
    unresolved = {
        key for key in required_project if is_placeholder(legacy.values.get(key))
    }
    if unresolved:
        return ProjectMigration(
            project_id=project_id,
            project_uuid=project_uuid,
            target=projects_root / project_id,
            files={},
            preserved=(),
            generated=(),
            obsolete=tuple(sorted(set(legacy.values) & OBSOLETE_KEYS)),
            unresolved=tuple(sorted(unresolved)),
            token_audits=(),
        )

    config_token = clean_value(legacy.values["CONFIG_TOKEN_PROJETO"])
    if not CONFIG_TOKEN_RE.fullmatch(config_token):
        raise MigrationError("CONFIG_TOKEN_PROJETO legado fora do formato hex de 64 caracteres")
    jwt_secret = clean_value(legacy.values["JWT_SECRET_PROJETO"])
    anon_key = clean_value(legacy.values["ANON_KEY_PROJETO"])
    service_key = clean_value(legacy.values["SERVICE_ROLE_KEY_PROJETO"])
    token_audits = (
        audit_jwt(anon_key, jwt_secret, "anon", project_uuid),
        audit_jwt(service_key, jwt_secret, "service_role", project_uuid),
    )

    public_base, nginx_server_host = normalize_public_base(
        server.values.get("SERVER_URL", ""), server.values.get("SERVER_PROTO", "")
    )
    project_public_url = f"{public_base}/{project_id}"
    project_root = clean_value(server.values.get("HOST_PROJECT_ROOT"))
    if not project_root:
        raise MigrationError("HOST_PROJECT_ROOT ausente no servidor/.env")

    target = projects_root / project_id
    target_values = {}
    if (target / ".env").is_file():
        target_values = EnvDocument.read(target / ".env").values
    access_key = clean_value(target_values.get("S3_PROTOCOL_ACCESS_KEY_ID"))
    access_secret = clean_value(target_values.get("S3_PROTOCOL_ACCESS_KEY_SECRET"))
    generated: set[str] = set()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", access_key):
        access_key = secrets.token_hex(16)
        generated.add("S3_PROTOCOL_ACCESS_KEY_ID")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", access_secret):
        access_secret = secrets.token_hex(32)
        generated.add("S3_PROTOCOL_ACCESS_KEY_SECRET")

    placeholders = {
        "anon_key": anon_key,
        "service_role_key": service_key,
        "project_id": project_id,
        "project_uuid": project_uuid,
        "config_token": config_token,
        "jwt_secret": jwt_secret,
        "server_url": nginx_server_host,
        "public_base_url": public_base,
        "project_public_url": project_public_url,
        "project_auth_external_url": f"{project_public_url}/auth/v1",
        "project_root": project_root,
        "s3_protocol_access_key_id": access_key,
        "s3_protocol_access_key_secret": access_secret,
    }

    env_template_path = template_root / ".envtemplate"
    env_rendered = replace_placeholders(
        env_template_path.read_text(encoding="utf-8"),
        placeholders,
        env_template_path.name,
    )
    env_document = env_document_from_text(env_rendered)
    preserved_overrides = {
        key: value
        for key, value in legacy.values.items()
        if key in PRESERVED_SETTINGS and key in env_document.values
    }
    preserved_overrides["SITE_URL"] = project_public_url + "/verify-success.html"
    preserved_overrides["ADDITIONAL_REDIRECT_URLS"] = (
        project_public_url + "/verify-success.html"
    )
    env_rendered = env_document.render(preserved_overrides)

    files = {".env": env_rendered}
    for output_name, template_name in TEMPLATE_FILES.items():
        template_path = template_root / template_name
        files[output_name] = replace_placeholders(
            template_path.read_text(encoding="utf-8"),
            placeholders,
            template_name,
        )
    nginx_output = f"nginx/nginx_{project_id}.conf"
    nginx_template = template_root / "nginxtemplate"
    files[nginx_output] = replace_placeholders(
        nginx_template.read_text(encoding="utf-8"),
        placeholders,
        nginx_template.name,
    )

    return ProjectMigration(
        project_id=project_id,
        project_uuid=project_uuid,
        target=target,
        files=files,
        preserved=tuple(sorted(set(preserved_overrides) | required_project | {"PROJECT_UUID"})),
        generated=tuple(sorted(generated)),
        obsolete=tuple(sorted(set(legacy.values) & OBSOLETE_KEYS)),
        unresolved=(),
        token_audits=token_audits,
    )


def write_project(result: ProjectMigration, *, refresh_config: bool = False) -> None:
    if result.unresolved:
        raise MigrationError("nao e possivel gravar um projeto com pendencias")
    if result.target.exists():
        if not refresh_config:
            raise MigrationError(f"destino ja existe: {result.target}")
        for relative, content in result.files.items():
            path = result.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=path.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.chmod(
                    0o600 if relative == ".env" else 0o644
                )
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        (result.target / "storage" / "stub" / "stub").mkdir(parents=True, exist_ok=True)
        return
    result.target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{result.project_id}.", dir=result.target.parent))
    try:
        for relative, content in result.files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600 if relative == ".env" else 0o644)
        (staging / "storage" / "stub" / "stub").mkdir(parents=True)
        os.replace(staging, result.target)
    finally:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()


def print_names(label: str, names: tuple[str, ...]) -> None:
    print(f"{label}: {', '.join(names) if names else 'nenhuma'}")


def print_report(result: ProjectMigration, *, wrote: bool) -> None:
    print(f"Migracao do projeto: {result.project_id}")
    print(f"  PROJECT_UUID: presente e valido")
    print_names("  configuracoes/chaves preservadas", result.preserved)
    print_names("  configuracoes geradas", result.generated)
    print_names("  chaves obsoletas descartadas", result.obsolete)
    print_names("  pendencias", result.unresolved)
    if result.token_audits:
        match = all(audit.issuer_matches_project_uuid for audit in result.token_audits)
        print(
            "  issuer dos JWTs: corresponde ao PROJECT_UUID"
            if match
            else "  issuer dos JWTs: legado; tokens preservados para compatibilidade"
        )
    print("  dados de banco/Storage: nao copiados nem inspecionados")
    print("  valores: omitidos intencionalmente")
    print("Saida: projeto gravado" if wrote else "Saida: dry-run, nenhum arquivo gravado")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Renderiza configuracao atual para um projeto legado descompactado."
    )
    parser.add_argument("legacy_project", type=Path)
    parser.add_argument("--server-env", type=Path, default=SERVER_ENV)
    parser.add_argument("--projects-root", type=Path, default=PROJECTS_ROOT)
    parser.add_argument("--write-project", action="store_true")
    parser.add_argument(
        "--refresh-config",
        action="store_true",
        help="atualiza somente arquivos gerenciados; preserva o diretorio Storage",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = build_project_migration(
            args.legacy_project,
            server_env=args.server_env,
            projects_root=args.projects_root,
        )
        if args.strict and result.unresolved:
            print_report(result, wrote=False)
            return 2
        if args.write_project:
            write_project(result, refresh_config=args.refresh_config)
        print_report(result, wrote=args.write_project)
        return 0
    except (MigrationError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
