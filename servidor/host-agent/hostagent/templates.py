"""Renderizacao dos arquivos gerados por template de um projeto.

Portado da Projects API (antiga ``_sync_project_nginx_generated_files``)
para o host-agent, que agora e o unico componente que materializa nginx,
Dockerfile e docker-compose do projeto durante o recreate.
"""

from __future__ import annotations

import re
from pathlib import Path

from .envfile import read_env_file
from .security import ensure_inside


def _normalize_public_base_url(url: str, proto: str | None = None) -> str:
    normalized = url.rstrip("/")
    if not re.match(r"^https?://", normalized):
        normalized_proto = (proto or "").strip().lower()
        if normalized_proto in {"http", "https"}:
            normalized = f"{normalized_proto}://{normalized}"
        else:
            normalized = f"https://{normalized}"
    return normalized


def _render_template(template_path: Path, output_path: Path, replacements: dict[str, str]) -> None:
    content = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def _build_replacements(root: Path, project_dir: Path, project: str) -> dict[str, str]:
    root_env = read_env_file(root / ".env")
    if not root_env:
        raise RuntimeError("Arquivo .env raiz nao encontrado")
    project_env = read_env_file(project_dir / ".env")
    if not project_env:
        raise RuntimeError(f"Arquivo .env nao encontrado para o projeto '{project}'")

    server_url = root_env.get("SERVER_URL", "").strip()
    server_proto = root_env.get("SERVER_PROTO", "").strip()
    host_project_root = root_env.get("HOST_PROJECT_ROOT", "").strip()
    if not server_url:
        raise RuntimeError("SERVER_URL ausente no .env raiz")
    if not host_project_root:
        raise RuntimeError("HOST_PROJECT_ROOT ausente no .env raiz")

    required_project_keys = (
        "ANON_KEY_PROJETO",
        "SERVICE_ROLE_KEY_PROJETO",
        "CONFIG_TOKEN_PROJETO",
        "JWT_SECRET_PROJETO",
    )
    missing = [key for key in required_project_keys if not project_env.get(key, "").strip()]
    if missing:
        raise RuntimeError(
            f".env do projeto '{project}' sem chaves obrigatorias: {', '.join(missing)}"
        )

    public_base_url = _normalize_public_base_url(server_url, server_proto)
    project_public_url = f"{public_base_url}/{project}"

    return {
        "anon_key": project_env["ANON_KEY_PROJETO"],
        "service_role_key": project_env["SERVICE_ROLE_KEY_PROJETO"],
        "project_id": project,
        "project_uuid": project_env.get("PROJECT_UUID") or project,
        "config_token": project_env["CONFIG_TOKEN_PROJETO"],
        "jwt_secret": project_env["JWT_SECRET_PROJETO"],
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
