"""Fail-closed data-plane authorizer for project opaque API keys."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import urllib.parse

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Response

from opaque_keys import (
    ALLOWED_SERVICES,
    OpaqueKeyError,
    parse_opaque_key,
    should_preserve_authorization,
)


PROJECT_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
GATEWAY_TOKEN_RE = re.compile(r"^[a-f0-9]{64}$")
DB_DSN = (os.getenv("DB_DSN") or "").strip()
if not DB_DSN:
    raise RuntimeError("DB_DSN is required by key-authorizer")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_pool: asyncpg.Pool | None = None


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail="Invalid API key",
        headers={"Cache-Control": "no-store"},
    )


def _canonical_query_key(
    query_key: str | None, original_args: str | None
) -> str:
    forwarded = query_key or ""
    if forwarded != forwarded.strip():
        raise OpaqueKeyError("API key query value has non-canonical whitespace")
    raw_values: list[str] = []
    for part in (original_args or "").split("&"):
        if not part:
            continue
        raw_name, separator, raw_value = part.partition("=")
        name = urllib.parse.unquote_plus(raw_name)
        if name.lower() != "apikey":
            continue
        if raw_name != "apikey" or name != "apikey" or not separator:
            raise OpaqueKeyError("API key query parameter is not canonical")
        decoded_value = urllib.parse.unquote_plus(raw_value)
        if raw_value != decoded_value:
            raise OpaqueKeyError("API key query value is not canonical")
        raw_values.append(decoded_value)
    if len(raw_values) > 1:
        raise OpaqueKeyError("duplicate API key query parameters")
    raw_value = raw_values[0] if raw_values else ""
    if not hmac.compare_digest(forwarded, raw_value):
        raise OpaqueKeyError("API key query parsing mismatch")
    return forwarded


def _candidate_key(
    header_key: str | None,
    query_key: str | None,
    original_args: str | None,
    *,
    allow_missing: bool,
) -> str | None:
    header_value = header_key or ""
    if header_value != header_value.strip():
        raise OpaqueKeyError("API key header has non-canonical whitespace")
    query_value = _canonical_query_key(query_key, original_args)
    if header_value and query_value and not hmac.compare_digest(
        header_value, query_value
    ):
        raise OpaqueKeyError("ambiguous API key sources")
    candidate = header_value or query_value
    if not candidate:
        if allow_missing:
            return None
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={
                "WWW-Authenticate": "ApiKey",
                "Cache-Control": "no-store",
            },
        )
    return candidate


@app.on_event("startup")
async def startup() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=20)
    async with _pool.acquire() as conn:
        await conn.fetchval("SELECT 1")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if _pool is None:
        raise HTTPException(503, "authorizer database pool is unavailable")
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except (asyncpg.PostgresError, OSError) as exc:
        raise HTTPException(503, "authorizer database is unavailable") from exc
    return {"status": "ok"}


@app.get("/v1/authorize", status_code=204)
async def authorize(
    x_project_ref: str | None = Header(default=None),
    x_project_gateway_token: str | None = Header(default=None),
    x_api_key_header: str | None = Header(default=None),
    x_api_key_query: str | None = Header(default=None),
    x_original_authorization: str | None = Header(default=None),
    x_original_args: str | None = Header(default=None),
    x_target_service: str | None = Header(default=None),
    x_required_role: str | None = Header(default=None),
    x_allow_missing_key: str | None = Header(default=None),
) -> Response:
    """Validate one request without returning or logging credential material."""

    project_ref = x_project_ref or ""
    gateway_token = x_project_gateway_token or ""
    target_service = x_target_service or ""
    required_role = x_required_role or ""
    allow_missing_value = (
        x_allow_missing_key if x_allow_missing_key is not None else ""
    )
    if any(
        value != value.strip()
        for value in (
            project_ref,
            gateway_token,
            target_service,
            required_role,
            allow_missing_value,
        )
    ):
        raise _forbidden()
    if not PROJECT_RE.fullmatch(project_ref):
        raise _forbidden()
    if not GATEWAY_TOKEN_RE.fullmatch(gateway_token):
        raise _forbidden()
    if target_service not in ALLOWED_SERVICES:
        raise _forbidden()
    if required_role not in {"", "anon", "service_role"}:
        raise _forbidden()
    if allow_missing_value not in {"0", "1"}:
        raise _forbidden()
    allow_missing = allow_missing_value == "1"
    if allow_missing and target_service != "storage":
        raise _forbidden()
    try:
        api_key = _candidate_key(
            x_api_key_header,
            x_api_key_query,
            x_original_args,
            allow_missing=allow_missing,
        )
    except OpaqueKeyError as exc:
        raise _forbidden() from exc

    if _pool is None:
        raise HTTPException(503, "key authorizer is not ready")
    try:
        async with _pool.acquire() as conn:
            project = await conn.fetchrow(
                """
                SELECT id, api_gateway_token_hash, api_keyset_version,
                       opaque_keys_activated_at
                FROM projects
                WHERE name = $1
                """,
                project_ref,
            )
            if (
                project is None
                or project["api_gateway_token_hash"] is None
                or project["opaque_keys_activated_at"] is None
            ):
                raise _forbidden()
            provided_gateway_hash = hashlib.sha256(
                gateway_token.encode("utf-8")
            ).digest()
            stored_gateway_hash = bytes(project["api_gateway_token_hash"])
            if not hmac.compare_digest(provided_gateway_hash, stored_gateway_hash):
                raise _forbidden()

            if api_key is None:
                authorization = x_original_authorization or ""
                if authorization != authorization.strip():
                    raise _forbidden()
                if re.match(
                    r"^Bearer\s+sb_(?:publishable|secret)_",
                    authorization,
                    flags=re.IGNORECASE,
                ):
                    raise _forbidden()
                return Response(
                    status_code=204,
                    headers={
                        "Cache-Control": "no-store",
                        "X-Opaque-Key-Present": "0",
                        "X-Opaque-Preserve-Authorization": "1",
                        "X-Opaque-Keyset-Version": str(
                            project["api_keyset_version"]
                        ),
                    },
                )

            try:
                parsed = parse_opaque_key(project["id"], api_key)
                authorization = x_original_authorization or ""
                if authorization != authorization.strip():
                    raise OpaqueKeyError(
                        "Authorization contains non-canonical whitespace"
                    )
                if (
                    target_service in {"storage", "functions"}
                    and authorization
                    and not re.match(
                        r"^Bearer\s+", authorization, flags=re.IGNORECASE
                    )
                ):
                    preserve_authorization = True
                else:
                    preserve_authorization = should_preserve_authorization(
                        api_key, authorization
                    )
            except OpaqueKeyError as exc:
                raise _forbidden() from exc

            key = await conn.fetchrow(
                """
                SELECT k.id, s.kind, s.allowed_services
                FROM project_api_keys k
                JOIN project_api_key_slots s ON s.id = k.slot_id
                WHERE s.project_id = $1
                  AND s.status = 'active'
                  AND k.secret_hash = $2
                  AND (k.expires_at IS NULL OR k.expires_at > now())
                  AND (
                      (
                          k.status = 'active'
                          AND k.activated_at IS NOT NULL
                          AND NOT EXISTS (
                              SELECT 1
                              FROM project_api_keys due
                              WHERE due.slot_id = k.slot_id
                                AND due.status = 'pending'
                                AND due.activate_at <= now()
                                AND due.confirmed_at IS NOT NULL
                          )
                      )
                      OR (
                          k.status = 'pending'
                          AND k.activate_at <= now()
                          AND k.confirmed_at IS NOT NULL
                      )
                  )
                """,
                project["id"],
                parsed.digest,
            )
            if (
                key is None
                or key["kind"] != parsed.kind
                or target_service not in key["allowed_services"]
                or (required_role and parsed.role != required_role)
            ):
                raise _forbidden()
            await conn.execute(
                """
                UPDATE project_api_keys
                SET last_used_at = now()
                WHERE id = $1
                  AND (last_used_at IS NULL OR last_used_at < now() - interval '5 minutes')
                """,
                key["id"],
            )
    except HTTPException:
        raise
    except (asyncpg.PostgresError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="API key authorization unavailable",
            headers={"Cache-Control": "no-store", "Retry-After": "1"},
        ) from exc

    return Response(
        status_code=204,
        headers={
            "Cache-Control": "no-store",
            "X-Opaque-Key-Role": parsed.role,
            "X-Opaque-Key-Present": "1",
            "X-Opaque-Key-Id": str(key["id"]),
            "X-Opaque-Preserve-Authorization": (
                "1" if preserve_authorization else "0"
            ),
            "X-Opaque-Keyset-Version": str(project["api_keyset_version"]),
        },
    )
