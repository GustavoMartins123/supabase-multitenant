"""Canonical project administration and one-time publication confirmation."""
from app.database import get_pool
from app.dependencies import resolve_authenticated_user, get_public_project_row, ensure_project_admin_access
from app.mailer_templates import build_router
from app.runtime_config import NGINX_HMAC_SECRET, USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
from app.project_env_secrets import PROJECTS_ROOT
from app.step_up_auth import consume_step_up_grant

async def authorize(project_ref, request, pool):
    actor=await resolve_authenticated_user(request,pool)
    async with pool.acquire() as conn:
        project=await get_public_project_row(conn,project_ref)
        await ensure_project_admin_access(conn,project_id=project["id"],auth_user=actor)
    return str(project["tenant_uuid"]),str(actor["db_user_id"]),PROJECTS_ROOT/project["name"]

async def confirm(project_ref,kind,payload,request,pool,tenant,actor_id):
    actor=await resolve_authenticated_user(request,pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project=await get_public_project_row(conn,project_ref)
            await ensure_project_admin_access(conn,project_id=project["id"],auth_user=actor)
            await consume_step_up_grant(conn,token=request.headers.get("X-Step-Up-Token"),
                secret=NGINX_HMAC_SECRET,max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
                auth_user=actor,action="publish_mailer_template",project_id=project["id"],project_ref=project_ref,
                resource_id=f"{kind}:{payload['version']}:{payload['draft_digest']}")

router=build_router(get_pool,authorize,confirm=confirm)
