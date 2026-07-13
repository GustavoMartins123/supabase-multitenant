"""ASGI composition root for the Projects API.

The core application remains in ``app.main``. Project-scoped compatibility routes
that are needed only by the shared Studio are registered here so they do not turn
the lifecycle module into another monolithic file.
"""

from __future__ import annotations

import pathlib
import re

from dotenv import dotenv_values
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.main import (
    app,
    ensure_project_admin_access,
    get_pool,
    get_project_row,
    resolve_authenticated_user,
)
from app.validation import validate_project_id

PROJECTS_ROOT = pathlib.Path("/docker/projects").resolve()
ACCESS_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SECRET_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _read_project_s3_vector_keys(project_name: str) -> tuple[str, str]:
    project_dir = (PROJECTS_ROOT / project_name).resolve()
    if project_dir.parent != PROJECTS_ROOT:
        raise HTTPException(400, "Invalid project path")

    env_path = project_dir / ".env"
    if not env_path.is_file():
        raise HTTPException(409, "Project environment file is missing")

    values = dotenv_values(env_path, interpolate=False)
    access_key = str(values.get("S3_PROTOCOL_ACCESS_KEY_ID") or "").strip()
    secret_key = str(values.get("S3_PROTOCOL_ACCESS_KEY_SECRET") or "").strip()

    if not ACCESS_KEY_RE.fullmatch(access_key):
        raise HTTPException(409, "Project S3 protocol access key is not configured")
    if not SECRET_KEY_RE.fullmatch(secret_key):
        raise HTTPException(409, "Project S3 protocol secret key is not configured")

    return access_key, secret_key


@app.get("/api/projects/{project_name}/storage/s3-keys")
async def get_project_s3_vector_keys(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Return the selected tenant's SigV4 pair to an authorized Studio admin.

    OpenResty rewrites the Studio's fixed ``/api/get-s3-keys`` endpoint to this
    project-scoped route. The global shared-token middleware authenticates the
    Studio-to-control-plane hop and the signed user token is checked here.
    """

    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message=(
                "Apenas admin do projeto ou administrador do sistema pode "
                "instalar o S3 Vectors Wrapper"
            ),
        )

    access_key, secret_key = _read_project_s3_vector_keys(project_name)
    return JSONResponse(
        content={"accessKey": access_key, "secretKey": secret_key},
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
