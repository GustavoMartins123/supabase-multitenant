from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse


INTERNAL_HMAC_VERSION = "internal-hmac-v1"
LEGACY_PUSH_HMAC_VERSION = "push-v2"


def request_target_from_url(url: str) -> str:
    parsed = urlparse(url)
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return request_target


def request_target_from_scope(scope: dict) -> str:
    """Retorna o request-target HTTP preservando path/query recebidos pelo ASGI."""

    raw_path = scope.get("raw_path")
    if isinstance(raw_path, bytes) and raw_path:
        path = raw_path.decode("latin-1")
    else:
        path = str(scope.get("path") or "/")

    query_string = scope.get("query_string") or b""
    if isinstance(query_string, bytes):
        query = query_string.decode("latin-1")
    else:
        query = str(query_string)
    return f"{path}?{query}" if query else path


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_internal_request(
    *,
    service: str,
    method: str,
    target: str,
    timestamp: int,
    nonce: str,
    body_hash: str,
    version: str = INTERNAL_HMAC_VERSION,
) -> str:
    if version == LEGACY_PUSH_HMAC_VERSION:
        # Compatibilidade com o contrato ja publicado do push-worker.
        parts = [
            version,
            method.upper(),
            target,
            str(timestamp),
            nonce,
            body_hash,
        ]
    elif version == INTERNAL_HMAC_VERSION:
        parts = [
            version,
            service,
            method.upper(),
            target,
            str(timestamp),
            nonce,
            body_hash,
        ]
    else:
        raise ValueError(f"unsupported internal HMAC version: {version}")
    return "\n".join(parts)


def internal_hmac_signature(
    secret: str,
    *,
    service: str,
    method: str,
    target: str,
    body: bytes,
    timestamp: int,
    nonce: str,
    version: str = INTERNAL_HMAC_VERSION,
) -> str:
    canonical = canonical_internal_request(
        service=service,
        method=method,
        target=target,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=_body_hash(body),
        version=version,
    )
    return hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_internal_hmac_signature(
    secret: str,
    *,
    service: str,
    method: str,
    target: str,
    body: bytes,
    timestamp: int,
    nonce: str,
    signature: str,
    version: str = INTERNAL_HMAC_VERSION,
) -> bool:
    try:
        expected = internal_hmac_signature(
            secret,
            service=service,
            method=method,
            target=target,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
            version=version,
        )
    except ValueError:
        return False
    return hmac.compare_digest(expected, signature)


def build_internal_hmac_headers(
    secret: str,
    method: str,
    url: str,
    body: bytes,
    *,
    service: str = "push-worker",
    version: str | None = None,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Assina uma chamada interna.

    O push-worker continua em ``push-v2`` por compatibilidade. Novos callers
    usam ``internal-hmac-v1``, que inclui a identidade do servico no MAC.
    """

    signed_at = int(time.time()) if timestamp is None else timestamp
    signed_nonce = secrets.token_hex(16) if nonce is None else nonce
    signed_version = version or (
        LEGACY_PUSH_HMAC_VERSION
        if service == "push-worker"
        else INTERNAL_HMAC_VERSION
    )
    request_target = request_target_from_url(url)
    signature = internal_hmac_signature(
        secret,
        service=service,
        method=method,
        target=request_target,
        body=body,
        timestamp=signed_at,
        nonce=signed_nonce,
        version=signed_version,
    )
    headers = {
        "X-Internal-Service": service,
        "X-Internal-Timestamp": str(signed_at),
        "X-Internal-Nonce": signed_nonce,
        "X-Internal-Signature": signature,
    }
    if signed_version == INTERNAL_HMAC_VERSION:
        headers["X-Internal-Version"] = signed_version
        headers["X-Internal-Caller"] = service
    return headers
