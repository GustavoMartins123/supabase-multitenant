"""Import an offline Studio SQL filesystem snapshot into the control-plane content store."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import struct
import uuid

from migration_files import digest, plain_tree

UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
NAMESPACE = re.compile(rf"^({UUID_PATTERN})__({UUID_PATTERN})(?:__(.+))?$")


def imported_id(parts):
    value = "_".join(parts).encode("utf-8")
    hashed = 0
    for byte in value:
        hashed = ((hashed << 5) - hashed + byte) & 0xffffffff
    if hashed >= 0x80000000:
        hashed -= 0x100000000
    seed = abs(hashed)
    data = bytearray()
    for _ in range(16):
        number = float(seed) * 1103515245 + 12345
        # LuaJIT BitOp converts doubles through the IEEE-754 mantissa, not int().
        seed = struct.unpack('<Q', struct.pack('<d', number + 6755399441055744.0))[0] & 0x7fffffff
        data.append((seed >> 16) & 0xff)
    data[6] = (data[6] & 0x0f) | 0x40
    data[8] = (data[8] & 0x3f) | 0x80
    return uuid.UUID(bytes=bytes(data))


def filesystem_root_id(name):
    """Reconstruct the root ID assigned by the removed Studio filesystem backend."""
    hashed = 0
    for byte in name.encode('ascii'):
        hashed = ((hashed << 5) - hashed + byte) & 0xffffffff
    seed = abs(hashed if hashed < 0x80000000 else hashed - 0x100000000)
    data = bytearray()
    for _ in range(16):
        seed = int(float(seed) * 1103515245 + 12345) & 0x7fffffff
        data.append((seed >> 16) & 0xff)
    data[6] = (data[6] & 0x0f) | 0x40
    data[8] = (data[8] & 0x3f) | 0x80
    return uuid.UUID(bytes=bytes(data))


def plan(directory, *, users, projects):
    plain_tree(directory)
    fingerprint = digest(directory)
    folders, snippets, seen = [], [], set()
    for namespace in sorted(directory.iterdir()):
        if namespace.name == ".gitignore" and namespace.is_file():
            continue
        match = NAMESPACE.fullmatch(namespace.name)
        if not match or not namespace.is_dir():
            raise RuntimeError("Unattributed snippet namespace")
        owner_id, project_id = uuid.UUID(match[1]), uuid.UUID(match[2])
        if owner_id not in users or project_id not in projects:
            raise RuntimeError("Unknown snippet owner or project")
        root_name = match[1] + "__" + match[2]
        folder_name = match[3]
        folder_id = imported_id([root_name, folder_name]) if folder_name else None
        id_scope = str(folder_id) if folder_id else str(filesystem_root_id(root_name))
        if folder_name:
            if folder_id in seen or len(folder_name) > 500:
                raise RuntimeError("Conflicting folder identity")
            seen.add(folder_id)
            folders.append((folder_id, project_id, owner_id, folder_name))
        for file in sorted(namespace.iterdir()):
            if not file.is_file() or not file.name.endswith(".sql"):
                raise RuntimeError("Unsupported snippet snapshot entry")
            name = file.name.replace(".sql", "", 1).replace(".sql", "", 1)
            if not name or len(name) > 500:
                raise RuntimeError("Invalid snippet name")
            sql = file.read_text(encoding="utf-8")
            if len(sql) > 5_000_000:
                raise RuntimeError("Snippet exceeds content contract")
            identity = imported_id([id_scope, name + ".sql"])
            if identity in seen:
                raise RuntimeError("Conflicting snippet identity")
            seen.add(identity)
            timestamp = datetime.fromtimestamp(file.stat().st_mtime, timezone.utc)
            content = json.dumps({"sql": sql, "content_id": str(identity), "schema_version": "1.0"})
            snippets.append((identity, project_id, owner_id, folder_id, name, content, timestamp))
    if digest(directory) != fingerprint:
        raise RuntimeError("Snippet snapshot changed during inspection")
    return folders, snippets, fingerprint


async def import_snapshot(conn, directory):
    async with conn.transaction():
        await conn.execute("LOCK TABLE studio_sql_folders,studio_sql_snippets IN EXCLUSIVE MODE")
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM studio_sql_folders) OR EXISTS(SELECT 1 FROM studio_sql_snippets)"):
            raise RuntimeError("Content store is not empty; refusing to overwrite snippets")
        users = {row["id"] for row in await conn.fetch("SELECT id FROM users")}
        projects = {row["id"] for row in await conn.fetch("SELECT id FROM projects")}
        folders, snippets, fingerprint = plan(directory, users=users, projects=projects)
        await conn.executemany("INSERT INTO studio_sql_folders(id,project_id,owner_id,name) VALUES($1,$2,$3,$4)", folders)
        await conn.executemany("""INSERT INTO studio_sql_snippets(id,project_id,owner_id,folder_id,name,content,inserted_at,updated_at)
            VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$7)""", snippets)
        for identity, project, owner, folder, name, content, timestamp in snippets:
            saved = await conn.fetchrow("SELECT id,project_id,owner_id,folder_id,name,content FROM studio_sql_snippets WHERE id=$1", identity)
            if (saved["project_id"], saved["owner_id"], saved["folder_id"], saved["name"], json.loads(saved["content"])) != (
                    project, owner, folder, name, json.loads(content)):
                raise RuntimeError("Imported snippet verification failed")
        if digest(directory) != fingerprint:
            raise RuntimeError("Snippet snapshot changed during import")
    return len(folders), len(snippets)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snippets-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", required=True,
                        help="Run only during maintenance, using a backed-up offline snapshot")
    args = parser.parse_args()
    import asyncpg
    conn = await asyncpg.connect(os.environ["DB_DSN"])
    try:
        folders, snippets = await import_snapshot(conn, args.snippets_dir)
        print(f"Imported and verified {folders} folders and {snippets} SQL snippets.")
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Content import failed ({type(exc).__name__}); originals preserved.")
        raise SystemExit(1)
