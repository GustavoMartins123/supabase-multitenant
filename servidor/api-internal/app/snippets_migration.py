"""Cliente da API interna de migracao de snippets do OpenResty (Studio).

Quando um projeto e renomeado, as pastas de snippets SQL do usuario (guardadas
pelo Studio em SNIPPETS_MANAGEMENT_FOLDER, nomeadas "<user_id>__<slug>") precisam
migrar para o novo slug. Esse trabalho roda na maquina do Studio; o projects-api
apenas dispara via HTTP, reusando o mesmo caminho autenticado do cache de
service key (STUDIO_CACHE_INVALIDATION_URL + X-Shared-Token).
"""

import asyncio
from typing import Any

import httpx

from app.runtime_config import (
    NGINX_SHARED_TOKEN,
    STUDIO_CACHE_INVALIDATION_URL,
    STUDIO_CACHE_INVALIDATION_VERIFY_TLS,
)


async def rename_project_snippets(old_name: str, new_name: str) -> dict[str, Any]:
    url = f"{STUDIO_CACHE_INVALIDATION_URL}/internal/snippets/rename"
    headers = {
        "X-Shared-Token": NGINX_SHARED_TOKEN,
        "X-Internal-Service": "projects-api",
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                verify=STUDIO_CACHE_INVALIDATION_VERIFY_TLS,
            ) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={"old_name": old_name, "new_name": new_name},
                )
            response.raise_for_status()
            return response.json() if response.content else {}
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.2 * attempt)
    raise RuntimeError(
        f"snippet rename migration failed after 3 attempts: {last_error}"
    )
