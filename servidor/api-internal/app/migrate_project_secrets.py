"""Migrate legacy Fernet project secrets to per-tenant envelope encryption.

Run inside the projects-api image after adding the new environment variables:

    python -m app.migrate_project_secrets --dry-run
    python -m app.migrate_project_secrets --apply

The command never prints plaintext secrets. A dry-run creates any required
schema inside a transaction and rolls the whole transaction back. The apply
mode is atomic and resumable: already-v2 rows are authenticated and skipped,
while a changed master key only rewraps each tenant DEK without re-encrypting
the individual values.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

import asyncpg
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.project_secrets import ProjectKeyEnvelope, ProjectSecretManager


SECRET_COLUMNS = ("anon_key", "service_role", "config_token")


def _previous_keys() -> tuple[str, ...]:
    return tuple(
        key.strip()
        for key in os.getenv("PROJECT_SECRETS_PREVIOUS_MASTER_KEYS", "").split(",")
        if key.strip()
    )


def _legacy_keyring() -> MultiFernet | None:
    keys = [
        key
        for key in [os.getenv("LEGACY_FERNET_SECRET", "").strip()]
        if key
    ]
    if not keys:
        return None
    return MultiFernet([Fernet(key.encode("ascii")) for key in keys])


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_key_envelopes (
            project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            key_id UUID NOT NULL UNIQUE,
            wrapped_dek TEXT NOT NULL,
            wrapping_key_id TEXT NOT NULL,
            algorithm TEXT NOT NULL DEFAULT 'aes-256-gcm',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_project_key_envelopes_wrapping_key
            ON project_key_envelopes(wrapping_key_id);
        """
    )


async def get_envelope(
    conn: asyncpg.Connection,
    manager: ProjectSecretManager,
    project_id: uuid.UUID,
    *,
    apply: bool,
) -> tuple[ProjectKeyEnvelope, bytes, bool]:
    row = await conn.fetchrow(
        """
        SELECT key_id, wrapped_dek, wrapping_key_id, algorithm
        FROM project_key_envelopes
        WHERE project_id = $1
        FOR UPDATE
        """,
        project_id,
    )
    if row is None:
        envelope, dek = manager.create_envelope()
        if apply:
            await conn.execute(
                """
                INSERT INTO project_key_envelopes(
                    project_id, key_id, wrapped_dek, wrapping_key_id, algorithm
                ) VALUES($1, $2, $3, $4, $5)
                """,
                project_id,
                uuid.UUID(envelope.key_id),
                envelope.wrapped_dek,
                envelope.wrapping_key_id,
                envelope.algorithm,
            )
        return envelope, dek, True

    envelope = ProjectKeyEnvelope(
        key_id=str(row["key_id"]),
        wrapped_dek=row["wrapped_dek"],
        wrapping_key_id=row["wrapping_key_id"],
        algorithm=row["algorithm"],
    )
    dek = manager.unwrap_dek(envelope)
    rewrapped = envelope.wrapping_key_id != manager.wrapping_key_id
    if rewrapped and apply:
        wrapped = manager.rewrap_dek(dek)
        await conn.execute(
            """
            UPDATE project_key_envelopes
            SET wrapped_dek = $1, wrapping_key_id = $2, updated_at = now()
            WHERE project_id = $3
            """,
            wrapped,
            manager.wrapping_key_id,
            project_id,
        )
    return envelope, dek, rewrapped


async def migrate(
    *,
    apply: bool,
    project_name: str | None,
    rotate_deks: bool,
) -> tuple[int, int, int, int]:
    dsn = os.getenv("DB_DSN", "").strip()
    master_key = os.getenv("PROJECT_SECRETS_MASTER_KEY", "").strip()
    if not dsn or not master_key:
        raise RuntimeError("DB_DSN and PROJECT_SECRETS_MASTER_KEY are required")

    manager = ProjectSecretManager(
        master_key,
        wrapping_key_id=os.getenv(
            "PROJECT_SECRETS_MASTER_KEY_ID", "project-secrets-master-v1"
        ),
        previous_master_keys=_previous_keys(),
    )
    legacy = _legacy_keyring()
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    migrated_projects = migrated_values = rewrapped_deks = rotated_deks = 0
    try:
        async with pool.acquire() as conn:
            outer_transaction = conn.transaction()
            await outer_transaction.start()
            try:
                await ensure_schema(conn)
                rows = await conn.fetch(
                    """
                    SELECT id, name, anon_key, service_role, config_token
                    FROM projects
                    WHERE ($1::text IS NULL OR name = $1)
                      AND (anon_key IS NOT NULL OR service_role IS NOT NULL OR config_token IS NOT NULL)
                    ORDER BY name
                    """,
                    project_name,
                )
                for row in rows:
                    async with conn.transaction():
                        envelope, dek, rewrapped = await get_envelope(
                            conn,
                            manager,
                            row["id"],
                            apply=apply,
                        )
                        target_envelope, target_dek = envelope, dek
                        if rotate_deks:
                            target_envelope, target_dek = manager.create_envelope()
                        updates: dict[str, str] = {}
                        for column in SECRET_COLUMNS:
                            ciphertext = row[column]
                            if not ciphertext:
                                continue
                            if manager.is_v2(ciphertext):
                                plaintext = manager.decrypt(
                                    project_id=row["id"],
                                    purpose=column,
                                    key_id=envelope.key_id,
                                    dek=dek,
                                    ciphertext=ciphertext,
                                )
                                if not rotate_deks:
                                    continue
                            else:
                                if legacy is None:
                                    raise RuntimeError(
                                        "LEGACY_FERNET_SECRET is required while legacy values remain"
                                    )
                                try:
                                    plaintext = legacy.decrypt(ciphertext.encode()).decode()
                                except (InvalidToken, UnicodeDecodeError) as exc:
                                    raise RuntimeError(
                                        f"Cannot decrypt legacy {column} for project {row['name']}"
                                    ) from exc
                            updates[column] = manager.encrypt(
                                project_id=row["id"],
                                purpose=column,
                                key_id=target_envelope.key_id,
                                dek=target_dek,
                                plaintext=plaintext,
                            )

                        if updates:
                            migrated_projects += 1
                            migrated_values += len(updates)
                            if apply:
                                if rotate_deks:
                                    await conn.execute(
                                        """
                                        UPDATE project_key_envelopes
                                        SET key_id = $1,
                                            wrapped_dek = $2,
                                            wrapping_key_id = $3,
                                            algorithm = $4,
                                            updated_at = now()
                                        WHERE project_id = $5
                                        """,
                                        uuid.UUID(target_envelope.key_id),
                                        target_envelope.wrapped_dek,
                                        target_envelope.wrapping_key_id,
                                        target_envelope.algorithm,
                                        row["id"],
                                    )
                                assignments = ", ".join(
                                    f"{column} = ${index}"
                                    for index, column in enumerate(updates, start=1)
                                )
                                await conn.execute(
                                    f"UPDATE projects SET {assignments} WHERE id = ${len(updates) + 1}",
                                    *updates.values(),
                                    row["id"],
                                )
                        if rotate_deks:
                            rotated_deks += 1
                        if rewrapped:
                            rewrapped_deks += 1
            except BaseException:
                await outer_transaction.rollback()
                raise
            else:
                if apply:
                    await outer_transaction.commit()
                else:
                    await outer_transaction.rollback()
    finally:
        await pool.close()
    return migrated_projects, migrated_values, rewrapped_deks, rotated_deks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="persist the migration")
    parser.add_argument("--project", help="migrate a single project slug")
    parser.add_argument(
        "--rotate-deks",
        action="store_true",
        help="generate a new per-project data key and re-encrypt every value",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    projects, values, rewrapped, rotated = await migrate(
        apply=args.apply,
        project_name=args.project,
        rotate_deks=args.rotate_deks,
    )
    mode = "applied" if args.apply else "dry-run"
    print(
        f"{mode}: projects_with_legacy_values={projects} "
        f"values_to_migrate={values} deks_to_rewrap={rewrapped} "
        f"deks_to_rotate={rotated}"
    )


if __name__ == "__main__":
    asyncio.run(main())
