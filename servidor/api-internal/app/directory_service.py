"""Durable complete-directory reconciliation; no individual authorization writes."""
import json
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict

from app.control_plane_service import sync_user_record
from app.directory_transport import read_directory, DirectoryUnavailable
from app.runtime_config import PROJECTS_API_HMAC_SECRET, STUDIO_CACHE_INVALIDATION_URL, STUDIO_CACHE_INVALIDATION_CA_FILE


class DirectoryUser(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: uuid.UUID
    username: str = Field(min_length=1, max_length=128)
    display_name: str | None
    groups: list[str]
    is_active: bool
    source: dict


class DirectorySnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(gt=0, le=9007199254740991)
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    users: list[DirectoryUser] = Field(max_length=10000)


async def reconcile_directory(conn, snapshot: DirectorySnapshot) -> dict:
    ids = [user.id for user in snapshot.users]
    names = [user.username for user in snapshot.users]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise HTTPException(409, 'Duplicate directory identities')
    await conn.execute("SELECT pg_advisory_xact_lock(7243118905412667002)")
    state = await conn.fetchrow('SELECT sequence, revision FROM studio_directory_state WHERE singleton FOR UPDATE')
    if state and snapshot.sequence <= state['sequence']:
        if snapshot.revision != state['revision']:
            raise HTTPException(409, 'Stale directory snapshot')
        # A concurrent read of identical raw YAML proves the same state. Return
        # its persisted projections without writing or reducing the sequence.
        rows = await conn.fetch("SELECT u.*, ARRAY(SELECT group_name FROM user_groups WHERE user_id=u.id ORDER BY group_name) AS groups FROM users u WHERE id=ANY($1::uuid[])", ids)
        return {'revision': state['revision'], 'users': [
            {'id': str(u['id']), 'username': u['authelia_username'], 'groups': u['groups'], 'is_active': u['is_active'], 'email': u['email'], 'picture_url': u['picture_url'], 'profile': json.loads(u['profile_data']) if isinstance(u['profile_data'], str) else u['profile_data'], 'profile_version': u['profile_version'], 'profile_updated_at': u['profile_updated_at'].isoformat() if u['profile_updated_at'] else None}
            for u in rows
        ]}
    synced = []
    for user in snapshot.users:
        synced.append(await sync_user_record(conn, user_id=user.id, username=user.username, display_name=user.display_name, groups=user.groups, is_active=user.is_active, source=user.source))
    absent = await conn.fetch('SELECT id FROM users WHERE NOT(id=ANY($1::uuid[]))', ids)
    for user in absent:
        await conn.execute("INSERT INTO user_group_audit(user_id, group_name, action, old_value, actor_type) SELECT user_id, group_name, 'removed', jsonb_build_object('group', group_name), 'studio_directory' FROM user_groups WHERE user_id=$1", user['id'])
        await conn.execute('DELETE FROM user_groups WHERE user_id=$1', user['id'])
        await conn.execute('UPDATE users SET is_active=false, last_sync_at=now(), updated_at=now() WHERE id=$1', user['id'])
    await conn.execute('INSERT INTO studio_directory_state(singleton, sequence, revision, confirmed_at) VALUES(true,$1,$2,now()) ON CONFLICT(singleton) DO UPDATE SET sequence=EXCLUDED.sequence, revision=EXCLUDED.revision, confirmed_at=now()', snapshot.sequence, snapshot.revision)
    return {'revision': snapshot.revision, 'users': synced}


async def confirm_directory(pool) -> DirectorySnapshot:
    try:
        snapshot = DirectorySnapshot.model_validate(await read_directory(STUDIO_CACHE_INVALIDATION_URL, PROJECTS_API_HMAC_SECRET, STUDIO_CACHE_INVALIDATION_CA_FILE or None))
    except (DirectoryUnavailable, ValueError) as exc:
        raise HTTPException(503, 'Canonical user directory unavailable') from exc
    async with pool.acquire() as conn:
        async with conn.transaction():
            await reconcile_directory(conn, snapshot)
    return snapshot
