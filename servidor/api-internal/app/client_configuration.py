"""Public configuration for one explicitly bound publishable consumer slot."""

from __future__ import annotations

import hmac
import pathlib
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from app.opaque_keys import parse_opaque_key
from app.project_env_secrets import read_canonical_project_fields
from app.project_secret_service import decrypt_project_material


def project_public_url(project, projects_root: pathlib.Path) -> str:
    values = read_canonical_project_fields(projects_root, project['name'], (
        'PROJECT_UUID', 'PROJECT_PUBLIC_REF', 'API_EXTERNAL_URL',
    ))
    if (values['PROJECT_UUID'] != str(project['tenant_uuid'])
            or values['PROJECT_PUBLIC_REF'] != project['public_ref']):
        raise ValueError('Project environment identity does not match the registry')
    url = urlsplit(values['API_EXTERNAL_URL'])
    if (url.scheme not in {'https', 'http'} or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or url.path != f"/{project['public_ref']}/auth/v1"):
        raise ValueError('Project Auth URL is not canonical')
    url.port
    return urlunsplit((url.scheme, url.netloc, f"/{project['public_ref']}", '', ''))


async def read_client_configuration(conn, application_ref: str, projects_root: pathlib.Path) -> dict:
    project = await conn.fetchrow(
        """
        SELECT p.id, p.name, p.tenant_uuid, p.public_ref,
               p.opaque_keys_activated_at, p.opaque_gateway_ready_at,
               s.id AS slot_id, s.status AS slot_status
        FROM project_api_key_slots s JOIN projects p ON p.id = s.project_id
        WHERE s.application_ref = $1 AND s.kind = 'publishable'
        """, application_ref,
    )
    if project is None:
        raise HTTPException(404, 'Application configuration not found')
    if (project['slot_status'] != 'active'
            or project['opaque_keys_activated_at'] is None
            or project['opaque_gateway_ready_at'] is None):
        raise HTTPException(410, 'Application configuration is unavailable')
    keys = await conn.fetch(
        """
        SELECT k.id, k.expires_at, k.secret_hash, r.ciphertext
        FROM project_api_keys k
        LEFT JOIN project_api_key_reveals r ON r.key_id = k.id
        WHERE k.slot_id = $1 AND (k.expires_at IS NULL OR k.expires_at > now())
          AND (
              (k.status = 'pending' AND k.activate_at <= now() AND k.confirmed_at IS NOT NULL)
              OR (k.status = 'active' AND k.activated_at IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM project_api_keys due WHERE due.slot_id = k.slot_id
                    AND due.status = 'pending' AND due.activate_at <= now()
                    AND due.confirmed_at IS NOT NULL
              ))
          )
        """, project['slot_id'],
    )
    if not keys:
        raise HTTPException(410, 'No valid publishable key for this application')
    if len(keys) != 1 or keys[0]['ciphertext'] is None:
        raise HTTPException(503, 'Canonical publishable key is unavailable')
    key = keys[0]
    plaintext = await decrypt_project_material(
        conn, project_id=project['id'], purpose=f"opaque-api-key-reveal:{key['id']}",
        ciphertext=key['ciphertext'], readonly=True,
    )
    parsed = parse_opaque_key(project['id'], plaintext)
    if parsed.kind != 'publishable' or not hmac.compare_digest(parsed.digest, bytes(key['secret_hash'])):
        raise HTTPException(503, 'Publishable key identity does not match the registry')
    return {
        'supabase_url': project_public_url(project, projects_root),
        'publishable_key': plaintext,
        'key_id': str(key['id']),
        'expires_at': key['expires_at'].isoformat() if key['expires_at'] else None,
    }
