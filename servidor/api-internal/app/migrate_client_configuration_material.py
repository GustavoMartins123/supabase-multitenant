"""Populate public publishable material during offline deployment."""

import hmac
import asyncio
import os

import asyncpg

from app.opaque_keys import parse_opaque_key
from app.project_secrets import ProjectKeyEnvelope, ProjectSecretManager


async def populate_public_client_configuration_keys(conn, manager: ProjectSecretManager) -> int:
    async with conn.transaction():
        rows = await conn.fetch("""
            SELECT k.id, k.secret_hash, s.project_id, r.ciphertext
            FROM project_api_keys k JOIN project_api_key_slots s ON s.id = k.slot_id
            LEFT JOIN project_api_key_reveals r ON r.key_id = k.id
            LEFT JOIN public_client_configuration_keys material ON material.key_id = k.id
            WHERE s.kind = 'publishable' AND s.status = 'active'
              AND k.status IN ('active', 'pending') AND material.key_id IS NULL
            ORDER BY k.id FOR UPDATE OF k
        """)
        for row in rows:
            if row['ciphertext'] is None:
                raise RuntimeError('Publishable material is missing; deployment cannot continue')
            envelope_row = await conn.fetchrow('''SELECT key_id,wrapped_dek,wrapping_key_id,algorithm
                FROM project_key_envelopes WHERE project_id=$1''', row['project_id'])
            if envelope_row is None:
                raise RuntimeError('Project key envelope is unavailable')
            envelope = ProjectKeyEnvelope(key_id=str(envelope_row['key_id']),
                wrapped_dek=envelope_row['wrapped_dek'], wrapping_key_id=envelope_row['wrapping_key_id'],
                algorithm=envelope_row['algorithm'])
            token = manager.decrypt(project_id=row['project_id'], purpose=f"opaque-api-key-reveal:{row['id']}",
                ciphertext=row['ciphertext'], key_id=envelope.key_id, dek=manager.unwrap_dek(envelope))
            parsed = parse_opaque_key(row['project_id'], token)
            if parsed.kind != 'publishable' or not hmac.compare_digest(parsed.digest, bytes(row['secret_hash'])):
                raise RuntimeError('Publishable material does not match the registry')
            await conn.execute('INSERT INTO public_client_configuration_keys(key_id,publishable_key) VALUES($1,$2)',
                row['id'], token)
        return len(rows)


async def main():
    manager = ProjectSecretManager(os.environ['PROJECT_SECRETS_MASTER_KEY'],
        wrapping_key_id=os.environ['PROJECT_SECRETS_MASTER_KEY_ID'],
        previous_master_keys=tuple(k.strip() for k in os.environ['PROJECT_SECRETS_PREVIOUS_MASTER_KEYS'].split(',') if k.strip()))
    conn = await asyncpg.connect(os.environ['DB_DSN'])
    try:
        count = await populate_public_client_configuration_keys(conn, manager)
        print(f'Publishable configuration material populated: {count}; no tokens printed.')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
