"""Backend-only stable opaque tenant key, independent of integration key slots."""
from fastapi import HTTPException

from app.opaque_keys import generate_opaque_key
from app.project_secret_service import encrypt_project_material, decrypt_project_material


async def get_studio_administrative_key(conn, *, project_id):
    # The canonical project lock serializes first provisioning and revocation.
    await conn.execute("SELECT id FROM projects WHERE id=$1 FOR UPDATE", project_id)
    row = await conn.fetchrow("SELECT secret_ciphertext, is_active FROM project_studio_keys WHERE project_id=$1", project_id)
    if row is None:
        key = generate_opaque_key(project_id, "secret")
        ciphertext = await encrypt_project_material(
            conn, project_id=project_id, purpose="studio-administrative-key", plaintext=key.token
        )
        await conn.execute("INSERT INTO project_studio_keys(project_id, secret_hash, secret_ciphertext) VALUES($1,$2,$3)", project_id, key.digest, ciphertext)
        return key.token
    if not row["is_active"]:
        raise HTTPException(403, "Studio administrative credential revoked; privileged reprovisioning required")
    return await decrypt_project_material(
        conn, project_id=project_id, purpose="studio-administrative-key", ciphertext=row["secret_ciphertext"]
    )
