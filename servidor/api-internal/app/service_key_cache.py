"""Cliente da API interna de cache de service keys do OpenResty."""

import asyncio

import httpx

from app.runtime_config import (
    NGINX_SHARED_TOKEN,
    STUDIO_CACHE_INVALIDATION_URL,
    build_studio_cache_ssl_context,
)


async def invalidate_service_key_cache(project_ref: str, version: int) -> None:
    url = f"{STUDIO_CACHE_INVALIDATION_URL}/internal/cache/service-key/{project_ref}"
    headers = {
        "X-Shared-Token": NGINX_SHARED_TOKEN,
        "X-Internal-Service": "projects-api",
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(
                timeout=3.0,
                verify=build_studio_cache_ssl_context(),
            ) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={"project_key_version": version},
                )
            response.raise_for_status()
            return
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.2 * attempt)
    raise RuntimeError(
        f"service key cache invalidation failed after 3 attempts: {last_error}"
    )
