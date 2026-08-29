"""Validation and one-time consumption of action-bound step-up grants."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import re
import time
import uuid
from typing import TYPE_CHECKING, Any, NoReturn

from fastapi import HTTPException

if TYPE_CHECKING:
    import asyncpg


STEP_UP_TOKEN_PREFIX = "su1"
STEP_UP_TOKEN_TTL_SECONDS = 300
STEP_UP_KEY_CONTEXT = b"supabase-multitenant:step-up-token:v1"
STEP_UP_ACTIONS = frozenset(
    {
        "delete_project",
        "reveal_secret_key",
        "create_secret_key",
        "rotate_secret_key",
        "activate_secret_key",
    }
)

_PROJECT_REF_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
_SLOT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,39}$")
_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_JTI_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")
_HEX_SIGNATURE_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _forbidden(
    message: str = "Reautenticacao obrigatoria ou invalida",
) -> NoReturn:
    raise HTTPException(403, message)


def _decode_base64url_json(raw: str) -> dict[str, Any] | None:
    try:
        padded = raw + ("=" * (-len(raw) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        binascii.Error,
    ):
        return None
    return payload if isinstance(payload, dict) else None


def _derived_signing_key(secret: str) -> bytes:
    if not secret:
        raise RuntimeError("NGINX_HMAC_SECRET is required for step-up grants")
    return hmac.new(
        secret.encode("utf-8"),
        STEP_UP_KEY_CONTEXT,
        hashlib.sha256,
    ).digest()


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if hmac.compare_digest(value, canonical) else None


def resolve_step_up_grant(
    token: str | None,
    *,
    secret: str,
    max_clock_skew_seconds: int,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify a grant without granting authority or consuming it."""

    raw_token = (token or "").strip()
    if not raw_token or len(raw_token) > 4096:
        _forbidden()

    parts = raw_token.split(".")
    if len(parts) != 3 or parts[0] != STEP_UP_TOKEN_PREFIX:
        _forbidden()
    _, encoded_payload, signature = parts
    if not _HEX_SIGNATURE_PATTERN.fullmatch(signature):
        _forbidden()

    try:
        encoded_payload_bytes = encoded_payload.encode("ascii", errors="strict")
    except UnicodeEncodeError:
        _forbidden()
    expected_signature = hmac.new(
        _derived_signing_key(secret),
        encoded_payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        _forbidden()

    payload = _decode_base64url_json(encoded_payload)
    required_claims = {
        "sub",
        "iat",
        "exp",
        "login_session",
        "action",
        "project",
        "resource",
        "jti",
    }
    if payload is None or set(payload) != required_claims:
        _forbidden()

    current_time = int(time.time()) if now is None else now
    if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
        _forbidden()
    issued_at = payload["iat"]
    expires_at = payload["exp"]

    if issued_at > current_time + max_clock_skew_seconds:
        _forbidden()
    if expires_at <= current_time:
        _forbidden("Reautenticacao expirada")
    if expires_at <= issued_at:
        _forbidden()
    if expires_at - issued_at != STEP_UP_TOKEN_TTL_SECONDS:
        _forbidden()

    subject = _canonical_uuid(payload["sub"])
    login_session = payload["login_session"]
    action = payload["action"]
    project = payload["project"]
    resource = payload["resource"]
    jti = payload["jti"]
    if subject is None:
        _forbidden()
    if not isinstance(login_session, str) or not _SESSION_PATTERN.fullmatch(
        login_session
    ):
        _forbidden()
    if action not in STEP_UP_ACTIONS:
        _forbidden()
    if not isinstance(project, str) or not _PROJECT_REF_PATTERN.fullmatch(project):
        _forbidden()
    if not isinstance(resource, str) or not resource:
        _forbidden()
    if not isinstance(jti, str) or not _JTI_PATTERN.fullmatch(jti):
        _forbidden()

    if action == "delete_project":
        if not hmac.compare_digest(resource, project):
            _forbidden()
    elif action == "create_secret_key":
        if not _SLOT_NAME_PATTERN.fullmatch(resource):
            _forbidden()
    elif _canonical_uuid(resource) is None:
        _forbidden()

    return {
        **payload,
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
    }


async def consume_step_up_grant(
    conn: asyncpg.Connection,
    *,
    token: str | None,
    secret: str,
    max_clock_skew_seconds: int,
    auth_user: dict[str, Any],
    action: str,
    project_id: uuid.UUID,
    project_ref: str,
    resource_id: str,
) -> dict[str, Any]:
    """Validate all bindings and atomically mark a grant as used."""

    if action not in STEP_UP_ACTIONS:
        raise ValueError(f"unsupported step-up action: {action}")

    claims = resolve_step_up_grant(
        token,
        secret=secret,
        max_clock_skew_seconds=max_clock_skew_seconds,
    )
    actor_id = str(auth_user.get("db_user_id") or "")
    login_session = str(auth_user.get("login_session") or "")
    expected_bindings = (
        (claims["sub"], actor_id),
        (claims["login_session"], login_session),
        (claims["action"], action),
        (claims["project"], project_ref),
        (claims["resource"], resource_id),
    )
    if not login_session or any(
        not hmac.compare_digest(actual, expected)
        for actual, expected in expected_bindings
    ):
        _forbidden("Reautenticacao nao corresponde a esta sessao ou operacao")

    issued_at = dt.datetime.fromtimestamp(claims["iat"], tz=dt.timezone.utc)
    expires_at = dt.datetime.fromtimestamp(claims["exp"], tz=dt.timezone.utc)
    consumed = await conn.fetchval(
        """
        INSERT INTO studio_step_up_grant_consumptions(
            jti, user_id, login_session_hash, action,
            project_id, project_ref, resource_id, issued_at, expires_at
        )
        SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9
        WHERE $9 > now()
        ON CONFLICT (jti) DO NOTHING
        RETURNING jti
        """,
        claims["jti"],
        auth_user["db_user_id"],
        login_session,
        action,
        project_id,
        project_ref,
        resource_id,
        issued_at,
        expires_at,
    )
    if consumed is None:
        _forbidden("Reautenticacao expirada ou ja utilizada")
    return claims
