from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_user_token(
    secret: str,
    user_id: str,
    *,
    now: int | None = None,
    ttl_seconds: int = 300,
) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = json.dumps(
        {"sub": user_id, "iat": issued_at, "exp": issued_at + ttl_seconds},
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"v1.{encoded}.{signature}"


def build_internal_push_headers(
    secret: str,
    url: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    signed_at = int(time.time()) if timestamp is None else timestamp
    signed_nonce = nonce or os.urandom(16).hex()
    path = urlparse(url).path or "/"
    canonical = "\n".join(
        [
            "push-v1",
            "POST",
            path,
            str(signed_at),
            signed_nonce,
            hashlib.sha256(body).hexdigest(),
        ]
    )
    signature = hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Internal-Service": "push-worker",
        "X-Internal-Timestamp": str(signed_at),
        "X-Internal-Nonce": signed_nonce,
        "X-Internal-Signature": signature,
    }


def ssl_context() -> ssl.SSLContext:
    if not env_flag("SMOKE_VERIFY_TLS", True):
        return ssl._create_unverified_context()
    ca_file = os.getenv("SMOKE_CA_FILE", "").strip()
    if ca_file:
        return ssl.create_default_context(cafile=str(Path(ca_file)))
    return ssl.create_default_context()


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
    timeout: float = 30,
) -> tuple[int, Any]:
    body = raw_body
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(
            req,
            timeout=timeout,
            context=ssl_context(),
        ) as response:
            status = response.status
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_body = exc.read()

    text = response_body.decode(errors="replace")
    try:
        return status, json.loads(text) if text else None
    except json.JSONDecodeError:
        return status, text


def wait_for_job(
    api_url: str,
    job_id: str,
    headers: dict[str, str],
    *,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, body = request(
            "GET",
            f"{api_url.rstrip('/')}/api/projects/status/{job_id}",
            headers=headers,
        )
        if status != 200 or not isinstance(body, dict):
            raise AssertionError(f"job polling returned HTTP {status}: {body}")
        last = body
        if body.get("status") == "done":
            return body
        if body.get("status") == "failed":
            raise AssertionError(
                "job failed at "
                f"{body.get('current_step')} ({body.get('progress')}%): "
                f"{body.get('message')}"
            )
        time.sleep(3)
    raise AssertionError(f"job timeout; last state: {last}")
