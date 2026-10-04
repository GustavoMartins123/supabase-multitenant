"""ASGI composition root for the Projects API.

The core application remains in ``app.main``. Project-scoped compatibility routes
that are needed only by the shared Studio are registered here so they do not turn
the lifecycle module into another monolithic file.
"""

from __future__ import annotations

import pathlib
import re

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.internal_service_auth import InternalServiceAuthenticationMiddleware
from app.dependencies import get_public_project_row
from app.project_env_secrets import read_canonical_project_fields
from app.main import (
    app,
    ensure_project_admin_access,
    get_pool,
    resolve_authenticated_user,
)
from app.routers.jobs_api import router as jobs_router
from app.routers.client_configuration import router as client_configuration_router
from app.routers.project_insights import router as project_insights_router
from app.routers.project_keys import router as project_keys_router
from app.routers.project_lifecycle_ops import router as project_lifecycle_ops_router
from app.routers.project_members import router as project_members_router
from app.routers.project_rename import router as project_rename_router
from app.routers.projects import router as projects_router
from app.routers.restore_points import router as restore_points_router
from app.schemas import ProjectS3VectorKeysResponse
from app.validation import validate_project_ref

PROJECTS_ROOT = pathlib.Path("/docker/projects").resolve()
ACCESS_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SECRET_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _read_project_s3_vector_keys(
    project_name: str,
    *,
    tenant_uuid: object,
    public_ref: str,
) -> tuple[str, str]:
    project_dir = (PROJECTS_ROOT / project_name).resolve()
    if project_dir.parent != PROJECTS_ROOT:
        raise HTTPException(400, "Invalid project path")

    env_path = project_dir / ".env"
    if not env_path.is_file():
        raise HTTPException(409, "Project environment file is missing")

    try:
        values = read_canonical_project_fields(PROJECTS_ROOT, project_name, (
            "PROJECT_ID", "PROJECT_UUID", "PROJECT_PUBLIC_REF",
            "S3_PROTOCOL_ACCESS_KEY_ID", "S3_PROTOCOL_ACCESS_KEY_SECRET",
        ))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    if (not tenant_uuid or values["PROJECT_UUID"] != str(tenant_uuid)
            or values["PROJECT_ID"] != project_name or values["PROJECT_PUBLIC_REF"] != public_ref):
        raise HTTPException(
            409, "Project environment identity does not match this project"
        )
    access_key = values["S3_PROTOCOL_ACCESS_KEY_ID"]
    secret_key = values["S3_PROTOCOL_ACCESS_KEY_SECRET"]

    if not ACCESS_KEY_RE.fullmatch(access_key):
        raise HTTPException(409, "Project S3 protocol access key is not configured")
    if not SECRET_KEY_RE.fullmatch(secret_key):
        raise HTTPException(409, "Project S3 protocol secret key is not configured")

    return access_key, secret_key


@app.get("/api/projects/{project_ref}/storage/s3-keys", tags=["project-insights"], response_model=ProjectS3VectorKeysResponse)
async def get_project_s3_vector_keys(
    project_ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Return the selected tenant's SigV4 pair to an authorized Studio admin."""

    project_ref = validate_project_ref(project_ref)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, project_ref)
        await ensure_project_admin_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message=(
                "Apenas admin do projeto ou administrador do sistema pode "
                "instalar o S3 Vectors Wrapper"
            ),
        )

    access_key, secret_key = _read_project_s3_vector_keys(
        project["name"],
        tenant_uuid=project["tenant_uuid"],
        public_ref=project["public_ref"],
    )
    return JSONResponse(
        content={"accessKey": access_key, "secretKey": secret_key},
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


app.include_router(jobs_router)
app.include_router(client_configuration_router)
app.include_router(projects_router)
app.include_router(project_rename_router)
app.include_router(restore_points_router)
app.include_router(project_keys_router)
app.include_router(project_members_router)
app.include_router(project_lifecycle_ops_router)
app.include_router(project_insights_router)

# Registrado por ultimo para ser a camada mais externa: valida a identidade
# criptografica do caller antes das rotas e dependencias da aplicacao.
app.add_middleware(InternalServiceAuthenticationMiddleware)
