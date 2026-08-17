"""Cliente da API interna de migracao de snippets do OpenResty (Studio).

Quando um projeto e renomeado, as pastas de snippets SQL do usuario (guardadas
pelo Studio em SNIPPETS_MANAGEMENT_FOLDER, nomeadas "<user_id>__<slug>") precisam
migrar para o novo slug. Esse trabalho roda na maquina do Studio; o projects-api
dispara a chamada com identidade HMAC propria do servico.
"""

import asyncio
import json
from typing import Any

import httpx

from app.internal_hmac import build_internal_hmac_headers
from app.runtime_config import (
    PROJECTS_API_HMAC_SECRET,
    STUDIO_CACHE_INVALIDATION_URL,
    build_studio_cache_ssl_context,
)


async def rename_project_snippets(old_name: str, new_name: str) -> dict[str, Any]:
    url = f"{STUDIO_CACHE_INVALIDATION_URL}/internal/snippets/rename"
    body = json.dumps(
        {"old_name": old_name, "new_name": new_name},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        **build_internal_hmac_headers(
            PROJECTS_API_HMAC_SECRET,
            "POST",
            url,
            body,
            service="projects-api",
        ),
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                verify=build_studio_cache_ssl_context(),
            ) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    content=body,
                )
            response.raise_for_status()
            return response.json() if response.content else {}
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.2 * attempt)
                headers.update(
                    build_internal_hmac_headers(
                        PROJECTS_API_HMAC_SECRET,
                        "POST",
                        url,
                        body,
                        service="projects-api",
                    )
                )
    raise RuntimeError(
        f"snippet rename migration failed after 3 attempts: {last_error}"
    )
