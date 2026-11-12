"""Authenticated Studio adapter for the isolated mail template service."""

from __future__ import annotations

import hashlib
import base64
import secrets
import time
import datetime as dt
import re
from urllib.parse import urlsplit
import hmac
import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

MAX_REQUEST = 8 * 1024 * 1024
KINDS = {
    "confirmation",
    "invite",
    "magic_link",
    "recovery",
    "email_change",
    "reauthentication",
}


async def initialize(pool):
    async with pool.acquire() as conn:
        await conn.execute(
            Path(__file__).with_name("mailer_templates_schema.sql").read_text()
        )
        await conn.execute(
            Path(__file__).with_name("mailer_templates_security.sql").read_text()
        )


async def copy_project(conn, source_id, destination_id, actor):
    # Cloning does not transfer publication authority to the destination project.
    await conn.execute(
        """INSERT INTO mailer_template(project_id,kind,version,updated_by,draft_body,draft_exists,policy_version)
           SELECT $2,kind,1,$3,body,true,1 FROM mailer_template WHERE project_id=$1 AND body IS NOT NULL""",
        source_id,
        destination_id,
        str(actor),
    )
    await conn.execute(
        """INSERT INTO mailer_template_version(project_id,kind,body,version,updated_by,action)
           SELECT project_id,kind,draft_body,version,updated_by,'copy' FROM mailer_template WHERE project_id=$1""",
        destination_id,
    )


async def authorize_idr(project_ref, request, pool):
    from app.main import validate_project_id

    project_ref = validate_project_id(project_ref)
    user = request.headers.get("Remote-Email", "")
    groups = {
        g.strip().lower() for g in request.headers.get("Remote-Groups", "").split(",")
    }
    if not user:
        raise HTTPException(401, "Autenticação necessária")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT p.id, p.tenant_uuid,
               (SELECT role FROM project_members WHERE project_id=p.id AND user_id=$2) AS role
               FROM projects p WHERE p.name=$1""",
            project_ref,
            user,
        )
    if row is None:
        raise HTTPException(404, "Projeto não encontrado")
    if row["role"] != "admin" and "admin" not in groups:
        raise HTTPException(403, "Acesso negado: administrador do projeto necessário")
    if row["tenant_uuid"] is None:
        raise HTTPException(409, "A identidade do projeto ainda não foi provisionada")
    project_dir = Path("/docker/projects") / project_ref
    return str(row["tenant_uuid"]), user, project_dir


def project_origins(directory):
    from dotenv import dotenv_values

    path = Path(directory) / ".env"
    if not path.is_file() or path.is_symlink():
        raise HTTPException(503, "Configuração de destinos do projeto indisponível")
    values = dotenv_values(path, interpolate=False)
    result = set()
    for key in ("SITE_URL", "API_EXTERNAL_URL"):
        raw = values.get(key) or ""
        parsed = urlsplit(raw)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(c in raw for c in "\\\r\n\t ")
        ):
            raise HTTPException(503, "Destinos do projeto devem usar HTTPS explícito")
        result.add("https://" + parsed.netloc.lower())
    # Extra image/document origins are operator-managed, never accepted from the
    # Studio request. No wildcards or user-controlled RedirectTo values.
    for raw in (values.get("MAILER_TEMPLATE_ALLOWED_ORIGINS") or "").split(","):
        if raw.strip():
            result.add(raw.strip())
    if len(result) > 16:
        raise HTTPException(503, "Muitas origens de templates")
    return sorted(result)


def credential(name):
    try:
        key_file = "MAILER_TEMPLATE_" + name + "_FILE"
        return (
            Path(os.getenv(key_file, "/run/secrets/mailer/" + name)).read_text().strip()
        )
    except OSError:
        raise HTTPException(503, "Credencial própria do mailer indisponível") from None


def publication_proof(secret, tenant, kind, actor, payload):
    claims = {
        "tenant": tenant,
        "kind": kind,
        "actor": actor,
        "version": payload["version"],
        "digest": payload["draft_digest"],
        "exp": int(time.time()) + 60,
        "jti": secrets.token_hex(16),
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    return (
        encoded
        + "."
        + hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    )


async def confirm_idr(project_ref, kind, payload, request, pool, tenant, actor):
    from app.studio_identity import credentials
    from app.mailer_step_up import consume

    key, _ = credentials()
    identity = request.state.studio_identity
    async with pool.acquire() as conn:
        async with conn.transaction():
            await consume(
                conn,
                request.headers.get("X-Step-Up-Token", ""),
                key,
                actor,
                identity["sid"],
                project_ref,
                kind,
                payload,
            )


def build_router(get_pool, authorize, confirm=confirm_idr):
    router = APIRouter(tags=["mailer-templates"])
    base_url = os.getenv("MAILER_TEMPLATE_URL", "http://template-service:18020").rstrip(
        "/"
    )

    async def forward(project_ref, request, pool, kind=None, operation=None):
        tenant, actor, directory = await authorize(project_ref, request, pool)
        approved = project_origins(directory)
        key = credential("ADMIN_KEY")
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise HTTPException(
                503, "Credencial própria do serviço de templates não configurada"
            )
        if kind is not None and kind not in KINDS:
            raise HTTPException(404, "Tipo de template desconhecido")
        raw = bytearray()
        if request.method in {"POST", "PUT", "DELETE"}:
            if (
                request.headers.get("content-type", "").split(";")[0].lower()
                != "application/json"
            ):
                raise HTTPException(415, "Content-Type application/json obrigatório")
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_REQUEST:
                    raise HTTPException(413, "Upload excede o limite")
            try:
                data = json.loads(raw.decode("utf-8", errors="strict"))
                if not isinstance(data, dict):
                    raise ValueError()
            except (UnicodeError, ValueError):
                raise HTTPException(422, "Objeto JSON UTF-8 obrigatório") from None
        publication = ""
        if operation == "publish":
            if (
                set(data) != {"version", "draft_digest"}
                or type(data.get("version")) is not int
                or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("draft_digest", "")))
            ):
                raise HTTPException(
                    422, "Identifique o rascunho salvo antes de publicar"
                )
            publish_key = credential("PUBLISH_KEY")
            if not re.fullmatch(r"[0-9a-f]{64}", publish_key) or publish_key == key:
                raise HTTPException(
                    503, "Credencial própria de publicação não configurada"
                )
            await confirm(project_ref, kind, data, request, pool, tenant, actor)
            publication = publication_proof(publish_key, tenant, kind, actor, data)
        path = f"/internal/projects/{tenant}/mailer-templates"
        if kind is not None:
            path += "/" + kind
        if operation:
            path += "/" + operation
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.request(
                    request.method,
                    base_url + path,
                    content=bytes(raw) if raw else None,
                    headers={
                        "X-Mailer-Admin": key,
                        "X-Mailer-Actor": actor,
                        "X-Mailer-Origins": json.dumps(approved),
                        "X-Mailer-Publication": publication,
                        "Content-Type": "application/json",
                    },
                )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "Serviço de templates indisponível") from None
        if response.status_code >= 500:
            raise HTTPException(
                503,
                "Serviço de templates indisponível; recarregue antes de tentar novamente",
            )
        return JSONResponse(
            data,
            status_code=response.status_code,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/api/projects/{project_ref}/mailer-templates")
    async def list_templates(
        project_ref: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool)

    @router.put("/api/projects/{project_ref}/mailer-templates/{kind}")
    async def save_template(
        project_ref: str, kind: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool, kind)

    @router.delete("/api/projects/{project_ref}/mailer-templates/{kind}")
    async def delete_template(
        project_ref: str, kind: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool, kind)

    @router.get("/api/projects/{project_ref}/mailer-templates/{kind}/history")
    async def history(
        project_ref: str, kind: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool, kind, "history")

    @router.post("/api/projects/{project_ref}/mailer-templates/{kind}/preview")
    async def preview(
        project_ref: str, kind: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool, kind, "preview")

    @router.get("/api/projects/{project_ref}/mailer-templates/{kind}/history/{version}")
    async def history_version(
        project_ref: str,
        kind: str,
        version: int,
        request: Request,
        pool=Depends(get_pool),
    ):
        if not 1 <= version <= 2147483647:
            raise HTTPException(404, "Versão não encontrada")
        return await forward(
            project_ref, request, pool, kind, "history/" + str(version)
        )

    @router.post("/api/projects/{project_ref}/mailer-templates/{kind}/publish")
    async def publish(
        project_ref: str, kind: str, request: Request, pool=Depends(get_pool)
    ):
        return await forward(project_ref, request, pool, kind, "publish")

    return router
