from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def git_compatible_bash() -> str:
    """Resolve Bash without selecting the Windows WSL application alias."""

    if os.name == "nt":
        candidate = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git"
            / "bin"
            / "bash.exe"
        )
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("bash")
    if executable is None:
        raise RuntimeError("bash nao esta instalado")
    return executable


def bash_path(path: Path) -> str:
    """Render an absolute path accepted by Git Bash and POSIX Bash."""

    return path.as_posix()


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


def build_step_up_token(
    secret: str,
    user_token: str,
    *,
    action: str,
    project: str,
    resource: str,
    now: int | None = None,
) -> str:
    """Build the gateway contract for direct API lifecycle smoke tests."""

    parts = user_token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise ValueError("SMOKE_USER_TOKEN is not a canonical user token")
    expected = hmac.new(
        secret.encode(), parts[1].encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(parts[2], expected):
        raise ValueError("SMOKE_USER_TOKEN signature does not match the HMAC secret")
    padded = parts[1] + ("=" * (-len(parts[1]) % 4))
    user_claims = json.loads(base64.urlsafe_b64decode(padded))
    subject = str(user_claims.get("sub") or "")
    login_session = str(user_claims.get("login_session") or "")
    if not subject or len(login_session) != 43:
        raise ValueError("SMOKE_USER_TOKEN has no step-up session binding")

    issued_at = int(time.time()) if now is None else now
    jti = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    payload = json.dumps(
        {
            "sub": subject,
            "iat": issued_at,
            "exp": issued_at + 300,
            "login_session": login_session,
            "action": action,
            "project": project,
            "resource": resource,
            "jti": jti,
        },
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signing_key = hmac.new(
        secret.encode(),
        b"supabase-multitenant:step-up-token:v1",
        hashlib.sha256,
    ).digest()
    signature = hmac.new(
        signing_key, encoded.encode(), hashlib.sha256
    ).hexdigest()
    return f"su1.{encoded}.{signature}"


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
    parsed = urlparse(url)
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    canonical = "\n".join(
        [
            "push-v2",
            "POST",
            request_target,
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



def build_internal_service_headers(
    secret: str,
    method: str,
    url: str,
    body: bytes = b"",
    *,
    service: str = "studio-gateway",
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    signed_at = int(time.time()) if timestamp is None else timestamp
    signed_nonce = nonce or os.urandom(16).hex()
    parsed = urlparse(url)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    canonical = "\n".join(
        [
            "internal-hmac-v1",
            service,
            method.upper(),
            target,
            str(signed_at),
            signed_nonce,
            hashlib.sha256(body).hexdigest(),
        ]
    )
    signature = hmac.new(
        secret.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "X-Internal-Version": "internal-hmac-v1",
        "X-Internal-Service": service,
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
    sign_internal: bool = True,
) -> tuple[int, Any]:
    body = raw_body
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        request_headers.setdefault("Content-Type", "application/json")

    if sign_internal:
        api_base = os.getenv("SMOKE_API_URL", "").rstrip("/")
        service_secret = os.getenv("SMOKE_STUDIO_GATEWAY_HMAC_SECRET", "")
        if api_base and service_secret and (url == api_base or url.startswith(api_base + "/")):
            request_headers.update(
                build_internal_service_headers(
                    service_secret,
                    method,
                    url,
                    body or b"",
                )
            )

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
