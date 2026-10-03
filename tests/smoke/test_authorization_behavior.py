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
import copy
from unittest import mock
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
        self.directory_sequence = 0
        self.directory_users = [dict(id=str(user_id), username=name, display_name=name, groups=["active"], is_active=True, source={"name":"test"}) for user_id, name in ((self.owner,"owner"),(self.admin2,"admin2"),(self.admin3,"admin3"),(self.ex_member,"exmember"),(self.outsider,"outsider"))]
        async def canonical_read(*args):
            self.directory_sequence += 1
            return {"sequence":self.directory_sequence, "revision":self.directory_revision(), "users":copy.deepcopy(self.directory_users)}
        # Mock only the remote YAML transport. Reconciliation and authorization
        # still run against the real PostgreSQL database.
        self.directory_patch = mock.patch("app.directory_service.read_directory", side_effect=canonical_read)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        sys.path.insert(0, str(ROOT / "servidor/host-agent"))
        self.agent_directory_patch = mock.patch("hostagent.directory_transport.read_directory", side_effect=canonical_read)
        self.agent_directory_patch.start()
        self.addCleanup(self.agent_directory_patch.stop)

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
                "host_agent_commands",
                "studio_directory_state",
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

    def directory_revision(self):
        return hashlib.sha256(json.dumps(self.directory_users, sort_keys=True).encode()).hexdigest()

    def user_token(self, user_id: uuid.UUID, directory_revision=None) -> str:
        from app.security_tokens import USER_TOKEN_AUDIENCE

        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "aud": USER_TOKEN_AUDIENCE,
            "jti": base64url(secrets.token_bytes(16)),
            "iat": now,
            "exp": now + 300,
            "login_session": base64url(secrets.token_bytes(32)),
            "directory_revision": directory_revision or self.directory_revision(),
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

    async def test_admin_cannot_demote_owner_by_upsert(self):
        response = await self.request(
            "POST", "/api/projects/projeto_a/members", actor=self.admin2,
            body=json.dumps({"user_id": str(self.owner), "role": "member"}).encode(),
        )
        self.assertEqual(response.status_code, 409, response.text)

    async def test_admin_cannot_demote_peer_by_upsert(self):
        response = await self.request(
            "POST", "/api/projects/projeto_a/members", actor=self.admin2,
            body=json.dumps({"user_id": str(self.admin3), "role": "member"}).encode(),
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_owner_can_demote_peer_by_upsert(self):
        response = await self.request(
            "POST", "/api/projects/projeto_a/members", actor=self.owner,
            body=json.dumps({"user_id": str(self.admin3), "role": "member"}).encode(),
        )
        self.assertEqual(response.status_code, 200, response.text)

    async def test_concurrent_self_demotions_preserve_last_admin(self):
        await self.pool.execute(
            "DELETE FROM project_members WHERE project_id=$1 AND user_id=$2",
            self.project_a, self.owner,
        )
        async def demote(actor):
            return await self.request(
                "POST", "/api/projects/projeto_a/members", actor=actor,
                body=json.dumps({"user_id": str(actor), "role": "member"}).encode(),
            )
        results = await asyncio.gather(demote(self.admin2), demote(self.admin3))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        self.assertEqual(await self.pool.fetchval(
            "SELECT count(*) FROM project_members WHERE project_id=$1 AND role='admin'",
            self.project_a,
        ), 1)

    async def test_member_cannot_obtain_studio_administrative_credential(self):
        response = await self.request("GET", "/api/projects/internal/studio-context/projeto_a?access=admin", actor=self.ex_member)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM project_studio_keys"), 0)

    async def test_studio_credential_is_stable_private_and_revocable(self):
        from app.project_secret_service import encrypt_project_secret
        from app.runtime_config import service_key_transport_fernet
        from unittest.mock import patch
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                ciphertext = await encrypt_project_secret(conn, project_id=self.project_a, column="anon_key", plaintext="test-anon-key")
                await conn.execute("UPDATE projects SET anon_key=$1 WHERE id=$2", ciphertext, self.project_a)
        path = "/api/projects/internal/studio-context/projeto_a?access=admin"
        with patch("app.routers.internal.get_project_file_size_limit", return_value=5000):
            first = await self.request("GET", path, actor=self.admin2)
            second = await self.request("GET", path, actor=self.owner)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        key1 = service_key_transport_fernet.decrypt(first.json()["enc_admin_key"].encode())
        key2 = service_key_transport_fernet.decrypt(second.json()["enc_admin_key"].encode())
        self.assertEqual(key1, key2)
        self.assertTrue(key1.startswith(b"sb_secret_"))
        self.assertNotIn(key1.decode(), first.text)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM project_api_key_slots"), 0)
        await self.pool.execute("UPDATE project_studio_keys SET is_active=false, revoked_at=now() WHERE project_id=$1", self.project_a)
        revoked = await self.request("GET", path, actor=self.owner)
        self.assertEqual(revoked.status_code, 403, revoked.text)

    async def test_revoked_project_admin_is_denied_on_next_context_request(self):
        await self.pool.execute("UPDATE project_members SET role='member' WHERE project_id=$1 AND user_id=$2", self.project_a, self.admin2)
        response = await self.request("GET", "/api/projects/internal/studio-context/projeto_a?access=admin", actor=self.admin2)
        self.assertEqual(response.status_code, 403, response.text)

    async def test_authorizer_accepts_only_scoped_active_studio_key_not_raw_jwt(self):
        import importlib.util
        import httpx
        from app import opaque_keys
        from app.studio_administrative_keys import get_studio_administrative_key
        sys.modules["opaque_keys"] = opaque_keys
        spec = importlib.util.spec_from_file_location("studio_authorizer_test", ROOT / "servidor/key-authorizer/app.py")
        authorizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(authorizer)
        authorizer._pool = self.pool
        gateway = "a" * 64
        await self.pool.execute("UPDATE projects SET api_gateway_token_hash=$1, opaque_keys_activated_at=now() WHERE id=$2", hashlib.sha256(gateway.encode()).digest(), self.project_a)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                key = await get_studio_administrative_key(conn, project_id=self.project_a)
        headers = {"X-Project-Ref": "projeto_a", "X-Project-Gateway-Token": gateway,
            "X-Api-Key-Header": key, "X-Original-Authorization": "Bearer " + key,
            "X-Allow-Missing-Key": "0", "X-Target-Service": "storage"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=authorizer.app), base_url="http://authorizer") as client:
            for service in ("rest", "graphql", "storage"):
                headers["X-Target-Service"] = service
                result = await client.get("/v1/authorize", headers=headers)
                self.assertEqual(result.status_code, 204, result.text)
                self.assertEqual(result.headers["X-Opaque-Key-Role"], "service_role")
                self.assertEqual(result.headers["X-Opaque-Preserve-Authorization"], "0")
            for service in ("auth", "functions", "realtime"):
                headers["X-Target-Service"] = service
                self.assertEqual((await client.get("/v1/authorize", headers=headers)).status_code, 403)
            headers["X-Target-Service"] = "rest"
            headers["X-Api-Key-Header"] = "eyJhbGciOiJIUzI1NiJ9.raw.jwt"
            self.assertEqual((await client.get("/v1/authorize", headers=headers)).status_code, 403)
            headers["X-Api-Key-Header"] = key
            await self.pool.execute("UPDATE project_studio_keys SET is_active=false WHERE project_id=$1", self.project_a)
            self.assertEqual((await client.get("/v1/authorize", headers=headers)).status_code, 403)

    async def duplicate_intent(self):
        sys.path.insert(0, str(ROOT / "servidor/host-agent"))
        from hostagent.host_agent_protocol import command_signature
        from hostagent.agent import HostAgent
        from types import SimpleNamespace
        dest = uuid.uuid4()
        await self.pool.execute("INSERT INTO projects(id, name, owner_id) VALUES($1,'copy_dest',$2)", dest, self.admin2)
        await self.pool.execute("INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin')", dest, self.admin2)
        args = {"original_name": "projeto_a", "original_uuid": str(self.project_a),
            "original_tenant_uuid": str(self.project_a), "copy_mode": "schema-only", "tenant_uuid": str(dest)}
        record = {"id": uuid.uuid4(), "project_uuid": dest, "requested_by": self.admin2,
            "issued_at": int(time.time()), "timeout_seconds": 600}
        record["signature"] = command_signature("signed-intent-test", command_id=str(record["id"]),
            command="duplicate_project", project="copy_dest", project_uuid=str(dest),
            requested_by=str(self.admin2), args=args, issued_at=record["issued_at"], timeout_seconds=600)
        agent = HostAgent(SimpleNamespace(hmac_secret="signed-intent-test", studio_directory_url="https://canonical.test", studio_directory_secret=PROJECTS_API_SECRET, studio_directory_ca_file=None))
        agent.pool = self.pool
        return agent, record, args

    async def test_signed_duplicate_reauthorizes_source_after_membership_revocation(self):
        agent, record, args = await self.duplicate_intent()
        self.assertIsNone(await agent._revalidate(record, "duplicate_project", "copy_dest", args))
        await self.pool.execute("DELETE FROM project_members WHERE project_id=$1 AND user_id=$2", self.project_a, self.admin2)
        denial = await agent._revalidate(record, "duplicate_project", "copy_dest", args)
        self.assertEqual(denial[0], "authorization_denied:source_access_revoked")

    async def test_pending_agent_job_obeys_yaml_disable_without_database_sync(self):
        agent, record, args = await self.duplicate_intent()
        for user in self.directory_users:
            if user['id'] == str(self.admin2):
                user['is_active'] = False
        self.assertTrue(await self.pool.fetchval('SELECT is_active FROM users WHERE id=$1', self.admin2))
        denial = await agent._revalidate(record, 'duplicate_project', 'copy_dest', args)
        self.assertEqual(denial[0], 'authorization_denied:directory_revoked')

    async def test_pending_global_admin_job_obeys_yaml_group_revocation_with_stale_db_group(self):
        agent, record, args = await self.duplicate_intent()
        from hostagent.host_agent_protocol import command_signature
        record['requested_by'] = self.outsider
        record['signature'] = command_signature('signed-intent-test', command_id=str(record['id']), command='duplicate_project', project='copy_dest', project_uuid=str(record['project_uuid']), requested_by=str(self.outsider), args=args, issued_at=record['issued_at'], timeout_seconds=600)
        user = next(u for u in self.directory_users if u['id']==str(self.outsider))
        user['groups'] = ['admin','active']
        await self.pool.execute("INSERT INTO user_groups(user_id,group_name,source) VALUES($1,'admin','test')", self.outsider)
        self.assertIsNone(await agent._revalidate(record,'duplicate_project','copy_dest',args))
        user['groups'] = ['active']
        self.assertTrue(await self.pool.fetchval("SELECT EXISTS(SELECT 1 FROM user_groups WHERE user_id=$1 AND group_name='admin')", self.outsider))
        denial = await agent._revalidate(record,'duplicate_project','copy_dest',args)
        self.assertEqual(denial[0], 'authorization_denied:source_access_revoked')

    async def test_directory_outage_denies_api_and_agent_even_with_active_database_user(self):
        from app.directory_transport import DirectoryUnavailable
        with mock.patch('app.directory_service.read_directory', side_effect=DirectoryUnavailable('offline')):
            response = await self.request('GET', '/api/projects/projeto_a/members', actor=self.owner)
        self.assertEqual(response.status_code, 503)
        agent, record, args = await self.duplicate_intent()
        from hostagent.directory_transport import DirectoryUnavailable as AgentDirectoryUnavailable
        with mock.patch('hostagent.directory_transport.read_directory', side_effect=AgentDirectoryUnavailable('offline')):
            denial = await agent._revalidate(record, 'duplicate_project', 'copy_dest', args)
        self.assertEqual(denial[0], 'authorization_denied:directory_unavailable')

    async def test_removed_directory_account_is_disabled_and_groups_removed_transactionally(self):
        await self.pool.execute("INSERT INTO user_groups(user_id,group_name,source) VALUES($1,'admin','test')", self.owner)
        self.directory_users = [u for u in self.directory_users if u['id'] != str(self.owner)]
        response = await self.request('GET', '/api/projects/projeto_a/members', actor=self.owner)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(await self.pool.fetchval('SELECT is_active FROM users WHERE id=$1', self.owner))
        self.assertEqual(await self.pool.fetchval('SELECT count(*) FROM user_groups WHERE user_id=$1', self.owner), 0)

    async def test_out_of_order_directory_snapshot_cannot_restore_removed_admin_group(self):
        from app.directory_service import DirectorySnapshot, reconcile_directory
        from fastapi import HTTPException
        current = DirectorySnapshot(sequence=20, revision='b'*64, users=self.directory_users)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await reconcile_directory(conn, current)
        stale_users = copy.deepcopy(self.directory_users)
        stale_users[0]['groups'].append('admin')
        stale = DirectorySnapshot(sequence=19, revision='a'*64, users=stale_users)
        async with self.pool.acquire() as conn:
            with self.assertRaises(HTTPException) as error:
                async with conn.transaction():
                    await reconcile_directory(conn, stale)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(await self.pool.fetchval("SELECT EXISTS(SELECT 1 FROM user_groups WHERE user_id=$1 AND group_name='admin')", self.owner))

    @unittest.skipUnless(os.environ.get('STUDIO_DIRECTORY_TEST_URL'), 'Start real OpenResty directory harness')
    async def test_live_openresty_snapshot_revokes_admin_in_real_postgres_and_api(self):
        import urllib.request
        from app.directory_transport import read_directory
        origin = os.environ['STUDIO_DIRECTORY_TEST_URL']
        async def seed(groups):
            body = json.dumps({'users':{'admin':{'email':'admin@example.test','displayname':'Admin','groups':groups,'disabled':False}}}).encode()
            def post():
                with urllib.request.urlopen(urllib.request.Request(origin+'/test/seed',data=body),timeout=10) as response:
                    response.read()
            await asyncio.to_thread(post)
        async def live_read(*args):
            return await read_directory(origin, PROJECTS_API_SECRET, None)
        await seed(['admin','active'])
        snapshot = await live_read()
        actor = uuid.UUID(snapshot['users'][0]['id'])
        path = '/api/projects/projeto_a/members'
        headers = self.signed_headers('GET', path, None, b'')
        headers['X-User-Token'] = self.user_token(actor, snapshot['revision'])
        with mock.patch('app.directory_service.read_directory', side_effect=live_read):
            response = await self.request('GET',path,headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        await seed(['active'])
        snapshot = await live_read()
        headers = self.signed_headers('GET', path, None, b'')
        headers['X-User-Token'] = self.user_token(actor, snapshot['revision'])
        with mock.patch('app.directory_service.read_directory', side_effect=live_read):
            response = await self.request('GET',path,headers=headers)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertFalse(await self.pool.fetchval("SELECT EXISTS(SELECT 1 FROM user_groups WHERE user_id=$1 AND group_name='admin')", actor))

    async def test_signed_duplicate_cannot_copy_reused_source_slug(self):
        agent, record, args = await self.duplicate_intent()
        await self.pool.execute("UPDATE projects SET name='renamed_source' WHERE id=$1", self.project_a)
        await self.pool.execute("INSERT INTO projects(id,name,owner_id) VALUES($1,'projeto_a',$2)", uuid.uuid4(), self.admin2)
        denial = await agent._revalidate(record, "duplicate_project", "copy_dest", args)
        self.assertEqual(denial[0], "authorization_denied:source_identity_mismatch")

    async def test_agent_serializes_duplicate_source_against_rename(self):
        agent, record, args = await self.duplicate_intent()
        from hostagent import db as agent_db
        await self.pool.execute("INSERT INTO host_agent_commands(id,project,command,args,issued_at,signature,timeout_seconds) VALUES($1,'copy_dest','duplicate_project',$2,0,'test',600)", record["id"], json.dumps(args))
        await self.pool.execute("INSERT INTO host_agent_commands(id,project,command,args,issued_at,signature,timeout_seconds) VALUES($1,'projeto_a','rename_project',$2,0,'test',600)", uuid.uuid4(), json.dumps({"new_name":"new_source"}))
        leases = await asyncio.gather(agent_db.lease_next_command(self.pool,"agent1",60,set()), agent_db.lease_next_command(self.pool,"agent2",60,set()))
        self.assertEqual(sum(row is not None for row in leases), 1)

    async def test_concurrent_delete_and_upsert_preserve_last_admin(self):
        await self.pool.execute(
            "DELETE FROM project_members WHERE project_id=$1 AND user_id=$2",
            self.project_a, self.owner,
        )
        results = await asyncio.gather(
            self.request("DELETE", f"/api/projects/projeto_a/members/{self.admin2}", actor=self.admin2),
            self.request("POST", "/api/projects/projeto_a/members", actor=self.admin3,
                body=json.dumps({"user_id": str(self.admin3), "role": "member"}).encode()),
        )
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        self.assertEqual(await self.pool.fetchval(
            "SELECT count(*) FROM project_members WHERE project_id=$1 AND role='admin'",
            self.project_a,
        ), 1)

    async def test_authenticated_user_cannot_grant_themselves_global_admin(self):
        body = json.dumps({"sequence":1,"revision":self.directory_revision(),"users":[{"id":str(self.outsider),"username":"outsider","display_name":"Outsider","groups":["admin"],"is_active":True,"source":{"name":"test"}}]}).encode()
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
