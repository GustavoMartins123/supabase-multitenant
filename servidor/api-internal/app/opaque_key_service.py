"""Persistence and lifecycle operations for project opaque API keys."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg

from app.opaque_keys import (
    ALLOWED_SERVICES,
    GeneratedOpaqueKey,
    OpaqueKeyKind,
    generate_opaque_key,
    normalize_slot_name,
    validate_allowed_services,
)
from app.project_secret_service import (
    decrypt_project_material,
    encrypt_project_material,
)


KeyStatus = Literal["pending", "active", "revoked", "expired"]
SlotStatus = Literal["active", "disabled"]
RotationTrigger = Literal["initial", "manual", "automatic"]
DEFAULT_ROTATION_INTERVAL_DAYS = 90
MIGRATION_PREPARATION_WINDOW_DAYS = 7
MIN_ROTATION_INTERVAL_DAYS = 1
MAX_ROTATION_INTERVAL_DAYS = 3650
PROJECT_GATEWAY_TOKEN_RE = re.compile(r"^[a-f0-9]{64}$")


class OpaqueKeyLifecycleError(ValueError):
    """Raised when a requested key lifecycle transition is invalid."""


class OpaqueKeyRevealGone(OpaqueKeyLifecycleError):
    """Raised when one-time key material no longer exists."""


@dataclass(frozen=True)
class IssuedOpaqueKey:
    slot_id: uuid.UUID
    key_id: uuid.UUID
    token: str
    token_hint: str
    kind: OpaqueKeyKind
    status: KeyStatus
    expires_at: dt.datetime | None
    activate_at: dt.datetime | None = None


def _validate_rotation_interval(days: int) -> int:
    if not MIN_ROTATION_INTERVAL_DAYS <= days <= MAX_ROTATION_INTERVAL_DAYS:
        raise OpaqueKeyLifecycleError(
            f"rotation interval must be between {MIN_ROTATION_INTERVAL_DAYS} "
            f"and {MAX_ROTATION_INTERVAL_DAYS} days"
        )
    return days


def _validate_slot_lifecycle(
    *, automatic_rotation_enabled: bool, rotation_interval_days: int | None
) -> None:
    if rotation_interval_days is None and automatic_rotation_enabled:
        raise OpaqueKeyLifecycleError(
            "automatic rotation requires a temporal expiration interval"
        )


def _expiration_from_policy(
    now: dt.datetime, rotation_interval_days: int | None
) -> dt.datetime | None:
    if rotation_interval_days is None:
        return None
    return now + dt.timedelta(days=rotation_interval_days)


def _expiration_for_policy_transition(
    *,
    now: dt.datetime,
    current_expires_at: dt.datetime | None,
    rotation_interval_days: int | None,
) -> dt.datetime | None:
    if current_expires_at is not None and current_expires_at <= now:
        raise OpaqueKeyLifecycleError(
            "an expired API key cannot be revived by a policy change; "
            "rotate the slot immediately"
        )
    return _expiration_from_policy(now, rotation_interval_days)


async def _database_now(conn: asyncpg.Connection) -> dt.datetime:
    value = await conn.fetchval("SELECT now()")
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise OpaqueKeyLifecycleError(
            "database returned an invalid transaction timestamp"
        )
    return value


def _reveal_purpose(key_id: uuid.UUID) -> str:
    return f"opaque-api-key-reveal:{key_id}"


async def _increment_keyset_version(
    conn: asyncpg.Connection, project_id: uuid.UUID
) -> int:
    version = await conn.fetchval(
        """
        UPDATE projects
        SET api_keyset_version = api_keyset_version + 1
        WHERE id = $1
        RETURNING api_keyset_version
        """,
        project_id,
    )
    if version is None:
        raise OpaqueKeyLifecycleError("project not found while updating keyset")
    return int(version)


async def _insert_key(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    kind: OpaqueKeyKind,
    status: KeyStatus,
    expires_at: dt.datetime | None,
    replaces_key_id: uuid.UUID | None,
    activate_at: dt.datetime | None = None,
    disclosed_inline: bool = False,
    rotation_trigger: RotationTrigger = "manual",
) -> IssuedOpaqueKey:
    generated: GeneratedOpaqueKey = generate_opaque_key(project_id, kind)
    key_id = uuid.uuid4()
    now = await _database_now(conn)
    activated_at = now if status == "active" else None
    revealed_at = now if status == "pending" and disclosed_inline else None
    await conn.execute(
        """
        INSERT INTO project_api_keys(
            id, slot_id, secret_hash, token_hint, status,
            activate_at, expires_at, activated_at, replaces_key_id,
            rotation_trigger, revealed_at
        )
        VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        key_id,
        slot_id,
        generated.digest,
        generated.token_hint,
        status,
        activate_at,
        expires_at,
        activated_at,
        replaces_key_id,
        rotation_trigger,
        revealed_at,
    )
    ciphertext = await encrypt_project_material(
        conn,
        project_id=project_id,
        purpose=_reveal_purpose(key_id),
        plaintext=generated.token,
    )
    await conn.execute(
        """
        INSERT INTO project_api_key_reveals(key_id, ciphertext)
        VALUES($1, $2)
        """,
        key_id,
        ciphertext,
    )
    return IssuedOpaqueKey(
        slot_id=slot_id,
        key_id=key_id,
        token=generated.token,
        token_hint=generated.token_hint,
        kind=kind,
        status=status,
        expires_at=expires_at,
        activate_at=activate_at,
    )


async def create_slot_with_active_key(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    name: str,
    kind: OpaqueKeyKind,
    allowed_services: list[str] | tuple[str, ...],
    created_by: uuid.UUID,
    automatic_rotation_enabled: bool | None = None,
    rotation_interval_days: int | None = DEFAULT_ROTATION_INTERVAL_DAYS,
    disclosed_inline: bool = True,
    rotation_trigger: RotationTrigger = "manual",
    initializing_project: bool = False,
) -> tuple[IssuedOpaqueKey, int]:
    """Create one consumer slot and its only active key atomically."""

    name = normalize_slot_name(name)
    services = validate_allowed_services(allowed_services)
    interval = (
        _validate_rotation_interval(rotation_interval_days)
        if rotation_interval_days is not None
        else None
    )
    project = await conn.fetchrow(
        """
        SELECT automatic_key_rotation_enabled, opaque_keys_prepared_at,
               opaque_keys_activated_at, opaque_gateway_ready_at
        FROM projects WHERE id = $1 FOR UPDATE
        """,
        project_id,
    )
    if project is None:
        raise OpaqueKeyLifecycleError("project not found")
    if initializing_project:
        if (
            project["opaque_keys_prepared_at"] is not None
            or project["opaque_keys_activated_at"] is not None
            or project["opaque_gateway_ready_at"] is not None
        ):
            raise OpaqueKeyLifecycleError(
                "project opaque API key initialization state is invalid"
            )
    elif (
        project["opaque_keys_activated_at"] is None
        or project["opaque_gateway_ready_at"] is None
    ):
        raise OpaqueKeyLifecycleError(
            "opaque API key management requires an active gateway"
        )
    auto_rotation = (
        bool(project["automatic_key_rotation_enabled"])
        if automatic_rotation_enabled is None
        else automatic_rotation_enabled
    )
    _validate_slot_lifecycle(
        automatic_rotation_enabled=auto_rotation,
        rotation_interval_days=interval,
    )
    slot_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO project_api_key_slots(
            id, project_id, name, kind, allowed_services,
            automatic_rotation_enabled, rotation_interval_days, created_by
        )
        VALUES($1, $2, $3, $4, $5::text[], $6, $7, $8)
        """,
        slot_id,
        project_id,
        name,
        kind,
        list(services),
        auto_rotation,
        interval,
        created_by,
    )
    now = await _database_now(conn)
    issued = await _insert_key(
        conn,
        project_id=project_id,
        slot_id=slot_id,
        kind=kind,
        status="active",
        expires_at=_expiration_from_policy(now, interval),
        replaces_key_id=None,
        disclosed_inline=disclosed_inline,
        rotation_trigger=rotation_trigger,
    )
    version = await _increment_keyset_version(conn, project_id)
    return issued, version


async def bootstrap_project_opaque_keys(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    gateway_token: str,
) -> tuple[IssuedOpaqueKey, IssuedOpaqueKey]:
    """Atomically activate the mandatory initial publishable and secret slots."""

    if not PROJECT_GATEWAY_TOKEN_RE.fullmatch(gateway_token):
        raise OpaqueKeyLifecycleError(
            "project gateway token must be 32 random bytes encoded as lowercase hex"
        )
    project = await conn.fetchrow(
        """
        SELECT api_gateway_token_hash, opaque_keys_prepared_at,
               opaque_keys_activated_at
        FROM projects
        WHERE id = $1
        FOR UPDATE
        """,
        project_id,
    )
    if project is None:
        raise OpaqueKeyLifecycleError("project not found")
    slot_count = await conn.fetchval(
        "SELECT count(*) FROM project_api_key_slots WHERE project_id = $1",
        project_id,
    )
    if (
        int(slot_count) != 0
        or project["api_gateway_token_hash"] is not None
        or project["opaque_keys_prepared_at"] is not None
        or project["opaque_keys_activated_at"] is not None
    ):
        raise OpaqueKeyLifecycleError("project opaque API keys are already initialized")

    publishable, _ = await create_slot_with_active_key(
        conn,
        project_id=project_id,
        name="default-publishable",
        kind="publishable",
        allowed_services=sorted(ALLOWED_SERVICES),
        created_by=created_by,
        disclosed_inline=False,
        rotation_trigger="initial",
        initializing_project=True,
    )
    secret, _ = await create_slot_with_active_key(
        conn,
        project_id=project_id,
        name="default-secret",
        kind="secret",
        allowed_services=sorted(ALLOWED_SERVICES),
        created_by=created_by,
        disclosed_inline=False,
        rotation_trigger="initial",
        initializing_project=True,
    )
    result = await conn.execute(
        """
        UPDATE projects
        SET api_gateway_token_hash = $2,
            opaque_keys_prepared_at = now(),
            opaque_keys_activated_at = now(),
            opaque_gateway_ready_at = now()
        WHERE id = $1
          AND api_gateway_token_hash IS NULL
          AND opaque_keys_prepared_at IS NULL
          AND opaque_keys_activated_at IS NULL
        """,
        project_id,
        hashlib.sha256(gateway_token.encode("ascii")).digest(),
    )
    if result != "UPDATE 1":
        raise OpaqueKeyLifecycleError("project opaque API key activation conflicted")
    return publishable, secret


async def prepare_project_opaque_key_migration(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    gateway_token: str,
) -> tuple[IssuedOpaqueKey, IssuedOpaqueKey]:
    """Prepare two rejected initial keys while the legacy gateway still runs."""

    if not PROJECT_GATEWAY_TOKEN_RE.fullmatch(gateway_token):
        raise OpaqueKeyLifecycleError(
            "project gateway token must be 32 random bytes encoded as lowercase hex"
        )
    project = await conn.fetchrow(
        """
        SELECT automatic_key_rotation_enabled, api_gateway_token_hash,
               opaque_keys_prepared_at, opaque_keys_activated_at
        FROM projects
        WHERE id = $1
        FOR UPDATE
        """,
        project_id,
    )
    if project is None:
        raise OpaqueKeyLifecycleError("project not found")
    if project["opaque_keys_activated_at"] is not None:
        raise OpaqueKeyLifecycleError("project opaque API keys are already active")
    if (
        project["opaque_keys_prepared_at"] is not None
        or project["api_gateway_token_hash"] is not None
        or await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM project_api_key_slots WHERE project_id = $1)",
            project_id,
        )
    ):
        raise OpaqueKeyLifecycleError(
            "project opaque API key migration is already prepared"
        )

    now = await _database_now(conn)
    issued: list[IssuedOpaqueKey] = []
    for name, kind in (
        ("default-publishable", "publishable"),
        ("default-secret", "secret"),
    ):
        slot_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO project_api_key_slots(
                id, project_id, name, kind, allowed_services,
                automatic_rotation_enabled, rotation_interval_days, created_by
            )
            VALUES($1, $2, $3, $4, $5::text[], $6, $7, $8)
            """,
            slot_id,
            project_id,
            name,
            kind,
            sorted(ALLOWED_SERVICES),
            bool(project["automatic_key_rotation_enabled"]),
            DEFAULT_ROTATION_INTERVAL_DAYS,
            created_by,
        )
        issued_key = await _insert_key(
            conn,
            project_id=project_id,
            slot_id=slot_id,
            kind=kind,
            status="pending",
            activate_at=None,
            expires_at=now
            + dt.timedelta(
                days=MIGRATION_PREPARATION_WINDOW_DAYS
                + DEFAULT_ROTATION_INTERVAL_DAYS
            ),
            replaces_key_id=None,
            rotation_trigger="initial",
        )
        issued.append(issued_key)
        await _increment_keyset_version(conn, project_id)

    result = await conn.execute(
        """
        UPDATE projects
        SET api_gateway_token_hash = $2,
            opaque_keys_prepared_at = now()
        WHERE id = $1
          AND api_gateway_token_hash IS NULL
          AND opaque_keys_prepared_at IS NULL
          AND opaque_keys_activated_at IS NULL
        """,
        project_id,
        hashlib.sha256(gateway_token.encode("ascii")).digest(),
    )
    if result != "UPDATE 1":
        raise OpaqueKeyLifecycleError("project opaque API key preparation conflicted")
    return issued[0], issued[1]


async def validate_prepared_project_opaque_keys(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    require_cutover_started: bool = False,
) -> list[asyncpg.Record]:
    """Lock and validate the immutable pre-cutover migration keyset."""

    project = await conn.fetchrow(
        """
        SELECT opaque_keys_prepared_at, opaque_keys_activated_at,
               opaque_gateway_cutover_started_at
        FROM projects
        WHERE id = $1
        FOR UPDATE
        """,
        project_id,
    )
    if project is None:
        raise OpaqueKeyLifecycleError("project not found")
    if project["opaque_keys_prepared_at"] is None:
        raise OpaqueKeyLifecycleError(
            "project opaque API key migration is not prepared"
        )
    if project["opaque_keys_activated_at"] is not None:
        raise OpaqueKeyLifecycleError("project opaque API keys are already active")
    if (
        require_cutover_started
        and project["opaque_gateway_cutover_started_at"] is None
    ):
        raise OpaqueKeyLifecycleError(
            "opaque gateway cutover has not started"
        )
    rows = await conn.fetch(
        """
        SELECT s.id AS slot_id, s.name, s.rotation_interval_days,
               k.id AS key_id, k.revealed_at, k.confirmed_at, k.expires_at
        FROM project_api_key_slots s
        JOIN project_api_keys k ON k.slot_id = s.id
        WHERE s.project_id = $1
          AND s.status = 'active'
          AND k.status = 'pending'
          AND k.rotation_trigger = 'initial'
        ORDER BY s.name
        FOR UPDATE OF s, k
        """,
        project_id,
    )
    if {row["name"] for row in rows} != {
        "default-publishable",
        "default-secret",
    } or len(rows) != 2:
        raise OpaqueKeyLifecycleError(
            "prepared migration must contain exactly the two initial slots"
        )
    if any(
        row["revealed_at"] is None or row["confirmed_at"] is None
        for row in rows
    ):
        raise OpaqueKeyLifecycleError(
            "both initial API keys must be revealed and confirmed before cutover"
        )
    now = await _database_now(conn)
    if any(
        row["expires_at"] is not None and row["expires_at"] <= now
        for row in rows
    ):
        raise OpaqueKeyLifecycleError(
            "prepared migration contains an expired API key"
        )
    return rows


async def abort_prepared_project_opaque_keys(
    conn: asyncpg.Connection, *, project_id: uuid.UUID
) -> int:
    """Transactionally discard a preparation before cutover has started."""

    project = await conn.fetchrow(
        """
        SELECT opaque_keys_prepared_at, opaque_keys_activated_at,
               opaque_gateway_cutover_started_at, opaque_gateway_ready_at
        FROM projects
        WHERE id = $1
        FOR UPDATE
        """,
        project_id,
    )
    if project is None:
        raise OpaqueKeyLifecycleError("project not found")
    if project["opaque_keys_prepared_at"] is None:
        raise OpaqueKeyLifecycleError(
            "project opaque API key migration is not prepared"
        )
    if (
        project["opaque_keys_activated_at"] is not None
        or project["opaque_gateway_cutover_started_at"] is not None
        or project["opaque_gateway_ready_at"] is not None
    ):
        raise OpaqueKeyLifecycleError(
            "prepared migration cannot be aborted after cutover starts"
        )
    slots = await conn.fetch(
        """
        SELECT s.id, s.name, k.status, k.rotation_trigger
        FROM project_api_key_slots s
        JOIN project_api_keys k ON k.slot_id = s.id
        WHERE s.project_id = $1
        FOR UPDATE OF s, k
        """,
        project_id,
    )
    if (
        len(slots) != 2
        or {row["name"] for row in slots}
        != {"default-publishable", "default-secret"}
        or any(
            row["status"] != "pending" or row["rotation_trigger"] != "initial"
            for row in slots
        )
    ):
        raise OpaqueKeyLifecycleError(
            "prepared migration keyset is inconsistent and was not modified"
        )
    await conn.execute(
        "DELETE FROM project_api_key_slots WHERE project_id = $1",
        project_id,
    )
    version = await conn.fetchval(
        """
        UPDATE projects
        SET api_gateway_token_hash = NULL,
            opaque_keys_prepared_at = NULL,
            api_keyset_version = api_keyset_version + 1
        WHERE id = $1
          AND opaque_keys_activated_at IS NULL
          AND opaque_gateway_cutover_started_at IS NULL
          AND opaque_gateway_ready_at IS NULL
        RETURNING api_keyset_version
        """,
        project_id,
    )
    if version is None:
        raise OpaqueKeyLifecycleError("prepared migration abort conflicted")
    return int(version)


async def activate_prepared_project_opaque_keys(
    conn: asyncpg.Connection, *, project_id: uuid.UUID
) -> int:
    """Commit an explicitly prepared project migration in one transaction."""

    rows = await validate_prepared_project_opaque_keys(
        conn, project_id=project_id, require_cutover_started=True
    )

    for row in rows:
        await conn.execute(
            """
            UPDATE project_api_keys
            SET status = 'active',
                activate_at = now(),
                activated_at = now(),
                expires_at = CASE
                    WHEN $2::integer IS NULL THEN NULL
                    ELSE now() + make_interval(days => $2::integer)
                END
            WHERE id = $1 AND status = 'pending'
            """,
            row["key_id"],
            row["rotation_interval_days"],
        )
    result = await conn.execute(
        """
        UPDATE projects
        SET opaque_keys_activated_at = now()
        WHERE id = $1 AND opaque_keys_activated_at IS NULL
        """,
        project_id,
    )
    if result != "UPDATE 1":
        raise OpaqueKeyLifecycleError("project opaque API key activation conflicted")
    return await _increment_keyset_version(conn, project_id)


async def rotate_slot_immediately(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> tuple[IssuedOpaqueKey, int]:
    """Hard-cut one slot to a replacement key with no validity overlap."""

    slot = await conn.fetchrow(
        """
        SELECT s.id, s.kind, s.rotation_interval_days
        FROM project_api_key_slots s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = $1 AND s.project_id = $2 AND s.status = 'active'
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
        FOR UPDATE OF s, p
        """,
        slot_id,
        project_id,
    )
    if slot is None:
        raise OpaqueKeyLifecycleError("active API key slot not found")
    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET automatic_rotation_blocked_at = NULL,
            automatic_rotation_last_error = NULL,
            updated_at = now()
        WHERE id = $1
        """,
        slot_id,
    )
    now = await _database_now(conn)
    pending = await conn.fetchrow(
        """
        SELECT id, activate_at, confirmed_at
        FROM project_api_keys
        WHERE slot_id = $1 AND status = 'pending'
        FOR UPDATE
        """,
        slot_id,
    )
    replaces_effective_pending_id = None
    if pending is not None:
        if (
            pending["confirmed_at"] is None
            or pending["activate_at"] is None
            or pending["activate_at"] > now
        ):
            raise OpaqueKeyLifecycleError("slot already has a pending rotation")
        result = await conn.execute(
            """
            UPDATE project_api_keys
            SET status = 'revoked', revoked_at = now()
            WHERE id = $1 AND status = 'pending'
            """,
            pending["id"],
        )
        if result != "UPDATE 1":
            raise OpaqueKeyLifecycleError(
                "effective pending API key replacement conflicted"
            )
        await conn.execute(
            "DELETE FROM project_api_key_reveals WHERE key_id = $1",
            pending["id"],
        )
        replaces_effective_pending_id = pending["id"]
    active_id = await conn.fetchval(
        """
        UPDATE project_api_keys
        SET status = 'revoked', revoked_at = now()
        WHERE slot_id = $1 AND status = 'active'
        RETURNING id
        """,
        slot_id,
    )
    if active_id is None:
        raise OpaqueKeyLifecycleError("slot has no active API key")
    await conn.execute(
        "DELETE FROM project_api_key_reveals WHERE key_id = $1",
        active_id,
    )
    if replaces_effective_pending_id is not None:
        replaces_key_id = replaces_effective_pending_id
    else:
        replaces_key_id = active_id
    issued = await _insert_key(
        conn,
        project_id=project_id,
        slot_id=slot_id,
        kind=slot["kind"],
        status="active",
        expires_at=_expiration_from_policy(
            now, slot["rotation_interval_days"]
        ),
        replaces_key_id=replaces_key_id,
    )
    version = await _increment_keyset_version(conn, project_id)
    return issued, version


async def prepare_slot_rotation(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    activate_at: dt.datetime,
    disclosed_inline: bool,
    rotation_trigger: RotationTrigger = "manual",
) -> tuple[IssuedOpaqueKey, int]:
    """Create a pending version for a future deterministic cutover."""

    now = await _database_now(conn)
    if activate_at.tzinfo is None:
        raise OpaqueKeyLifecycleError("activate_at must include a timezone")
    activate_at = activate_at.astimezone(dt.timezone.utc)
    if activate_at <= now:
        raise OpaqueKeyLifecycleError("activate_at must be in the future")
    slot = await conn.fetchrow(
        """
        SELECT s.id, s.kind, s.rotation_interval_days
        FROM project_api_key_slots s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = $1 AND s.project_id = $2 AND s.status = 'active'
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
        FOR UPDATE OF s, p
        """,
        slot_id,
        project_id,
    )
    if slot is None:
        raise OpaqueKeyLifecycleError("active API key slot not found")
    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET automatic_rotation_blocked_at = NULL,
            automatic_rotation_last_error = NULL,
            updated_at = now()
        WHERE id = $1
        """,
        slot_id,
    )
    pending_exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM project_api_keys WHERE slot_id = $1 AND status = 'pending')",
        slot_id,
    )
    if pending_exists:
        raise OpaqueKeyLifecycleError("slot already has a pending rotation")
    active = await conn.fetchrow(
        "SELECT id, expires_at FROM project_api_keys WHERE slot_id = $1 AND status = 'active'",
        slot_id,
    )
    if active is None:
        raise OpaqueKeyLifecycleError("slot has no active API key")
    if (
        active["expires_at"] is not None
        and activate_at > active["expires_at"]
    ):
        raise OpaqueKeyLifecycleError(
            "activate_at cannot be later than the active API key expiration"
        )
    issued = await _insert_key(
        conn,
        project_id=project_id,
        slot_id=slot_id,
        kind=slot["kind"],
        status="pending",
        activate_at=activate_at,
        expires_at=_expiration_from_policy(
            activate_at, slot["rotation_interval_days"]
        ),
        replaces_key_id=active["id"],
        disclosed_inline=disclosed_inline,
        rotation_trigger=rotation_trigger,
    )
    version = await _increment_keyset_version(conn, project_id)
    return issued, version


async def activate_pending_key(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> tuple[uuid.UUID, int]:
    """Activate a due pending key and revoke the current version atomically."""

    slot = await conn.fetchrow(
        """
        SELECT s.id
        FROM project_api_key_slots s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = $1 AND s.project_id = $2 AND s.status = 'active'
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
        FOR UPDATE OF s, p
        """,
        slot_id,
        project_id,
    )
    if slot is None:
        raise OpaqueKeyLifecycleError("active API key slot not found")
    pending = await conn.fetchrow(
        """
        SELECT id, activate_at, expires_at, confirmed_at
        FROM project_api_keys
        WHERE slot_id = $1 AND status = 'pending'
        FOR UPDATE
        """,
        slot_id,
    )
    if pending is None:
        raise OpaqueKeyLifecycleError("slot has no pending API key")
    if pending["confirmed_at"] is None:
        raise OpaqueKeyLifecycleError(
            "pending API key installation has not been confirmed"
        )
    now = await _database_now(conn)
    if pending["activate_at"] is None or pending["activate_at"] > now:
        raise OpaqueKeyLifecycleError("pending API key is not due for activation")
    if pending["expires_at"] is not None and pending["expires_at"] <= now:
        raise OpaqueKeyLifecycleError("pending API key has expired")
    revoked_id = await conn.fetchval(
        """
        UPDATE project_api_keys
        SET status = 'revoked', revoked_at = now()
        WHERE slot_id = $1 AND status = 'active'
        RETURNING id
        """,
        slot_id,
    )
    if revoked_id is None:
        raise OpaqueKeyLifecycleError("slot has no active API key")
    activated_id = await conn.fetchval(
        """
        UPDATE project_api_keys
        SET status = 'active', activated_at = now()
        WHERE id = $1 AND status = 'pending'
        RETURNING id
        """,
        pending["id"],
    )
    if activated_id is None:
        raise OpaqueKeyLifecycleError("pending API key activation conflicted")
    await conn.execute(
        "DELETE FROM project_api_key_reveals WHERE key_id = $1",
        revoked_id,
    )
    version = await _increment_keyset_version(conn, project_id)
    return pending["id"], version


async def confirm_pending_key_installation(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    key_id: uuid.UUID,
) -> int:
    """Confirm that a revealed pending key has reached its consumer."""

    pending = await conn.fetchrow(
        """
        SELECT k.id, k.revealed_at, k.confirmed_at, k.expires_at
        FROM project_api_keys k
        JOIN project_api_key_slots s ON s.id = k.slot_id
        JOIN projects p ON p.id = s.project_id
        WHERE k.id = $1
          AND k.slot_id = $2
          AND s.project_id = $3
          AND s.status = 'active'
          AND k.status = 'pending'
          AND (
              (
                  p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
              )
              OR (
                  p.opaque_keys_prepared_at IS NOT NULL
                  AND p.opaque_keys_activated_at IS NULL
                  AND p.opaque_gateway_cutover_started_at IS NULL
                  AND k.rotation_trigger = 'initial'
              )
          )
        FOR UPDATE OF k, s, p
        """,
        key_id,
        slot_id,
        project_id,
    )
    if pending is None:
        raise OpaqueKeyLifecycleError("pending API key not found")
    if pending["revealed_at"] is None:
        raise OpaqueKeyLifecycleError(
            "pending API key must be revealed before installation confirmation"
        )
    if pending["confirmed_at"] is not None:
        raise OpaqueKeyLifecycleError(
            "pending API key installation is already confirmed"
        )
    now = await _database_now(conn)
    if pending["expires_at"] is not None and pending["expires_at"] <= now:
        raise OpaqueKeyLifecycleError("pending API key has expired")
    await conn.execute(
        "UPDATE project_api_keys SET confirmed_at = now() WHERE id = $1",
        key_id,
    )
    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET automatic_rotation_blocked_at = NULL,
            automatic_rotation_last_error = NULL,
            updated_at = now()
        WHERE id = $1
        """,
        slot_id,
    )
    return await _increment_keyset_version(conn, project_id)


async def cancel_pending_key(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> tuple[uuid.UUID, int]:
    """Revoke the one pending replacement without touching the active key."""

    pending = await conn.fetchrow(
        """
        SELECT k.id, k.activate_at, k.confirmed_at
        FROM project_api_keys k
        JOIN project_api_key_slots s ON s.id = k.slot_id
        JOIN projects p ON p.id = s.project_id
        WHERE k.slot_id = s.id
          AND k.slot_id = $1
          AND s.project_id = $2
          AND p.id = s.project_id
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
          AND s.status = 'active'
          AND k.status = 'pending'
        FOR UPDATE OF k, s, p
        """,
        slot_id,
        project_id,
    )
    if pending is None:
        raise OpaqueKeyLifecycleError("slot has no pending API key")
    now = await _database_now(conn)
    if (
        pending["confirmed_at"] is not None
        and pending["activate_at"] is not None
        and pending["activate_at"] <= now
    ):
        raise OpaqueKeyLifecycleError(
            "an effective pending API key cannot be cancelled"
        )
    key_id = pending["id"]
    result = await conn.execute(
        """
        UPDATE project_api_keys
        SET status = 'revoked', revoked_at = now()
        WHERE id = $1 AND status = 'pending'
        """,
        key_id,
    )
    if result != "UPDATE 1":
        raise OpaqueKeyLifecycleError("pending API key cancellation conflicted")
    await conn.execute(
        "DELETE FROM project_api_key_reveals WHERE key_id = $1",
        key_id,
    )
    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET automatic_rotation_blocked_at = NULL,
            automatic_rotation_last_error = NULL,
            updated_at = now()
        WHERE id = $1
        """,
        slot_id,
    )
    version = await _increment_keyset_version(conn, project_id)
    return key_id, version


async def disable_slot(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> int:
    slot = await conn.fetchrow(
        """
        SELECT s.id
        FROM project_api_key_slots s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = $1 AND s.project_id = $2 AND s.status = 'active'
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
        FOR UPDATE OF s, p
        """,
        slot_id,
        project_id,
    )
    if slot is None:
        raise OpaqueKeyLifecycleError("active API key slot not found")
    await conn.execute(
        """
        UPDATE project_api_keys
        SET status = 'revoked', revoked_at = now()
        WHERE slot_id = $1 AND status IN ('active', 'pending')
        """,
        slot_id,
    )
    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET status = 'disabled', updated_at = now()
        WHERE id = $1
        """,
        slot_id,
    )
    await conn.execute(
        """
        DELETE FROM project_api_key_reveals
        WHERE key_id IN (SELECT id FROM project_api_keys WHERE slot_id = $1)
        """,
        slot_id,
    )
    return await _increment_keyset_version(conn, project_id)


async def update_slot_policy(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    slot_id: uuid.UUID,
    automatic_rotation_enabled: bool | None,
    rotation_interval_days: int | None,
    rotation_interval_days_provided: bool,
    allowed_services: list[str] | tuple[str, ...] | None,
) -> int:
    """Update one slot policy without reviving an expired key."""

    slot = await conn.fetchrow(
        """
        SELECT s.automatic_rotation_enabled, s.rotation_interval_days,
               s.allowed_services
        FROM project_api_key_slots s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = $1 AND s.project_id = $2 AND s.status = 'active'
          AND p.opaque_keys_activated_at IS NOT NULL
          AND p.opaque_gateway_ready_at IS NOT NULL
        FOR UPDATE OF s, p
        """,
        slot_id,
        project_id,
    )
    if slot is None:
        raise OpaqueKeyLifecycleError("active API key slot not found")
    if (
        automatic_rotation_enabled is None
        and not rotation_interval_days_provided
        and allowed_services is None
    ):
        raise OpaqueKeyLifecycleError("at least one slot policy field is required")

    interval = (
        (
            _validate_rotation_interval(rotation_interval_days)
            if rotation_interval_days is not None
            else None
        )
        if rotation_interval_days_provided
        else slot["rotation_interval_days"]
    )
    services = (
        validate_allowed_services(allowed_services)
        if allowed_services is not None
        else tuple(slot["allowed_services"])
    )
    auto_rotation = (
        bool(automatic_rotation_enabled)
        if automatic_rotation_enabled is not None
        else bool(slot["automatic_rotation_enabled"])
    )
    _validate_slot_lifecycle(
        automatic_rotation_enabled=auto_rotation,
        rotation_interval_days=interval,
    )

    if automatic_rotation_enabled is False:
        cancelled = await conn.fetch(
            """
            UPDATE project_api_keys
            SET status = 'revoked', revoked_at = now()
            WHERE slot_id = $1
              AND status = 'pending'
              AND rotation_trigger = 'automatic'
              AND NOT (
                  confirmed_at IS NOT NULL
                  AND activate_at IS NOT NULL
                  AND activate_at <= now()
              )
            RETURNING id
            """,
            slot_id,
        )
        if cancelled:
            await conn.execute(
                """
                DELETE FROM project_api_key_reveals
                WHERE key_id = ANY($1::uuid[])
                """,
                [row["id"] for row in cancelled],
            )

    if (
        rotation_interval_days_provided
        and interval != slot["rotation_interval_days"]
    ):
        pending_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM project_api_keys
                WHERE slot_id = $1 AND status = 'pending'
            )
            """,
            slot_id,
        )
        if pending_exists:
            raise OpaqueKeyLifecycleError(
                "expiration policy cannot change while the slot has a pending key"
            )
        active = await conn.fetchrow(
            """
            SELECT id, expires_at
            FROM project_api_keys
            WHERE slot_id = $1 AND status = 'active'
            FOR UPDATE
            """,
            slot_id,
        )
        if active is None:
            raise OpaqueKeyLifecycleError("slot has no active API key")
        now = await _database_now(conn)
        new_expiration = _expiration_for_policy_transition(
            now=now,
            current_expires_at=active["expires_at"],
            rotation_interval_days=interval,
        )
        result = await conn.execute(
            """
            UPDATE project_api_keys
            SET expires_at = $2
            WHERE id = $1
              AND status = 'active'
              AND (expires_at IS NULL OR expires_at > now())
            """,
            active["id"],
            new_expiration,
        )
        if result != "UPDATE 1":
            raise OpaqueKeyLifecycleError(
                "active API key expiration policy update conflicted"
            )

    await conn.execute(
        """
        UPDATE project_api_key_slots
        SET automatic_rotation_enabled = $2,
            rotation_interval_days = $3,
            allowed_services = $4::text[],
            automatic_rotation_blocked_at = CASE
                WHEN $2 OR $3::integer IS NULL THEN NULL
                ELSE automatic_rotation_blocked_at
            END,
            automatic_rotation_last_error = CASE
                WHEN $2 OR $3::integer IS NULL THEN NULL
                ELSE automatic_rotation_last_error
            END,
            updated_at = now()
        WHERE id = $1
        """,
        slot_id,
        auto_rotation,
        interval,
        list(services),
    )
    return await _increment_keyset_version(conn, project_id)


async def cancel_project_automatic_pending_keys(
    conn: asyncpg.Connection, *, project_id: uuid.UUID
) -> int | None:
    """Cancel scheduled machine rotations when the project master switch is off."""

    await conn.fetchval(
        "SELECT id FROM projects WHERE id = $1 FOR UPDATE",
        project_id,
    )
    cancelled = await conn.fetch(
        """
        UPDATE project_api_keys k
        SET status = 'revoked', revoked_at = now()
        FROM project_api_key_slots s
        WHERE k.slot_id = s.id
          AND s.project_id = $1
          AND k.status = 'pending'
          AND k.rotation_trigger = 'automatic'
          AND NOT (
              k.confirmed_at IS NOT NULL
              AND k.activate_at IS NOT NULL
              AND k.activate_at <= now()
          )
        RETURNING k.id
        """,
        project_id,
    )
    if not cancelled:
        return None
    await conn.execute(
        "DELETE FROM project_api_key_reveals WHERE key_id = ANY($1::uuid[])",
        [row["id"] for row in cancelled],
    )
    return await _increment_keyset_version(conn, project_id)


async def claim_key_reveal(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    key_id: uuid.UUID,
) -> str:
    """Decrypt one reveal in the caller's transaction, without consuming it."""

    row = await conn.fetchrow(
        """
        SELECT r.ciphertext
        FROM project_api_key_reveals r
        JOIN project_api_keys k ON k.id = r.key_id
        JOIN project_api_key_slots s ON s.id = k.slot_id
        WHERE r.key_id = $1
          AND s.project_id = $2
          AND k.status IN ('active', 'pending')
        """,
        key_id,
        project_id,
    )
    if row is None:
        raise OpaqueKeyRevealGone("API key plaintext is no longer stored")
    await conn.execute(
        "UPDATE project_api_keys SET revealed_at = coalesce(revealed_at, now()) WHERE id = $1",
        key_id,
    )
    return await decrypt_project_material(
        conn,
        project_id=project_id,
        purpose=_reveal_purpose(key_id),
        ciphertext=row["ciphertext"],
    )


async def list_slots(
    conn: asyncpg.Connection, *, project_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            s.id AS slot_id,
            s.name,
            s.kind,
            s.allowed_services,
            s.automatic_rotation_enabled,
            s.rotation_interval_days,
            s.automatic_rotation_blocked_at,
            s.automatic_rotation_last_error,
            s.status AS slot_status,
            s.created_at AS slot_created_at,
            k.id AS key_id,
            k.token_hint,
            k.status AS key_status,
            k.created_at AS key_created_at,
            k.activate_at,
            k.expires_at,
            k.activated_at,
            k.revoked_at,
            k.last_used_at,
            k.revealed_at,
            k.confirmed_at,
            k.replaces_key_id,
            k.rotation_trigger,
            CASE
                WHEN s.status = 'active'
                  AND k.status = 'pending'
                  AND k.activate_at <= now()
                  AND k.confirmed_at IS NOT NULL
                  AND (k.expires_at IS NULL OR k.expires_at > now()) THEN true
                WHEN s.status = 'active'
                  AND k.status = 'active'
                  AND (k.expires_at IS NULL OR k.expires_at > now())
                  AND NOT EXISTS (
                      SELECT 1 FROM project_api_keys due
                      WHERE due.slot_id = k.slot_id
                        AND due.status = 'pending'
                        AND due.activate_at <= now()
                        AND due.confirmed_at IS NOT NULL
                  ) THEN true
                ELSE false
            END AS currently_accepted
        FROM project_api_key_slots s
        LEFT JOIN project_api_keys k ON k.slot_id = s.id
        WHERE s.project_id = $1
        ORDER BY s.created_at, k.created_at
        """,
        project_id,
    )
    by_slot: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        slot_id = row["slot_id"]
        slot = by_slot.setdefault(
            slot_id,
            {
                "id": str(slot_id),
                "name": row["name"],
                "kind": row["kind"],
                "role": "anon" if row["kind"] == "publishable" else "service_role",
                "allowed_services": list(row["allowed_services"]),
                "automatic_rotation_enabled": row["automatic_rotation_enabled"],
                "rotation_interval_days": row["rotation_interval_days"],
                "automatic_rotation_blocked_at": (
                    row["automatic_rotation_blocked_at"].isoformat()
                    if row["automatic_rotation_blocked_at"]
                    else None
                ),
                "automatic_rotation_last_error": row[
                    "automatic_rotation_last_error"
                ],
                "status": row["slot_status"],
                "created_at": row["slot_created_at"].isoformat(),
                "keys": [],
            },
        )
        if row["key_id"] is None:
            continue
        slot["keys"].append(
            {
                "id": str(row["key_id"]),
                "token_hint": row["token_hint"],
                "status": row["key_status"],
                "currently_accepted": row["currently_accepted"],
                "created_at": row["key_created_at"].isoformat(),
                "activate_at": (
                    row["activate_at"].isoformat() if row["activate_at"] else None
                ),
                "expires_at": (
                    row["expires_at"].isoformat() if row["expires_at"] else None
                ),
                "activated_at": (
                    row["activated_at"].isoformat() if row["activated_at"] else None
                ),
                "revoked_at": (
                    row["revoked_at"].isoformat() if row["revoked_at"] else None
                ),
                "last_used_at": (
                    row["last_used_at"].isoformat() if row["last_used_at"] else None
                ),
                "revealed_at": (
                    row["revealed_at"].isoformat() if row["revealed_at"] else None
                ),
                "confirmed_at": (
                    row["confirmed_at"].isoformat() if row["confirmed_at"] else None
                ),
                "replaces_key_id": (
                    str(row["replaces_key_id"]) if row["replaces_key_id"] else None
                ),
                "rotation_trigger": row["rotation_trigger"],
            }
        )
    return list(by_slot.values())


async def list_reveals(
    conn: asyncpg.Connection, *, project_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT r.key_id, r.created_at, k.status, k.revealed_at,
               s.id AS slot_id, s.name, s.kind
        FROM project_api_key_reveals r
        JOIN project_api_keys k ON k.id = r.key_id
        JOIN project_api_key_slots s ON s.id = k.slot_id
        WHERE s.project_id = $1
          AND k.status IN ('active', 'pending')
        ORDER BY r.created_at
        """,
        project_id,
    )
    return [
        {
            "key_id": str(row["key_id"]),
            "slot_id": str(row["slot_id"]),
            "slot_name": row["name"],
            "kind": row["kind"],
            "created_at": row["created_at"].isoformat(),
            "key_status": row["status"],
            "revealed_at": (
                row["revealed_at"].isoformat() if row["revealed_at"] else None
            ),
        }
        for row in rows
    ]
