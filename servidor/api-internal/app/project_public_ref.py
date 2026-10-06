"""Public project identity; callers must authorize the resolved project separately."""

from __future__ import annotations

import re
import secrets
import string
import json
import uuid
from typing import Any, Protocol


PUBLIC_REF_LENGTH = 20
PUBLIC_REF_PATTERN = re.compile(r"[a-z]{20}\Z", re.ASCII)


class PublicProjectNotFound(LookupError):
    pass


class ProjectLookupConnection(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> Any: ...


def generate_public_ref() -> str:
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(PUBLIC_REF_LENGTH))


def validate_public_ref(value: str) -> str:
    if not isinstance(value, str) or not PUBLIC_REF_PATTERN.fullmatch(value):
        raise ValueError("public_ref must contain exactly 20 lowercase ASCII letters")
    return value


async def resolve_public_project(
    conn: ProjectLookupConnection, public_ref: str, *, for_update: bool = False
) -> Any:
    public_ref = validate_public_ref(public_ref)
    row = await conn.fetchrow(
        """
        SELECT id, tenant_uuid, name, display_name, owner_id, public_ref,
               automatic_key_rotation_enabled,
               automatic_key_rotation_blocked_at,
               automatic_key_rotation_last_error,
               opaque_gateway_ready_at, resource_profile
        FROM projects WHERE public_ref = $1
        """ + (" FOR UPDATE" if for_update else ""),
        public_ref,
    )
    if row is None:
        raise PublicProjectNotFound("Project not found")
    return row


async def get_provisioning_public_ref(conn: ProjectLookupConnection, job_id: str) -> str:
    row = await conn.fetchrow(
        """
        SELECT p.public_ref, j.payload
        FROM jobs j JOIN projects p ON p.id = j.project_uuid
        WHERE j.job_id = $1
        """,
        uuid.UUID(str(job_id)),
    )
    if row is None:
        raise PublicProjectNotFound("Provisioning project not found")
    public_ref = validate_public_ref(row["public_ref"])
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("public_ref") != public_ref:
        raise ValueError("Provisioning public reference differs from the durable job intent")
    return public_ref
