"""Canonical per-tenant SQL identity. No shared-role membership or legacy DSN."""
from __future__ import annotations

import hashlib
import hmac
import re
import uuid


def tenant_meta_credentials(tenant_uuid: object, master_password: str) -> tuple[str, str]:
    try:
        identity = uuid.UUID(str(tenant_uuid))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("Canonical tenant UUID is required for SQL administration") from exc
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", master_password):
        raise RuntimeError("META_ADMIN_DB_PASSWORD must contain 32-128 URL-safe characters")
    password = hmac.new(
        master_password.encode(), f"tenant-meta-v1:{identity}".encode(), hashlib.sha256
    ).hexdigest()
    return f"tenant_meta_{identity.hex}", password


def tenant_assistant_reader_credentials(tenant_uuid: object, master_password: str) -> tuple[str, str]:
    meta_role, meta_password = tenant_meta_credentials(tenant_uuid, master_password)
    password = hashlib.sha256(f"assistant-reader-v1:{meta_password}".encode()).hexdigest()
    return meta_role.replace("tenant_meta_", "tenant_ai_reader_", 1), password
