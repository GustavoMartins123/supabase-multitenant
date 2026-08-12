"""Renderizacao dos arquivos gerados por template de um projeto.

Portado da Projects API (antiga ``_sync_project_nginx_generated_files``)
para o host-agent, que agora e o unico componente que materializa nginx,
Dockerfile e docker-compose do projeto durante o recreate.
"""

from __future__ import annotations

import re
from pathlib import Path

from .envfile import read_canonical_env_value
from .security import ensure_inside


def _normalize_public_base_url(url: str, proto: str | None = None) -> str:
    normalized = url.rstrip("/")
    if not re.match(r"^https?://", normalized):
        normalized_proto = (proto or "").strip().lower()
        if normalized_proto not in {"http", "https"}:
            raise RuntimeError(
                "SERVER_PROTO deve ser http ou https quando SERVER_URL nao inclui esquema"
            )
        normalized = f"{normalized_proto}://{normalized}"
    return normalized


def _render_template(template_path: Path, output_path: Path, replacements: dict[str, str]) -> None:
    content = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    unresolved = sorted(set(re.findall(r"\{\{[a-z0-9_]+\}\}", content)))
    if unresolved:
        raise RuntimeError(
            f"Template {template_path.name} possui placeholders sem valor: "
            + ", ".join(unresolved)
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def _build_replacements(root: Path, project_dir: Path, project: str) -> dict[str, str]:
    root_env_path = root / ".env"
    server_url = read_canonical_env_value(root_env_path, "SERVER_URL")
    server_proto = read_canonical_env_value(root_env_path, "SERVER_PROTO")
    host_project_root = read_canonical_env_value(
        root_env_path, "HOST_PROJECT_ROOT"
    )
    if not server_url:
        raise RuntimeError("SERVER_URL ausente no .env raiz")
    if not host_project_root:
        raise RuntimeError("HOST_PROJECT_ROOT ausente no .env raiz")

    required_project_keys = (
        "ANON_KEY_PROJETO",
        "SERVICE_ROLE_KEY_PROJETO",
        "CONFIG_TOKEN_PROJETO",
        "JWT_SECRET_PROJETO",
        "API_GATEWAY_TOKEN_PROJETO",
        "PROJECT_UUID",
    )
    project_env_path = project_dir / ".env"
    raw_project_env = {
        key: read_canonical_env_value(project_env_path, key)
        for key in required_project_keys
    }
    missing = [key for key, value in raw_project_env.items() if not value]
    if missing:
        raise RuntimeError(
            f".env do projeto '{project}' sem chaves obrigatorias: {', '.join(missing)}"
        )
    project_env = {
        key: value
        for key, value in raw_project_env.items()
        if value is not None
    }
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        project_env["PROJECT_UUID"],
    ):
        raise RuntimeError("PROJECT_UUID invalido no .env do projeto")
    if not re.fullmatch(r"[a-f0-9]{64}", project_env["CONFIG_TOKEN_PROJETO"]):
        raise RuntimeError("CONFIG_TOKEN_PROJETO invalido no .env do projeto")
    if not re.fullmatch(
        r"[a-f0-9]{64}", project_env["API_GATEWAY_TOKEN_PROJETO"]
    ):
        raise RuntimeError("API_GATEWAY_TOKEN_PROJETO invalido no .env do projeto")
    if not re.fullmatch(
        r"[A-Za-z0-9_-]{43}=?", project_env["JWT_SECRET_PROJETO"]
    ):
        raise RuntimeError("JWT_SECRET_PROJETO invalido no .env do projeto")
    jwt_re = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
    if not jwt_re.fullmatch(project_env["ANON_KEY_PROJETO"]):
        raise RuntimeError("ANON_KEY_PROJETO invalida no .env do projeto")
    if not jwt_re.fullmatch(project_env["SERVICE_ROLE_KEY_PROJETO"]):
        raise RuntimeError("SERVICE_ROLE_KEY_PROJETO invalida no .env do projeto")

    public_base_url = _normalize_public_base_url(server_url, server_proto)
    project_public_url = f"{public_base_url}/{project}"

    return {
        "anon_key": project_env["ANON_KEY_PROJETO"],
        "service_role_key": project_env["SERVICE_ROLE_KEY_PROJETO"],
        "project_id": project,
        "project_uuid": project_env["PROJECT_UUID"],
        "config_token": project_env["CONFIG_TOKEN_PROJETO"],
        "jwt_secret": project_env["JWT_SECRET_PROJETO"],
        "api_gateway_token": project_env["API_GATEWAY_TOKEN_PROJETO"],
        "server_url": server_url,
        "public_base_url": public_base_url,
        "project_public_url": project_public_url,
        "project_auth_external_url": f"{project_public_url}/auth/v1",
        "project_root": host_project_root,
    }


def sync_project_generated_files(
    *,
    root: Path,
    scripts_dir: Path,
    project_dir: Path,
    project: str,
) -> None:
    """Regenera nginx.conf, Dockerfile e docker-compose.yml do projeto."""
    replacements = _build_replacements(root, project_dir, project)

    nginx_config_path = ensure_inside(
        project_dir, project_dir / "nginx" / f"nginx_{project}.conf"
    )
    _render_template(scripts_dir / "nginxtemplate", nginx_config_path, replacements)
    nginx_config_path.chmod(0o600)

    _render_template(
        scripts_dir / "Dockerfile",
        ensure_inside(project_dir, project_dir / "Dockerfile"),
        replacements,
    )
    _render_template(
        scripts_dir / "dockercomposetemplate",
        ensure_inside(project_dir, project_dir / "docker-compose.yml"),
        replacements,
    )
