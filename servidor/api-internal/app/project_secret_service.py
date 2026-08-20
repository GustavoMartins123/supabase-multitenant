"""Persistencia criptografada dos segredos de cada projeto."""

import re
import uuid

import asyncpg

from app.project_secrets import ProjectKeyEnvelope, ProjectSecretError
from app.runtime_config import project_secret_manager


PROJECT_SECRET_COLUMNS = frozenset({"anon_key", "service_role", "config_token"})
PROJECT_MATERIAL_PURPOSE_RE = re.compile(
    r"^opaque-api-key-reveal:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _project_secret_column(column: str) -> str:
    if column not in PROJECT_SECRET_COLUMNS:
        raise ValueError(f"unsupported project secret column: {column}")
    return column


def _record_to_envelope(row: asyncpg.Record) -> ProjectKeyEnvelope:
    return ProjectKeyEnvelope(
        key_id=str(row["key_id"]),
        wrapped_dek=row["wrapped_dek"],
        wrapping_key_id=row["wrapping_key_id"],
        algorithm=row["algorithm"],
    )


async def _get_project_key_envelope(
    conn: asyncpg.Connection, project_id: uuid.UUID
) -> tuple[ProjectKeyEnvelope, bytes]:
    row = await conn.fetchrow(
        """
        SELECT key_id, wrapped_dek, wrapping_key_id, algorithm
        FROM project_key_envelopes WHERE project_id = $1 FOR UPDATE
        """,
        project_id,
    )
    if row is None:
        created, created_dek = project_secret_manager.create_envelope()
        await conn.execute(
            """
            INSERT INTO project_key_envelopes(
                project_id, key_id, wrapped_dek, wrapping_key_id, algorithm
            ) VALUES($1, $2, $3, $4, $5)
            ON CONFLICT (project_id) DO NOTHING
            """,
            project_id,
            uuid.UUID(created.key_id),
            created.wrapped_dek,
            created.wrapping_key_id,
            created.algorithm,
        )
        row = await conn.fetchrow(
            """
            SELECT key_id, wrapped_dek, wrapping_key_id, algorithm
            FROM project_key_envelopes WHERE project_id = $1 FOR UPDATE
            """,
            project_id,
        )
        if row is None:
            raise RuntimeError("project key envelope was not persisted")
        envelope = _record_to_envelope(row)
        if envelope.key_id == created.key_id:
            return envelope, created_dek

    envelope = _record_to_envelope(row)
    dek = project_secret_manager.unwrap_dek(envelope)
    if envelope.wrapping_key_id != project_secret_manager.wrapping_key_id:
        rewrapped = project_secret_manager.rewrap_dek(dek)
        await conn.execute(
            """
            UPDATE project_key_envelopes
            SET wrapped_dek = $1, wrapping_key_id = $2, updated_at = now()
            WHERE project_id = $3
            """,
            rewrapped,
            project_secret_manager.wrapping_key_id,
            project_id,
        )
        envelope = ProjectKeyEnvelope(
            key_id=envelope.key_id,
            wrapped_dek=rewrapped,
            wrapping_key_id=project_secret_manager.wrapping_key_id,
            algorithm=envelope.algorithm,
        )
    return envelope, dek


async def encrypt_project_secret(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    column: str,
    plaintext: str,
) -> str:
    column = _project_secret_column(column)
    envelope, dek = await _get_project_key_envelope(conn, project_id)
    return project_secret_manager.encrypt(
        project_id=project_id,
        purpose=column,
        key_id=envelope.key_id,
        dek=dek,
        plaintext=plaintext,
    )


async def decrypt_project_secret(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    column: str,
    ciphertext: str,
) -> str:
    column = _project_secret_column(column)
    if not project_secret_manager.is_v2(ciphertext):
        raise ProjectSecretError(
            "legacy project secret format is not supported by projects-api; "
            "run app.migrate_project_secrets before deploying this version"
        )
    envelope, dek = await _get_project_key_envelope(conn, project_id)
    return project_secret_manager.decrypt(
        project_id=project_id,
        purpose=column,
        key_id=envelope.key_id,
        dek=dek,
        ciphertext=ciphertext,
    )


def _project_material_purpose(purpose: str) -> str:
    """Restrict non-column AAD purposes to explicitly supported material."""

    if not PROJECT_MATERIAL_PURPOSE_RE.fullmatch(purpose):
        raise ValueError(f"unsupported project material purpose: {purpose}")
    return purpose


async def encrypt_project_material(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    purpose: str,
    plaintext: str,
) -> str:
    """Encrypt transient project material with the project's existing DEK."""

    purpose = _project_material_purpose(purpose)
    envelope, dek = await _get_project_key_envelope(conn, project_id)
    return project_secret_manager.encrypt(
        project_id=project_id,
        purpose=purpose,
        key_id=envelope.key_id,
        dek=dek,
        plaintext=plaintext,
    )


async def decrypt_project_material(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    purpose: str,
    ciphertext: str,
) -> str:
    """Decrypt explicitly supported transient project material."""

    purpose = _project_material_purpose(purpose)
    if not project_secret_manager.is_v2(ciphertext):
        raise ProjectSecretError("project material is not a v2 envelope")
    envelope, dek = await _get_project_key_envelope(conn, project_id)
    return project_secret_manager.decrypt(
        project_id=project_id,
        purpose=purpose,
        key_id=envelope.key_id,
        dek=dek,
        ciphertext=ciphertext,
    )


async def store_project_secrets(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    anon_key: str | None = None,
    service_role: str | None = None,
    config_token: str | None = None,
) -> None:
    values: dict[str, str] = {}
    for column, plaintext in {
        "anon_key": anon_key,
        "service_role": service_role,
        "config_token": config_token,
    }.items():
        if plaintext is not None:
            values[column] = await encrypt_project_secret(
                conn, project_id=project_id, column=column, plaintext=plaintext
            )
    if not values:
        return
    assignments = ", ".join(
        f"{column} = ${index}" for index, column in enumerate(values, start=1)
    )
    await conn.execute(
        f"UPDATE projects SET {assignments} WHERE id = ${len(values) + 1}",
        *values.values(),
        project_id,
    )
