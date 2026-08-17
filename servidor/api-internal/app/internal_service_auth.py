"""Autenticacao HMAC de chamadas Studio Gateway -> Projects API.

A identidade do servico e vinculada ao metodo, request-target, timestamp,
nonce e hash do body. A identidade/autorizacao do usuario permanece uma
camada separada por X-User-Token nas rotas que representam acoes humanas.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.internal_hmac import (
    INTERNAL_HMAC_VERSION,
    request_target_from_scope,
    verify_internal_hmac_signature,
)
from app.runtime_config import (
    INTERNAL_HMAC_MAX_SKEW_SECONDS,
    STUDIO_GATEWAY_HMAC_SECRET,
)

_NONCE_RE = re.compile(r"^[0-9a-fA-F]{32,128}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_nonce_lock = asyncio.Lock()
_nonce_expirations: OrderedDict[str, float] = OrderedDict()
_MAX_TRACKED_NONCES = 20_000


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _claim_nonce(service: str, nonce: str, *, now: float) -> bool:
    """Registra nonce por toda a janela na qual o timestamp seria aceito."""
    ttl = INTERNAL_HMAC_MAX_SKEW_SECONDS * 2 + 5
    cache_key = f"{service}:{nonce.lower()}"
    async with _nonce_lock:
        while _nonce_expirations:
            first_key, expires_at = next(iter(_nonce_expirations.items()))
            if expires_at > now and len(_nonce_expirations) <= _MAX_TRACKED_NONCES:
                break
            _nonce_expirations.pop(first_key, None)

        current_expiry = _nonce_expirations.get(cache_key)
        if current_expiry is not None and current_expiry > now:
            return False

        _nonce_expirations[cache_key] = now + ttl
        _nonce_expirations.move_to_end(cache_key)
        while len(_nonce_expirations) > _MAX_TRACKED_NONCES:
            _nonce_expirations.popitem(last=False)
        return True


async def authenticate_internal_request(request: Request) -> JSONResponse | None:
    """Exige internal-hmac-v1 em toda a Projects API, exceto healthz."""
    if request.url.path == "/healthz":
        return None

    headers = request.headers
    version = headers.get("X-Internal-Version") or ""
    service = headers.get("X-Internal-Service") or ""
    raw_timestamp = headers.get("X-Internal-Timestamp") or ""
    nonce = headers.get("X-Internal-Nonce") or ""
    signature = headers.get("X-Internal-Signature") or ""

    if version != INTERNAL_HMAC_VERSION:
        return _json_error(401, "Unauthorized: Missing or unsupported internal HMAC version")
    if service != "studio-gateway":
        return _json_error(403, "Forbidden: Internal service is not allowed")
    if not _NONCE_RE.fullmatch(nonce):
        return _json_error(401, "Unauthorized: Invalid internal HMAC nonce")
    if not _SIGNATURE_RE.fullmatch(signature):
        return _json_error(401, "Unauthorized: Invalid internal HMAC signature")

    try:
        timestamp = int(raw_timestamp)
    except ValueError:
        return _json_error(401, "Unauthorized: Invalid internal HMAC timestamp")

    now = int(time.time())
    if abs(now - timestamp) > INTERNAL_HMAC_MAX_SKEW_SECONDS:
        return _json_error(401, "Unauthorized: Expired internal HMAC signature")

    body = await request.body()
    target = request_target_from_scope(request.scope)
    if not verify_internal_hmac_signature(
        STUDIO_GATEWAY_HMAC_SECRET,
        service=service,
        method=request.method,
        target=target,
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        version=version,
    ):
        return _json_error(403, "Forbidden: Invalid internal HMAC signature")

    if not await _claim_nonce(service, nonce, now=float(now)):
        return _json_error(401, "Unauthorized: Replayed internal HMAC signature")

    request.state.internal_service = service
    return None


class InternalServiceAuthenticationMiddleware(BaseHTTPMiddleware):
    """Camada externa que valida a identidade criptografica do caller."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        auth_error = await authenticate_internal_request(request)
        if auth_error is not None:
            return auth_error
        return await call_next(request)
