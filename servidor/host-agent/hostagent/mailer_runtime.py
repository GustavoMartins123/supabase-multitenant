"""Materialize mailer credentials and public assets on the physical host."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import tempfile
import uuid

from .envfile import read_canonical_env_value, upsert_env_value
from .security import ensure_inside

MAIL_FILES = {
    "confirmation.html",
    "invite.html",
    "magiclink.html",
    "recovery.html",
    "email_change.html",
    "email_change_current.html",
    "reauthentication.html",
}
BUILTIN_ROUTES = {"verify-success.html", "verify-success.js"}


def _confined(root: Path, path: Path) -> Path:
    current = root
    for part in path.relative_to(root).parts:
        if part == "..":
            raise RuntimeError("Caminho publico invalido")
        current /= part
        if current.is_symlink():
            raise RuntimeError("Arquivos do mailer nao podem atravessar links")
    return ensure_inside(root, path)


def ensure_mailer_key(root: Path, project_dir: Path) -> None:
    env = _confined(project_dir, project_dir / ".env")
    tenant = str(uuid.UUID(read_canonical_env_value(env, "PROJECT_UUID") or ""))
    secret_path = _confined(root, root / "secrets/mailer/URL_SECRET")
    if not secret_path.is_file():
        raise RuntimeError(
            "Credencial do mailer ausente; prepare configure_mailer_runtime.py antes de recriar o projeto"
        )
    secret = secret_path.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise RuntimeError("Credencial do mailer invalida")
    expected = hmac.new(
        secret.encode(), ("mailer-url-v1:" + tenant).encode(), hashlib.sha256
    ).hexdigest()
    current = read_canonical_env_value(env, "MAILER_TEMPLATE_KEY")
    if current is not None and not re.fullmatch(r"[0-9a-f]{64}", current):
        raise RuntimeError("MAILER_TEMPLATE_KEY invalida no projeto")
    if current != expected:
        upsert_env_value(env, "MAILER_TEMPLATE_KEY", expected)


def _files(root: Path, directory: Path) -> dict[str, bytes]:
    _confined(root, directory)
    if not directory.is_dir():
        raise RuntimeError("Arquivos publicos do mailer ausentes: " + str(directory))
    files = {}
    total = 0
    for base, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            _confined(root, Path(base) / name)
        for name in names:
            path = Path(base) / name
            if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise RuntimeError("Arquivo publico invalido ou excessivo")
            data = path.read_bytes()
            total += len(data)
            if total > 64 * 1024 * 1024 or len(files) >= 2000:
                raise RuntimeError(
                    "Arquivos publicos excedem o limite de materializacao"
                )
            files[path.relative_to(directory).as_posix()] = data
    return files


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mailer-public-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_mailer_files(root: Path, scripts_dir: Path, project_dir: Path) -> str:
    compose = _confined(project_dir, project_dir / "docker-compose.yml")
    if compose.exists():
        text = compose.read_text()
        urls = re.findall(r"^\s+GOTRUE_MAILER_TEMPLATES_[A-Z_]+:\s*(.+)$", text, re.M)
        static_mount = re.search(
            r"""(?::|target:\s*)["']?/usr/share/nginx/html(?:[/'"\s:]|$)""", text
        )
        if static_mount or any(
            "template-service:18020/mailer/" not in url for url in urls
        ):
            raise RuntimeError(
                "Migre os templates legados com migrate_mailer_templates.py antes de regenerar o projeto"
            )
    public = _confined(project_dir, project_dir / "nginx/public")
    current = _files(project_dir, public) if public.exists() else {}
    defaults = _files(scripts_dir, scripts_dir / "public")
    desired = {**defaults, **current}
    dockerfile = _confined(project_dir, project_dir / "Dockerfile")
    if (
        dockerfile.exists()
        and "# BEGIN IDR MAILER STATIC ASSETS" in dockerfile.read_text()
    ):
        # This COPY was last in the migrated image: it is the effective source,
        # including project-specific recovery pages, JavaScript and images.
        desired.update(_files(project_dir, project_dir / "nginx/mailer-static-assets"))
    for name in desired:
        _confined(project_dir, public / name)
    ensure_mailer_key(root, project_dir)
    for name, data in desired.items():
        target = _confined(project_dir, public / name)
        if not target.exists() or target.read_bytes() != data:
            _write(target, data)
    for name in (".dockerignore", "Dockerfile.dockerignore"):
        ignore = _confined(project_dir, project_dir / name)
        if name != ".dockerignore" and not ignore.exists():
            continue
        text = (
            ignore.read_text()
            if ignore.exists()
            else (scripts_dir / ".dockerignore").read_text()
        )
        for rule in ("!nginx/", "!nginx/public/", "!nginx/public/**"):
            if rule not in text.splitlines():
                text = text.rstrip() + "\n" + rule + "\n"
        if not ignore.exists() or ignore.read_text() != text:
            _write(ignore, text.encode())
    locations = []
    for name in sorted(set(desired) - MAIL_FILES - BUILTIN_ROUTES):
        if not re.fullmatch(
            r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.(?:html|js|css|png|jpg|jpeg|gif|svg|webp|ico|woff2?)",
            name,
        ):
            continue
        locations.append(
            "        location = /" + name + " {\n"
            "            set $opaque_target_service auth;\n"
            "            root /usr/share/nginx/html;\n"
            "            try_files $uri =404;\n"
            "            add_header X-Content-Type-Options nosniff always;\n"
            "        }\n"
        )
    return "\n".join(locations)
