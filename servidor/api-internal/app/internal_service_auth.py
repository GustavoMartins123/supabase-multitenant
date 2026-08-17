"""Autenticacao de chamadas internas entre o Studio Gateway e Projects API.

O HMAC de servico autentica o caller e vincula a assinatura ao request real.
A autenticacao/autorizacao do usuario continua sendo feita separadamente pelo
X-User-Token nas rotas que representam uma acao de usuario.
"""

from __future__ import annotations

import asyncio
import hmac
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
    INTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN,
    INTERNAL_HMAC_MAX_SKEW_SECONDS,
    NGINX_SHARED_TOKEN,
    STUDIO_GATEWAY_HMAC_SECRET,
)


_HMAC_HEADER_NAMES = (
    "X-Internal-Version",
    "X-Internal-Service",
    "X-Internal-Timestamp",
    "X-Internal-Nonce",
    "X-Internal-Signature",
)
_NONCE_RE = re.compile(r"^[0-9a-fA-F]{32,128}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_nonce_lock = asyncio.Lock()
_nonce_expirations: OrderedDict[str, float] = OrderedDict()
_MAX_TRACKED_NONCES = 20_000


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _replace_scope_header(scope: dict, name: bytes, value: bytes) -> None:
    lowered_name = name.lower()
    headers = [
        (header_name, header_value)
        for header_name, header_value in scope.get("headers", [])
        if header_name.lower() != lowered_name
    ]
    headers.append((lowered_name, value))
    scope["headers"] = headers


async def _claim_nonce(service: str, nonce: str, *, now: float) -> bool:
    """Registra nonce por toda a janela na qual o timestamp ainda seria aceito."""

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
    """Valida identidade de servico antes de qualquer rota da Projects API.

    Durante o rollout, chamadas sem nenhum header HMAC podem usar o token
    legado quando INTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN estiver habilitado.
    Se qualquer header HMAC estiver presente, a assinatura deve ser valida;
    nunca fazemos downgrade silencioso para o token legado.
    """

    if request.url.path == "/healthz":
        return None

    headers = request.headers
    has_hmac_headers = any(headers.get(name) for name in _HMAC_HEADER_NAMES)

    if not has_hmac_headers:
        if INTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN:
            legacy_token = headers.get("X-Shared-Token") or ""
            if legacy_token and NGINX_SHARED_TOKEN and hmac.compare_digest(
                legacy_token, NGINX_SHARED_TOKEN
            ):
                request.state.internal_service = "legacy-shared-token"
                print(
                    "[internal-auth] legacy X-Shared-Token accepted for "
                    f"{request.method} {request.url.path}"
                )
                return None

        return _json_error(401, "Unauthorized: Missing internal HMAC signature")

    version = headers.get("X-Internal-Version") or ""
    service = headers.get("X-Internal-Service") or ""
    raw_timestamp = headers.get("X-Internal-Timestamp") or ""
    nonce = headers.get("X-Internal-Nonce") or ""
    signature = headers.get("X-Internal-Signature") or ""

    if version != INTERNAL_HMAC_VERSION:
        return _json_error(401, "Unauthorized: Unsupported internal HMAC version")
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
    """Outer middleware do composition root da Projects API.

    O middleware legado em ``app.main`` continua existindo durante o rollout.
    Depois que o HMAC e validado, este bridge substitui qualquer X-Shared-Token
    recebido pelo valor interno correto, de modo que o bearer legado nunca
    precise ser enviado por callers ja migrados.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        auth_error = await authenticate_internal_request(request)
        if auth_error is not None:
            return auth_error

        if getattr(request.state, "internal_service", None) == "studio-gateway":
            _replace_scope_header(
                request.scope,
                b"x-shared-token",
                NGINX_SHARED_TOKEN.encode("utf-8"),
            )

        return await call_next(request)
