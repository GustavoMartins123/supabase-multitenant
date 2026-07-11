from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request


def _decode_base64url_json(raw: str) -> dict[str, Any] | None:
    try:
        padded = raw + ("=" * (-len(raw) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
        return None
    return payload if isinstance(payload, dict) else None


def resolve_user_id_from_hmac_token(
    request: Request,
    *,
    secret: str,
    max_clock_skew_seconds: int,
    now: int | None = None,
) -> uuid.UUID:
    token = (request.headers.get("X-User-Token") or "").strip()
    if not token:
        raise HTTPException(401, "X-User-Token ausente")

    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise HTTPException(401, "X-User-Token inválido")

    _, encoded_payload, signature = parts
    try:
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
    except UnicodeEncodeError as exc:
        raise HTTPException(401, "X-User-Token inválido") from exc

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(401, "X-User-Token com assinatura inválida")

    payload = _decode_base64url_json(encoded_payload)
    if payload is None:
        raise HTTPException(401, "X-User-Token com payload inválido")

    current_time = int(time.time()) if now is None else now
    try:
        expires_at = int(payload.get("exp", 0))
        issued_at = int(payload.get("iat", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "X-User-Token com datas inválidas") from exc

    if expires_at <= current_time - max_clock_skew_seconds:
        raise HTTPException(401, "X-User-Token expirado")
    if issued_at > current_time + max_clock_skew_seconds:
        raise HTTPException(401, "X-User-Token emitido no futuro")

    try:
        return uuid.UUID(str(payload.get("sub") or ""))
    except ValueError as exc:
        raise HTTPException(401, "X-User-Token sem usuário válido") from exc
