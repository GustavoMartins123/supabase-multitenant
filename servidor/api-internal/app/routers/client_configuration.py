from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.client_configuration import read_client_configuration
from app.database import get_pool
from app.opaque_keys import APPLICATION_REF_PATTERN
from app.project_env_secrets import PROJECTS_ROOT
from app.project_secrets import ProjectSecretError

router = APIRouter(tags=['client-configuration'])
NO_STORE_HEADERS = {'Cache-Control': 'no-store, max-age=0', 'Pragma': 'no-cache'}


class ClientConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supabase_url: str
    publishable_key: str
    key_id: str
    expires_at: str | None


@router.get('/config/{application_ref}', response_model=ClientConfigurationResponse)
async def get_client_configuration(application_ref: str, request: Request, pool=Depends(get_pool)):
    if not APPLICATION_REF_PATTERN.fullmatch(application_ref) or request.url.query:
        raise HTTPException(400, 'Invalid application configuration reference')
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                payload = await read_client_configuration(conn, application_ref, PROJECTS_ROOT)
    except HTTPException:
        raise
    except (OSError, ValueError, RuntimeError, ProjectSecretError, asyncpg.PostgresError) as exc:
        raise HTTPException(503, 'Application configuration could not be verified') from exc
    return JSONResponse(payload, headers=NO_STORE_HEADERS)
