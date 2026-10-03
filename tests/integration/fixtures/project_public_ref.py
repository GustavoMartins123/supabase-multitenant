"""Validate the identity contract on a disposable PostgreSQL, never an installation."""

from __future__ import annotations

import asyncio
import ast
from dataclasses import replace
import os
from pathlib import Path
import uuid

import asyncpg

from app.project_public_ref import (
    PublicProjectNotFound,
    generate_public_ref,
    resolve_public_project,
)
from app.schema_migrations import SchemaMigrationError, apply_migrations, discover_migrations


def project_insert_sql(function_name: str) -> str:
    path = Path(__file__).resolve().parents[3] / "servidor/api-internal/app/routers/projects.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in module.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name)
    statements = [node.args[0].value for node in ast.walk(function)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "execute" and node.args
                  and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str)
                  and "INSERT INTO projects(" in node.args[0].value]
    assert len(statements) == 1
    return statements[0]


async def expect_constraint(conn, query, *args, error) -> None:
    try:
        async with conn.transaction():
            await conn.execute(query, *args)
    except error:
        return
    raise AssertionError(f"Expected {error.__name__}")


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DB_DSN"])
    try:
        if await conn.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"):
            raise RuntimeError("Empty disposable control-plane database required")
        catalog = discover_migrations()
        assert catalog[-1].name == "project_public_ref"
        await apply_migrations(conn, migrations=catalog[:-1])
        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users(id, authelia_username) VALUES($1, 'fixture_admin')", user_id
        )
        identities = [(uuid.uuid4(), uuid.uuid4(), "source_project"),
                      (uuid.uuid4(), uuid.uuid4(), "abcdefghijklmnopqrst")]
        for project_id, tenant_id, name in identities:
            await conn.execute(
                """INSERT INTO projects(id, tenant_uuid, name, owner_id, display_name,
                   anon_key, service_role, config_token)
                   VALUES($1, $2, $3, $4, 'Original', 'anon', 'service', 'config')""",
                project_id, tenant_id, name, user_id,
            )
            await conn.execute(
                "INSERT INTO project_members(project_id, user_id, role) VALUES($1,$2,'admin')",
                project_id, user_id,
            )
        before = await conn.fetch("SELECT * FROM projects ORDER BY id")
        collision_migration = replace(
            catalog[-1],
            sql=catalog[-1].sql.replace(
                "byte_value := get_byte(entropy, position);", "byte_value := 0;"
            ),
        )
        try:
            await apply_migrations(conn, migrations=(*catalog[:-1], collision_migration))
        except SchemaMigrationError:
            pass
        else:
            raise AssertionError("Colliding backfill did not fail")
        assert await conn.fetchval(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_schema='public' AND table_name='projects' AND column_name='public_ref'"""
        ) == 0
        assert before == await conn.fetch("SELECT * FROM projects ORDER BY id")
        print("PASS: colliding backfill fails closed and rolls back schema, identity and migration ledger")
        applied = await apply_migrations(conn)
        assert [m.version for m in applied] == [catalog[-1].version]
        after = await conn.fetch("SELECT * FROM projects ORDER BY id")
        for original, migrated in zip(before, after):
            assert dict(original) == {k: v for k, v in migrated.items() if k != "public_ref"}
            assert len(migrated["public_ref"]) == 20
            assert migrated["public_ref"].isascii() and migrated["public_ref"].islower()
            assert (await resolve_public_project(conn, migrated["public_ref"]))["id"] == migrated["id"]
        assert len({r["public_ref"] for r in after}) == len(after)
        assert await conn.fetchval("SELECT count(*) FROM project_members") == 2
        assert await apply_migrations(conn) == []
        assert after == await conn.fetch("SELECT * FROM projects ORDER BY id")
        print("PASS: backfill preserves every existing project field and membership; ledger rerun is stable")

        source = after[0]
        created_ref, cloned_ref = generate_public_ref(), generate_public_ref()
        assert created_ref != cloned_ref and cloned_ref != source["public_ref"]
        created_id, clone_id = uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            project_insert_sql("create_project"),
            created_id, "created_project", user_id, "medium", created_ref,
        )
        await conn.execute(
            project_insert_sql("duplicate_project"),
            clone_id, "cloned_project", user_id, source["id"], cloned_ref,
        )
        created = await resolve_public_project(conn, created_ref)
        cloned = await resolve_public_project(conn, cloned_ref)
        assert created["id"] == created_id and created["tenant_uuid"] == created_id
        assert cloned["id"] == clone_id and cloned["tenant_uuid"] == clone_id
        assert cloned["resource_profile"] == source["resource_profile"]
        print("PASS: create and duplicate allocate independent UUIDs and public references")

        for invalid in (None, "", "a" * 19, "a" * 21, "A" * 20,
                        "a" * 19 + "1", "a" * 19 + "á", "a" * 20 + "\n"):
            await expect_constraint(
                conn, "UPDATE projects SET public_ref=$1 WHERE id=$2", invalid, clone_id,
                error=asyncpg.NotNullViolationError if invalid is None else asyncpg.CheckViolationError,
            )
        await expect_constraint(
            conn, "UPDATE projects SET public_ref=$1 WHERE id=$2", created_ref, clone_id,
            error=asyncpg.UniqueViolationError,
        )
        assert (await resolve_public_project(conn, cloned_ref))["id"] == clone_id
        print("PASS: database rejects missing, malformed and duplicate references; failed changes roll back")

        await conn.execute("UPDATE projects SET display_name='Changed title' WHERE id=$1", clone_id)
        assert (await resolve_public_project(conn, cloned_ref))["display_name"] == "Changed title"
        snapshot = dict(await conn.fetchrow("SELECT * FROM projects WHERE id=$1", clone_id))
        next_ref = generate_public_ref()
        await conn.execute("UPDATE projects SET public_ref=$1 WHERE id=$2", next_ref, clone_id)
        changed = dict(await conn.fetchrow("SELECT * FROM projects WHERE id=$1", clone_id))
        assert changed == {**snapshot, "public_ref": next_ref}
        assert (await resolve_public_project(conn, next_ref))["id"] == clone_id
        for absent in (cloned_ref, "abcdefghijklmnopqrst"):
            try:
                await resolve_public_project(conn, absent)
            except PublicProjectNotFound:
                pass
            else:
                raise AssertionError("Old reference or infrastructure name was resolved")
        print("PASS: display name preserves address; ref-only database change preserves identity and rejects old ref/name lookup")
        print("Public-reference schema contract validated (not a gateway/lifecycle cutover test)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
