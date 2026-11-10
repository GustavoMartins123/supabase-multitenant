"""Internal GoTrue mail templates; defaults remain available without PostgreSQL."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
from collections import OrderedDict
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from policy import validate, origins, PolicyError, POLICY_VERSION

MAX_BODY = 1024 * 1024
MAX_REQUEST = 8 * MAX_BODY  # JSON may escape each Unicode codepoint.
KINDS = (
    "confirmation",
    "invite",
    "magic_link",
    "recovery",
    "email_change",
    "reauthentication",
)
LOGGER = logging.getLogger("mailer-templates")
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def project_key(secret: str, tenant: str) -> str:
    return hmac.new(
        secret.encode(), ("mailer-url-v1:" + tenant).encode(), hashlib.sha256
    ).hexdigest()


def admin_key(secret: str) -> str:
    # Compatibility for callers building test credentials; this is now a
    # dedicated random credential, independent of platform authentication.
    return secret


def draft_digest(body, approved):
    return hashlib.sha256(
        json.dumps(
            {"body": body, "origins": origins(approved), "policy": POLICY_VERSION},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def publication_claims(token, secret):
    try:
        encoded, signature = token.split(".")
        if len(token) > 2048 or not hmac.compare_digest(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest(),
            signature,
        ):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if set(data) != {"tenant", "kind", "actor", "version", "digest", "exp", "jti"}:
            raise ValueError()
        if (
            type(data["exp"]) is not int
            or not time.time() < data["exp"] <= time.time() + 65
        ):
            raise ValueError()
        if not isinstance(data["jti"], str) or len(data["jti"]) != 32:
            raise ValueError()
        return data
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(
            403, "Confirmação de publicação inválida ou expirada"
        ) from None


def valid_key(provided: str, expected: str) -> bool:
    return len(provided) == 64 and hmac.compare_digest(
        provided.encode(), expected.encode()
    )


def migration_signature(secret, scope, kind, version, body):
    """Attest the exact legacy content imported by the host-side migrator."""
    message = json.dumps(
        ["mailer-legacy-v1", scope, kind, version, body],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class Engine:
    def __init__(self, binary=None):
        self.binary = binary or os.getenv(
            "MAILER_TEMPLATE_ENGINE", "/usr/local/bin/template-engine"
        )
        self.slots = asyncio.Semaphore(4)

    async def run(self, *args, payload=None):
        async with self.slots:
            process = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                raw, _ = await asyncio.wait_for(
                    process.communicate(
                        json.dumps(payload, ensure_ascii=True).encode()
                        if payload is not None
                        else None
                    ),
                    timeout=5,
                )
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            result = json.loads(raw)
            if process.returncode:
                raise HTTPException(422, result.get("error", "Go template inválido"))
            return result

    async def render(self, kind, body, *, approved=None, enforce_policy=False):
        if kind not in KINDS:
            raise HTTPException(404, "Tipo de template desconhecido")
        if not isinstance(body, str):
            raise HTTPException(422, "O HTML deve ser uma string UTF-8")
        try:
            size = len(body.encode("utf-8", errors="strict"))
        except UnicodeError:
            raise HTTPException(422, "O HTML deve ser UTF-8") from None
        if not 0 < size <= MAX_BODY:
            raise HTTPException(422, "O HTML deve conter entre 1 byte e 1 MB")
        if enforce_policy:
            try:
                validate(body, approved or [], kind)
            except (PolicyError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from None
        try:
            return (
                await asyncio.wait_for(
                    self.run(payload={"kind": kind, "body": body}), 10
                )
            )["html"]
        except asyncio.TimeoutError:
            raise HTTPException(
                422, "O template excedeu o tempo de renderização"
            ) from None

    async def preview(self, kind, body, approved=None):
        return await self.render(kind, body, approved=approved, enforce_policy=True)


class Templates:
    def __init__(
        self,
        pool,
        defaults,
        engine,
        secret,
        *,
        ttl=60,
        capacity=1024,
        max_cache_bytes=16 * 1024 * 1024,
        admin_secret=None,
        publish_secret=None,
    ):
        self.pool, self.defaults, self.engine, self.secret = (
            pool,
            defaults,
            engine,
            secret,
        )
        self.admin_secret = admin_secret or secret
        self.publish_secret = publish_secret or secret
        self.ttl, self.capacity = ttl, capacity
        self.cache = OrderedDict()
        self.requests = OrderedDict()
        self.cache_bytes = 0
        self.max_cache_bytes = max_cache_bytes

    def throttle(self, tenant, actor, operation):
        key = (tenant, actor, operation)
        now = time.monotonic()
        started, count = self.requests.get(key, (now, 0))
        if now - started >= 60:
            started, count = now, 0
        limit = 30 if operation == "preview" else 12
        if count >= limit:
            raise HTTPException(429, "Muitas alterações; aguarde um minuto")
        self.requests[key] = (started, count + 1)
        self.requests.move_to_end(key)
        while len(self.requests) > 4096:
            self.requests.popitem(last=False)

    def cache_pop(self, key):
        previous = self.cache.pop(key, None)
        if previous is not None:
            self.cache_bytes -= sys.getsizeof(previous[1])

    def cache_put(self, key, body, source):
        self.cache_pop(key)
        self.cache[key] = (time.monotonic() + self.ttl, body, source)
        self.cache_bytes += sys.getsizeof(body)
        self.cache.move_to_end(key)
        while (
            len(self.cache) > self.capacity or self.cache_bytes > self.max_cache_bytes
        ):
            self.cache_pop(next(iter(self.cache)))

    async def resolve(self, tenant, kind):
        key = (tenant, kind)
        cached = self.cache.get(key)
        if cached and cached[0] > time.monotonic():
            self.cache.move_to_end(key)
            return cached[1], cached[2]
        try:
            async with asyncio.timeout(2):
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """SELECT t.body, t.allowed_origins, t.policy_version, t.published_version,
                           t.migration_signature, d.body AS default_body, d.version AS default_version,
                           d.migration_signature AS default_signature
                           FROM projects p LEFT JOIN mailer_template t
                           ON t.project_id=p.id AND t.kind=$2
                           LEFT JOIN mailer_template_default d ON d.kind=$2 WHERE p.tenant_uuid=$1""",
                        uuid.UUID(tenant),
                        kind,
                    )
            if row is None:
                self.cache_pop(key)
                raise HTTPException(404, "Projeto desconhecido")
            body = row["body"]
            if body is not None and row["policy_version"] != POLICY_VERSION:
                raise HTTPException(422, "Política de publicação desatualizada")
            source = "override" if body is not None else "default"
            if body is not None:
                if row["migration_signature"]:
                    await self.check_migration(
                        tenant,
                        kind,
                        body,
                        row["published_version"],
                        row["migration_signature"],
                        cached,
                    )
                elif cached is None or cached[1] != body:
                    await self.engine.preview(
                        kind, body, decode_origins(row["allowed_origins"])
                    )
            elif row["default_body"] is not None:
                body = row["default_body"]
                await self.check_migration(
                    "platform",
                    kind,
                    body,
                    row["default_version"],
                    row["default_signature"],
                    cached,
                )
            else:
                body = self.defaults[kind]
            # An administrator may have saved while the database read or Go
            # validation was in flight. Never overwrite that newer cache entry.
            latest = self.cache.get(key)
            if latest is not cached and latest is not None:
                return latest[1], latest[2]
            self.cache_put(key, body, source)
            return body, source
        except HTTPException as exc:
            if exc.status_code == 404:
                raise
            # A damaged override must never replace the last validated value.
            LOGGER.warning("Invalid saved mail template; serving fallback")
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
            LOGGER.warning("Mailer database unavailable; serving fallback")
        cached = self.cache.get(key) or cached
        if cached:
            self.cache_put(key, cached[1], "last_good")
            # Retry the database shortly; do not extend stale data by a minute.
            if key in self.cache:
                self.cache[key] = (time.monotonic() + 5, cached[1], "last_good")
            return cached[1], "last_good"
        return self.defaults[kind], "default"

    async def check_migration(self, scope, kind, body, version, signature, cached=None):
        expected = migration_signature(self.publish_secret, scope, kind, version, body)
        if not isinstance(signature, str) or not valid_key(signature, expected):
            raise HTTPException(
                422, "O conteúdo migrado não corresponde ao legado registrado"
            )
        if cached is None or cached[1] != body:
            return await self.engine.render(kind, body)

    async def preview(self, tenant, kind, body, approved):
        async with self.pool.acquire() as conn:
            project = await self.project(conn, tenant)
            row = await conn.fetchrow(
                "SELECT * FROM mailer_template WHERE project_id=$1 AND kind=$2", project, kind
            )
            if row and row["body"] == body and row["migration_signature"] and row["policy_version"] == POLICY_VERSION:
                return await self.check_migration(tenant, kind, body, row["published_version"], row["migration_signature"])
            default = await conn.fetchrow("SELECT * FROM mailer_template_default WHERE kind=$1", kind)
            if default and default["body"] == body:
                return await self.check_migration("platform", kind, body, default["version"], default["migration_signature"])
        return await self.engine.preview(kind, body, approved)

    async def default_for(self, conn, kind):
        row = await conn.fetchrow(
            "SELECT * FROM mailer_template_default WHERE kind=$1", kind
        )
        if row is None:
            return self.defaults[kind]
        await self.check_migration(
            "platform", kind, row["body"], row["version"], row["migration_signature"]
        )
        return row["body"]

    async def project(self, conn, tenant):
        row = await conn.fetchrow(
            "SELECT id FROM projects WHERE tenant_uuid=$1", uuid.UUID(tenant)
        )
        if row is None:
            raise HTTPException(404, "Projeto desconhecido")
        return row["id"]

    def describe(self, kind, row=None, default_body=None):
        default_body = self.defaults[kind] if default_body is None else default_body
        published = row["body"] if row and row["body"] is not None else default_body
        draft_exists = bool(row and row["draft_exists"])
        draft = (
            row["draft_body"]
            if draft_exists and row["draft_body"] is not None
            else default_body
        )
        return {
            "kind": kind,
            "body": draft if draft_exists else published,
            "published_body": published,
            "default_body": default_body,
            "source": "override" if row and row["body"] is not None else "default",
            "version": row["version"] if row else 0,
            "published_version": row["published_version"] if row else 0,
            "has_draft": draft_exists,
            "draft_default": draft_exists and row["draft_body"] is None,
            "draft_digest": (
                draft_digest(row["draft_body"], decode_origins(row["draft_origins"]))
                if draft_exists
                else None
            ),
            "updated_at": row["updated_at"].isoformat() if row else None,
            "updated_by": row["updated_by"] if row else None,
        }

    async def list(self, tenant, approved=None):
        async with self.pool.acquire() as conn:
            project = await self.project(conn, tenant)
            rows = {
                r["kind"]: r
                for r in await conn.fetch(
                    "SELECT * FROM mailer_template WHERE project_id=$1", project
                )
            }
            defaults = {kind: await self.default_for(conn, kind) for kind in KINDS}
        described = [
            self.describe(kind, rows.get(kind), defaults[kind]) for kind in KINDS
        ]
        # A host-side import writes directly to PostgreSQL. An authenticated
        # listing invalidates older cache entries before the runtime cutover.
        for row in described:
            key = (tenant, row["kind"])
            cached = self.cache.get(key)
            if cached and cached[1] != row["published_body"]:
                self.cache_pop(key)
        return {
            "templates": described,
            "allowed_origins": origins(approved or []),
            "cache_max_age_seconds": self.ttl,
        }

    async def history(self, tenant, kind):
        async with self.pool.acquire() as conn:
            project = await self.project(conn, tenant)
            rows = await conn.fetch(
                """SELECT version, action, updated_at, updated_by FROM mailer_template_version
                   WHERE project_id=$1 AND kind=$2 ORDER BY version DESC LIMIT 50""",
                project,
                kind,
            )
        return {
            "versions": [
                {**dict(row), "updated_at": row["updated_at"].isoformat()}
                for row in rows
            ]
        }

    async def history_version(self, tenant, kind, version):
        async with self.pool.acquire() as conn:
            project = await self.project(conn, tenant)
            row = await conn.fetchrow(
                """SELECT version, body, action, updated_at, updated_by FROM mailer_template_version
                   WHERE project_id=$1 AND kind=$2 AND version=$3""",
                project,
                kind,
                version,
            )
        if row is None:
            raise HTTPException(404, "Versão não encontrada")
        return {**dict(row), "updated_at": row["updated_at"].isoformat()}

    async def save(
        self,
        tenant,
        kind,
        payload,
        actor,
        *,
        approved=None,
        reset=False,
        action="draft",
    ):
        if set(payload) - ({"version"} if reset else {"version", "body"}):
            raise HTTPException(422, "Campos inesperados no rascunho")
        version = payload.get("version")
        if type(version) is not int or not 0 <= version <= 2147483646:
            raise HTTPException(422, "Informe a versão atual do template")
        approved = origins(approved or [])
        body = None if reset else payload.get("body")
        if not reset:
            if action == "import":
                try:
                    if (
                        not isinstance(body, str)
                        or not 0
                        < len(body.encode("utf-8", errors="strict"))
                        <= MAX_BODY
                    ):
                        raise ValueError()
                except (ValueError, UnicodeError):
                    raise HTTPException(
                        422, "HTML legado inválido ou excessivo"
                    ) from None
            else:
                await self.engine.preview(kind, body, approved)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                project = await self.project(conn, tenant)
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"mailer:{project}:{kind}",
                )
                current = await conn.fetchval(
                    "SELECT version FROM mailer_template WHERE project_id=$1 AND kind=$2",
                    project,
                    kind,
                )
                if (current or 0) != version:
                    raise HTTPException(
                        409, "O template mudou. Recarregue antes de salvar novamente."
                    )
                row = await conn.fetchrow(
                    """INSERT INTO mailer_template(project_id,kind,version,updated_by,draft_body,draft_exists,draft_origins,policy_version)
                       VALUES($1,$2,$4,$5,$3,true,$6::jsonb,$7) ON CONFLICT(project_id,kind) DO UPDATE
                       SET draft_body=EXCLUDED.draft_body,draft_exists=true,draft_origins=EXCLUDED.draft_origins,
                           version=EXCLUDED.version,updated_by=EXCLUDED.updated_by,updated_at=now()
                       RETURNING *""",
                    project,
                    kind,
                    body,
                    version + 1,
                    actor,
                    json.dumps(approved),
                    POLICY_VERSION,
                )
                await conn.execute(
                    """INSERT INTO mailer_template_version(project_id,kind,body,version,updated_by,action)
                       VALUES($1,$2,$3,$4,$5,$6)""",
                    project,
                    kind,
                    body,
                    version + 1,
                    actor,
                    "draft_default" if reset else action,
                )
                default_body = await self.default_for(conn, kind)
        # Saving a draft never changes the published cache.
        return self.describe(kind, row, default_body)

    async def publish(self, tenant, kind, payload, actor, proof, approved):
        if (
            set(payload) != {"version", "draft_digest"}
            or type(payload.get("version")) is not int
        ):
            raise HTTPException(422, "Versão e identificação do rascunho obrigatórias")
        claims = publication_claims(proof, self.publish_secret)
        expected = {
            "tenant": tenant,
            "kind": kind,
            "actor": actor,
            "version": payload["version"],
            "digest": payload["draft_digest"],
        }
        if any(claims[key] != value for key, value in expected.items()):
            raise HTTPException(403, "A confirmação não corresponde a este rascunho")
        approved = origins(approved)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                project = await self.project(conn, tenant)
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"mailer:{project}:{kind}",
                )
                current = await conn.fetchrow(
                    "SELECT * FROM mailer_template WHERE project_id=$1 AND kind=$2 FOR UPDATE",
                    project,
                    kind,
                )
                if (
                    not current
                    or not current["draft_exists"]
                    or current["version"] != payload["version"]
                    or draft_digest(current["draft_body"], approved)
                    != payload["draft_digest"]
                    or decode_origins(current["draft_origins"]) != approved
                ):
                    raise HTTPException(
                        409,
                        "O rascunho ou os destinos mudaram. Recarregue e confirme novamente.",
                    )
                body = current["draft_body"]
                if body is not None:
                    await self.engine.preview(kind, body, approved)
                await conn.execute(
                    "DELETE FROM mailer_template_publication_grant WHERE expires_at<now()"
                )
                used = await conn.fetchval(
                    """INSERT INTO mailer_template_publication_grant(jti,expires_at) VALUES($1,$2)
                    ON CONFLICT DO NOTHING RETURNING jti""",
                    claims["jti"],
                    dt.datetime.fromtimestamp(claims["exp"], tz=dt.timezone.utc),
                )
                if used is None:
                    raise HTTPException(403, "Confirmação já utilizada")
                version = current["version"] + 1
                row = await conn.fetchrow(
                    """UPDATE mailer_template SET body=$3,version=$4,published_version=$4,
                    allowed_origins=$5::jsonb,policy_version=$6,migration_signature=NULL,
                    draft_exists=false,draft_body=NULL,draft_origins='[]',
                    updated_by=$7,updated_at=now() WHERE project_id=$1 AND kind=$2 RETURNING *""",
                    project,
                    kind,
                    body,
                    version,
                    json.dumps(approved),
                    POLICY_VERSION,
                    actor,
                )
                await conn.execute(
                    """INSERT INTO mailer_template_version(project_id,kind,body,version,updated_by,action)
                    VALUES($1,$2,$3,$4,$5,$6)""",
                    project,
                    kind,
                    body,
                    version,
                    actor,
                    "publish" if body is not None else "publish_default",
                )
                default_body = await self.default_for(conn, kind)
        self.cache_put(
            (tenant, kind),
            body if body is not None else default_body,
            "override" if body is not None else "default",
        )
        return self.describe(kind, row, default_body)


def decode_origins(value):
    return origins(json.loads(value) if isinstance(value, str) else value)


def credential(name):
    path = Path(
        os.getenv("MAILER_TEMPLATE_" + name + "_FILE", "/run/secrets/mailer/" + name)
    )
    value = path.read_text().strip()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise RuntimeError("Invalid dedicated mailer credential")
    return value


def create_app(templates=None):
    @asynccontextmanager
    async def lifespan(app):
        if templates is not None:
            app.state.templates = templates
            yield
            return
        secret = credential("URL_SECRET")
        admin_secret = credential("ADMIN_KEY")
        publish_secret = credential("PUBLISH_KEY")
        if len({secret, admin_secret, publish_secret}) != 3 or any(
            len(key) != 64 for key in (secret, admin_secret, publish_secret)
        ):
            raise RuntimeError(
                "Mailer credentials must be distinct 32-byte random keys"
            )
        engine = Engine()
        defaults = await engine.run("defaults")
        for kind in KINDS:
            await engine.preview(kind, defaults[kind])
        # min_size=0 deliberately allows booting with the database offline.
        pool = await asyncpg.create_pool(
            os.environ["DB_DSN"],
            password=credential("DB_PASSWORD"),
            min_size=0,
            max_size=5,
            timeout=2,
            command_timeout=5,
        )
        ttl = int(os.getenv("MAILER_TEMPLATE_CACHE_SECONDS", "60"))
        if not 1 <= ttl <= 60:
            raise RuntimeError("MAILER_TEMPLATE_CACHE_SECONDS must be between 1 and 60")
        app.state.templates = Templates(
            pool,
            defaults,
            engine,
            secret,
            ttl=ttl,
            admin_secret=admin_secret,
            publish_secret=publish_secret,
        )
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    if templates is not None:
        app.state.templates = templates

    @app.middleware("http")
    async def bounds(request, call_next):
        length = request.headers.get("content-length", "0")
        if not length.isdecimal() or int(length) > MAX_REQUEST:
            return JSONResponse(
                {"detail": "Upload excede o limite"}, status_code=413, headers=NO_STORE
            )
        response = await call_next(request)
        response.headers.update(NO_STORE)
        return response

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    def checked(tenant, kind=None):
        try:
            if str(uuid.UUID(tenant)) != tenant:
                raise ValueError()
        except ValueError:
            raise HTTPException(404, "Projeto desconhecido") from None
        if kind is not None and kind not in KINDS:
            raise HTTPException(404, "Tipo de template desconhecido")

    @app.get("/mailer/{tenant}/{kind}")
    async def mailer(tenant: str, kind: str, request: Request):
        checked(tenant, kind)
        service = app.state.templates
        if not valid_key(
            request.query_params.get("k", ""), project_key(service.secret, tenant)
        ):
            raise HTTPException(403, "Acesso negado")
        body, source = await service.resolve(tenant, kind)
        return HTMLResponse(
            body,
            headers={
                "X-Template-Source": source,
                "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
                "Referrer-Policy": "no-referrer",
            },
        )

    async def admin(request, tenant, kind=None):
        checked(tenant, kind)
        service = app.state.templates
        if not valid_key(
            request.headers.get("X-Mailer-Admin", ""), service.admin_secret
        ):
            raise HTTPException(403, "Acesso negado")
        if request.method != "GET":
            service.throttle(
                tenant,
                request.headers.get("X-Mailer-Actor", ""),
                "preview" if request.url.path.endswith("/preview") else "mutation",
            )
        return service

    async def payload(request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REQUEST:
                raise HTTPException(413, "Upload excede o limite")
        try:
            value = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError):
            raise HTTPException(422, "JSON UTF-8 inválido") from None
        if not isinstance(value, dict):
            raise HTTPException(422, "Objeto JSON obrigatório")
        return value

    @app.get("/internal/projects/{tenant}/mailer-templates")
    async def list_templates(tenant: str, request: Request):
        service = await admin(request, tenant)
        return await service.list(tenant, request_origins(request))

    @app.get("/internal/projects/{tenant}/mailer-templates/{kind}/history")
    async def history(tenant: str, kind: str, request: Request):
        service = await admin(request, tenant, kind)
        return await service.history(tenant, kind)

    @app.get("/internal/projects/{tenant}/mailer-templates/{kind}/history/{version}")
    async def history_version(tenant: str, kind: str, version: int, request: Request):
        service = await admin(request, tenant, kind)
        if not 1 <= version <= 2147483647:
            raise HTTPException(404, "Versão não encontrada")
        return await service.history_version(tenant, kind, version)

    @app.post("/internal/projects/{tenant}/mailer-templates/{kind}/preview")
    async def preview(tenant: str, kind: str, request: Request):
        service = await admin(request, tenant, kind)
        data = await payload(request)
        return {
            "html": await service.preview(
                tenant, kind, data.get("body"), request_origins(request)
            )
        }

    @app.post("/internal/projects/{tenant}/mailer-templates/{kind}/import")
    async def import_draft(tenant: str, kind: str, request: Request):
        service = await admin(request, tenant, kind)
        if request.headers.get("X-Mailer-Actor") != "legacy-migration":
            raise HTTPException(403, "Importação restrita ao migrador")
        return await service.save(
            tenant,
            kind,
            await payload(request),
            "legacy-migration",
            approved=request_origins(request),
            action="import",
        )

    @app.post("/internal/projects/{tenant}/mailer-templates/{kind}/publish")
    async def publish(tenant: str, kind: str, request: Request):
        service = await admin(request, tenant, kind)
        actor = request.headers.get("X-Mailer-Actor", "").strip()
        if not actor or len(actor) > 256:
            raise HTTPException(422, "Autor obrigatório")
        try:
            return await service.publish(
                tenant,
                kind,
                await payload(request),
                actor,
                request.headers.get("X-Mailer-Publication", ""),
                request_origins(request),
            )
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
            raise HTTPException(
                503, "Publicação indisponível; recarregue antes de tentar novamente"
            ) from None

    @app.api_route(
        "/internal/projects/{tenant}/mailer-templates/{kind}", methods=["PUT", "DELETE"]
    )
    async def save(tenant: str, kind: str, request: Request):
        service = await admin(request, tenant, kind)
        actor = request.headers.get("X-Mailer-Actor", "").strip()
        if not actor or len(actor) > 256:
            raise HTTPException(422, "Autor da alteração obrigatório")
        data = await payload(request)
        try:
            return await service.save(
                tenant,
                kind,
                data,
                actor,
                reset=request.method == "DELETE",
                approved=request_origins(request),
            )
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
            raise HTTPException(
                503, "Banco indisponível; o template não foi alterado"
            ) from None

    return app


def request_origins(request):
    try:
        return origins(json.loads(request.headers.get("X-Mailer-Origins", "[]")))
    except (ValueError, PolicyError):
        raise HTTPException(422, "Política de destinos inválida") from None


app = create_app()
