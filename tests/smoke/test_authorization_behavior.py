"""Autorizacao ponta a ponta: app real, schema real, cada teste afirma o que
um usuario NAO pode alcancar.

Requer CONTROL_PLANE_TEST_DSN; sem ela os testes sao pulados. Cada execucao
cria e derruba um banco proprio, sem tocar o apontado pela DSN.

    bash tools/test_postgres.sh start
    CONTROL_PLANE_TEST_DSN=... python -m pytest tests/smoke/test_authorization_behavior.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sys
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

ADMIN_DSN = os.environ.get("CONTROL_PLANE_TEST_DSN", "").strip()

GATEWAY_SECRET = "1" * 64
PROJECTS_API_SECRET = "2" * 64
ANALYTICS_SECRET = "3" * 64
NGINX_HMAC_SECRET = "n" * 48


def _seed_environment() -> None:
    """runtime_config valida tudo isto no import; precisa vir antes da app."""
    defaults = {
        "DB_DSN": "postgresql://placeholder:placeholder@localhost:5432/placeholder",
        "PROJECT_SECRETS_MASTER_KEY": base64.urlsafe_b64encode(b"0" * 32).decode(),
        "PG_META_CRYPTO_KEY": base64.urlsafe_b64encode(b"1" * 32).decode(),
        "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"2" * 32).decode(),
        "NGINX_HMAC_SECRET": NGINX_HMAC_SECRET,
        "NGINX_SHARED_TOKEN": "t" * 32,
        "STUDIO_GATEWAY_HMAC_SECRET": GATEWAY_SECRET,
        "PROJECTS_API_HMAC_SECRET": PROJECTS_API_SECRET,
        "STUDIO_ANALYTICS_HMAC_SECRET": ANALYTICS_SECRET,
        "LOGFLARE_PRIVATE_ACCESS_TOKEN": "logflare-test",
        "HOST_AGENT_HMAC_SECRET": "host-agent-test",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class AuthorizationBehaviorTest(unittest.IsolatedAsyncioTestCase):

    database: str
    dsn: str

    @classmethod
    def setUpClass(cls):
        if not ADMIN_DSN:
            raise unittest.SkipTest(
                "defina CONTROL_PLANE_TEST_DSN para rodar os testes de autorizacao"
            )
        cls.database = f"authz_test_{secrets.token_hex(6)}"
        cls.dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + cls.database
        _seed_environment()
        # runtime_config le DB_DSN no import; a app so pode ser importada depois.
        os.environ["DB_DSN"] = cls.dsn
        asyncio.run(cls._create_database())

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "database", None):
            asyncio.run(cls._drop_database())

    @classmethod
    async def _create_database(cls):
        import asyncpg

        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            await conn.execute(f'CREATE DATABASE "{cls.database}"')
        finally:
            await conn.close()

        from app.schema_migrations import apply_migrations

        conn = await asyncpg.connect(cls.dsn)
        try:
            await apply_migrations(conn)
        finally:
            await conn.close()

    @classmethod
    async def _drop_database(cls):
        import asyncpg

        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1",
                cls.database,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{cls.database}"')
        finally:
            await conn.close()

    async def asyncSetUp(self):
        import asyncpg

        from app import database as database_module

        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)
        database_module._pool = self.pool
        await self._seed_fixture()

        from app.asgi import app

        self.app = app

    async def asyncTearDown(self):
        from app import database as database_module

        async with self.pool.acquire() as conn:
            for table in (
                "project_members",
                "user_groups",
                "projects",
                "users",
                "internal_hmac_nonces",
            ):
                await conn.execute(f"TRUNCATE {table} CASCADE")
        database_module._pool = None
        await self.pool.close()

    async def _seed_fixture(self):
        self.owner = uuid.uuid4()
        self.admin2 = uuid.uuid4()
        self.admin3 = uuid.uuid4()
        self.ex_member = uuid.uuid4()
        self.outsider = uuid.uuid4()
        self.project_a = uuid.uuid4()

        async with self.pool.acquire() as conn:
            for user_id, name in (
                (self.owner, "owner"),
                (self.admin2, "admin2"),
                (self.admin3, "admin3"),
                (self.ex_member, "exmember"),
                (self.outsider, "outsider"),
            ):
                await conn.execute(
                    "INSERT INTO users(id, authelia_username, display_name, "
                    "is_active, source) VALUES($1, $2, $2, true, 'test')",
                    user_id,
                    name,
                )
            await conn.execute(
                "INSERT INTO projects(id, name, owner_id) VALUES($1, 'projeto_a', $2)",
                self.project_a,
                self.owner,
            )
            for user_id, role in (
                (self.owner, "admin"),
                (self.admin2, "admin"),
                (self.admin3, "admin"),
                (self.ex_member, "member"),
            ):
                await conn.execute(
                    "INSERT INTO project_members(project_id, user_id, role) "
                    "VALUES($1, $2, $3)",
                    self.project_a,
                    user_id,
                    role,
                )

    def user_token(self, user_id: uuid.UUID) -> str:
        from app.security_tokens import USER_TOKEN_AUDIENCE

        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "aud": USER_TOKEN_AUDIENCE,
            "jti": base64url(secrets.token_bytes(16)),
            "iat": now,
            "exp": now + 300,
            "login_session": base64url(secrets.token_bytes(32)),
        }
        encoded = base64url(json.dumps(payload).encode())
        signature = hmac.new(
            NGINX_HMAC_SECRET.encode(), encoded.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"v1.{encoded}.{signature}"

    def signed_headers(self, method: str, path: str, actor, body: bytes) -> dict:
        from app.internal_hmac import build_internal_hmac_headers

        headers = build_internal_hmac_headers(
            GATEWAY_SECRET,
            method,
            f"https://api.local{path}",
            body,
            service="studio-nginx",
        )
        if actor is not None:
            headers["X-User-Token"] = self.user_token(actor)
        if body:
            headers["Content-Type"] = "application/json"
        return headers

    async def request(
        self, method: str, path: str, *, actor: uuid.UUID | None = None,
        body: bytes = b"", headers: dict | None = None,
    ):
        """ASGITransport, nao TestClient: o TestClient sincrono abre o proprio
        portal anyio e trava dentro do loop do IsolatedAsyncioTestCase."""
        import httpx

        request_headers = headers or self.signed_headers(method, path, actor, body)
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://api.local"
        ) as client:
            return await client.request(
                method, path, headers=request_headers, content=body or None
            )

    async def test_outsider_cannot_read_a_project_they_do_not_belong_to(self):
        response = await self.request(
            "GET", "/api/projects/projeto_a/members", actor=self.outsider
        )
        self.assertIn(response.status_code, (403, 404), response.text)

    async def test_plain_member_cannot_remove_another_member(self):
        response = await self.request(
            "DELETE",
            f"/api/projects/projeto_a/members/{self.admin2}",
            actor=self.ex_member,
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_project_admin_cannot_remove_the_owner(self):
        """A transferencia mantem o dono em project_members."""
        response = await self.request(
            "DELETE",
            f"/api/projects/projeto_a/members/{self.owner}",
            actor=self.admin2,
        )
        self.assertEqual(response.status_code, 409, response.text)
        async with self.pool.acquire() as conn:
            still_member = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM project_members "
                "WHERE project_id = $1 AND user_id = $2)",
                self.project_a,
                self.owner,
            )
        self.assertTrue(still_member, "o dono perdeu a linha de membership")

    async def test_project_admin_cannot_remove_a_peer_admin(self):
        response = await self.request(
            "DELETE",
            f"/api/projects/projeto_a/members/{self.admin3}",
            actor=self.admin2,
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_owner_can_remove_an_admin(self):
        response = await self.request(
            "DELETE",
            f"/api/projects/projeto_a/members/{self.admin3}",
            actor=self.owner,
        )
        self.assertEqual(response.status_code, 200, response.text)

    async def test_authenticated_user_cannot_grant_themselves_global_admin(self):
        body = json.dumps(
            {
                "id": str(self.outsider),
                "username": "outsider",
                "groups": ["admin"],
            }
        ).encode()
        response = await self.request(
            "POST",
            "/api/projects/internal/users/sync",
            actor=self.outsider,
            body=body,
        )
        self.assertEqual(response.status_code, 403, response.text)
        async with self.pool.acquire() as conn:
            is_admin = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM user_groups "
                "WHERE user_id = $1 AND group_name = 'admin')",
                self.outsider,
            )
        self.assertFalse(is_admin, "usuario virou admin global")

    async def test_service_route_rejects_a_browser_originated_request(self):
        response = await self.request(
            "GET", "/api/projects/internal/enc-key/projeto_a", actor=self.owner
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_replayed_internal_signature_is_rejected(self):
        from app import internal_service_auth

        path = "/api/projects/projeto_a/members"
        headers = self.signed_headers("GET", path, self.owner, b"")
        first = await self.request("GET", path, headers=headers)
        self.assertNotEqual(first.status_code, 401, first.text)

        # Simula o replay chegando em outro worker: sem isso o cache em
        # processo rejeitaria sozinho e o store compartilhado nunca seria
        # exercitado.
        internal_service_auth._nonce_expirations.clear()

        replay = await self.request("GET", path, headers=headers)
        self.assertEqual(
            replay.status_code,
            401,
            "replay aceito por outro worker: o store compartilhado nao esta valendo",
        )


if __name__ == "__main__":
    unittest.main()
