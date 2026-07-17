from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse


def build_internal_hmac_headers(
    secret: str,
    method: str,
    url: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    signed_at = int(time.time()) if timestamp is None else timestamp
    signed_nonce = secrets.token_hex(16) if nonce is None else nonce
    parsed = urlparse(url)
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        [
            "push-v2",
            method.upper(),
            request_target,
            str(signed_at),
            signed_nonce,
            body_hash,
        ]
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Internal-Service": "push-worker",
        "X-Internal-Timestamp": str(signed_at),
        "X-Internal-Nonce": signed_nonce,
        "X-Internal-Signature": signature,
    }
