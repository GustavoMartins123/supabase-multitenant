"""Host-invoked legacy import. Deliberately has no HTTP route."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import asyncpg
from fastapi import HTTPException

from policy import POLICY_VERSION
from service import Engine, KINDS, credential, migration_signature


async def import_templates(pool, engine, secret, payload):
    defaults = {**(await engine.run("defaults")), **payload["defaults"]}
    if set(defaults) != set(KINDS):
        raise ValueError("Tipos de templates padrão inválidos")
    # These files are already in production. Preserve their HTML exactly, while
    # still requiring valid UTF-8, bounded size and executable Go templates.
    for kind, body in defaults.items():
        await engine.render(kind, body)
    for project in payload["projects"]:
        uuid.UUID(project["tenant"])
        for kind, body in project["templates"].items():
            if kind not in KINDS:
                raise ValueError("Tipo de template legado inválido")
            if body is not None:
                await engine.render(kind, body)

    imported = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('mailer:legacy-migration',0))"
            )
            for kind, body in defaults.items():
                existing = await conn.fetchrow(
                    "SELECT * FROM mailer_template_default WHERE kind=$1", kind
                )
                signature = migration_signature(secret, "platform", kind, 1, body)
                if existing:
                    if (
                        existing["body"] != body
                        or existing["migration_signature"] != signature
                    ):
                        raise ValueError(
                            "O padrão já registrado difere de auth_template: " + kind
                        )
                    continue
                await conn.execute(
                    """INSERT INTO mailer_template_default(kind,body,version,migration_signature,updated_by)
                    VALUES($1,$2,1,$3,'legacy-migration')""",
                    kind,
                    body,
                    signature,
                )
            for project in payload["projects"]:
                tenant = str(uuid.UUID(project["tenant"]))
                project_id = await conn.fetchval(
                    "SELECT id FROM projects WHERE tenant_uuid=$1 AND name=$2",
                    uuid.UUID(tenant),
                    project["name"],
                )
                if project_id is None:
                    raise ValueError(
                        "Projeto e identidade não correspondem ao cadastro: "
                        + project["name"]
                    )
                for kind, body in sorted(project["templates"].items()):
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                        f"mailer:{project_id}:{kind}",
                    )
                    current = await conn.fetchrow(
                        "SELECT * FROM mailer_template WHERE project_id=$1 AND kind=$2 FOR UPDATE",
                        project_id,
                        kind,
                    )
                    if current:
                        if current["published_version"] > 0 and current["body"] == body:
                            # Retain any newer Studio draft as well as its audit.
                            continue
                        legacy_draft = (
                            current["published_version"] == 0
                            and current["draft_exists"]
                            and current["draft_body"]
                            == (body if body is not None else defaults[kind])
                            and current["updated_by"]
                            in {"legacy-migration", "security-migration"}
                        )
                        if not legacy_draft:
                            raise ValueError(
                                "Studio já contém outra edição; nenhum conteúdo foi sobrescrito: "
                                + project["name"]
                                + "/"
                                + kind
                            )
                    version = (current["version"] if current else 0) + 1
                    signature = (
                        migration_signature(secret, tenant, kind, version, body)
                        if body is not None
                        else None
                    )
                    await conn.execute(
                        """INSERT INTO mailer_template(project_id,kind,body,version,published_version,updated_by,
                            policy_version,migration_signature)
                        VALUES($1,$2,$3,$4,$4,'legacy-migration',$5,$6)
                        ON CONFLICT(project_id,kind) DO UPDATE SET body=EXCLUDED.body,version=EXCLUDED.version,
                            published_version=EXCLUDED.published_version,updated_by=EXCLUDED.updated_by,
                            policy_version=EXCLUDED.policy_version,migration_signature=EXCLUDED.migration_signature,
                            draft_exists=false,draft_body=NULL,draft_origins='[]',allowed_origins='[]',updated_at=now()""",
                        project_id,
                        kind,
                        body,
                        version,
                        POLICY_VERSION,
                        signature,
                    )
                    await conn.execute(
                        """INSERT INTO mailer_template_version(project_id,kind,body,version,updated_by,action)
                        VALUES($1,$2,$3,$4,'legacy-migration',$5)""",
                        project_id,
                        kind,
                        body if body is not None else defaults[kind],
                        version,
                        "import_active" if body is not None else "import_default",
                    )
                    imported += 1
    return {"imported": imported, "projects": len(payload["projects"])}


async def main():
    payload = json.load(sys.stdin)
    pool = await asyncpg.create_pool(
        os.environ["DB_DSN"],
        password=credential("DB_PASSWORD"),
        min_size=1,
        max_size=1,
        command_timeout=10,
    )
    try:
        print(
            json.dumps(
                await import_templates(
                    pool, Engine(), credential("PUBLISH_KEY"), payload
                )
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
    except HTTPException:
        print(
            json.dumps(
                {
                    "error": "Template legado inválido; verifique UTF-8, tamanho e sintaxe Go. Nenhuma alteração foi aplicada."
                }
            )
        )
        sys.exit(1)
    except Exception:
        # Docker errors must not print templates, database credentials or keys.
        print(
            "Importação do legado recusada; nenhuma alteração da transação foi aplicada.",
            file=sys.stderr,
        )
        sys.exit(1)
