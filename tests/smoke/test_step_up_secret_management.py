"""Step-up para gestao de secret keys (LOG-08).

Alteracao de policy, cancelamento de rotacao e revogacao de slot `secret`
exigem grant vinculado a acao/sessao/recurso, igual a criacao/rotacao/
ativacao/revelacao. A lista de acoes precisa ser identica no backend, no
mint (Lua), na migration do CHECK e no app Flutter.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

from app.step_up_auth import (  # noqa: E402
    STEP_UP_ACTIONS,
    consume_step_up_grant,
    resolve_step_up_grant,
)

SECRET = "step-up-secret-management-contract"

NEW_ACTIONS = (
    "update_secret_key_policy",
    "cancel_secret_key_rotation",
    "revoke_secret_key",
)


def build_grant(
    *,
    subject: uuid.UUID,
    login_session: str,
    action: str,
    project: str,
    resource: str,
    issued_at: int,
    jti: str = "b" * 22,
) -> str:
    from app.step_up_auth import STEP_UP_KEY_CONTEXT

    payload = json.dumps(
        {
            "sub": str(subject),
            "iat": issued_at,
            "exp": issued_at + 300,
            "login_session": login_session,
            "action": action,
            "project": project,
            "resource": resource,
            "jti": jti,
        },
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    key = hmac.new(SECRET.encode(), STEP_UP_KEY_CONTEXT, hashlib.sha256).digest()
    signature = hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
    return f"su1.{encoded}.{signature}"


class FakeConnection:
    def __init__(self) -> None:
        self.consumed: set[str] = set()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object) -> str | None:
        self.calls.append((query, args))
        jti = str(args[0])
        if jti in self.consumed:
            return None
        self.consumed.add(jti)
        return jti


def lua_actions() -> set[str]:
    source = (
        ROOT
        / "studio"
        / "nginx"
        / "lua"
        / "security"
        / "step_up_authenticate.lua"
    ).read_text(encoding="utf-8")
    block = source.split("local ACTIONS = {", 1)[1].split("}", 1)[0]
    return set(re.findall(r"([a-z_]+) = true", block))


def migration_actions() -> set[str]:
    sql = (
        API_ROOT
        / "app"
        / "migrations"
        / "0008_step_up_secret_management.sql"
    ).read_text(encoding="utf-8")
    return set(re.findall(r"'([a-z_]+)'", sql))


def flutter_actions() -> set[str]:
    source = (
        ROOT
        / "studio"
        / "seletor_de_projetos"
        / "lib"
        / "services"
        / "step_up_authentication_service.dart"
    ).read_text(encoding="utf-8")
    return set(re.findall(r"\w+\('([a-z_]+)'\)", source))


class StepUpSecretManagementContractTest(unittest.TestCase):
    def test_action_allowlist_is_identical_everywhere(self) -> None:
        self.assertEqual(set(STEP_UP_ACTIONS), lua_actions())
        self.assertEqual(set(STEP_UP_ACTIONS), migration_actions())
        for action in (*NEW_ACTIONS, "activate_secret_key"):
            with self.subTest(action=action):
                self.assertIn(action, STEP_UP_ACTIONS)
                self.assertIn(action, flutter_actions())
        self.assertLessEqual(flutter_actions(), set(STEP_UP_ACTIONS))

    def test_migration_extends_the_previous_check(self) -> None:
        sql = (
            API_ROOT
            / "app"
            / "migrations"
            / "0008_step_up_secret_management.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("studio_step_up_grant_consumptions_action_check", sql)
        for action in (
            "delete_project",
            "reveal_secret_key",
            "create_secret_key",
            "rotate_secret_key",
            "activate_secret_key",
            *NEW_ACTIONS,
        ):
            with self.subTest(action=action):
                self.assertIn(f"'{action}'", sql)


class StepUpSecretManagementGrantTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = int(time.time())
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.session = "s" * 43
        self.slot_id = str(uuid.uuid4())
        self.auth_user = {
            "db_user_id": self.user_id,
            "login_session": self.session,
        }

    def grant(self, action: str, jti: str = "b" * 22) -> str:
        return build_grant(
            subject=self.user_id,
            login_session=self.session,
            action=action,
            project="demo_project",
            resource=self.slot_id,
            issued_at=self.now,
            jti=jti,
        )

    async def consume(self, conn: FakeConnection, token: str, action: str) -> None:
        await consume_step_up_grant(
            conn,
            token=token,
            secret=SECRET,
            max_clock_skew_seconds=30,
            auth_user=self.auth_user,
            action=action,
            project_id=self.project_id,
            project_ref="demo_project",
            resource_id=self.slot_id,
        )

    def test_new_actions_resolve_consume_once_and_bind_action(self) -> None:
        for index, action in enumerate(NEW_ACTIONS):
            with self.subTest(action=action):
                token = self.grant(action, jti=f"b{index:021d}")
                claims = resolve_step_up_grant(
                    token,
                    secret=SECRET,
                    max_clock_skew_seconds=30,
                    now=self.now,
                )
                self.assertEqual(claims["action"], action)

    async def test_new_actions_consume_once_and_reject_replay(self) -> None:
        for index, action in enumerate(NEW_ACTIONS):
            with self.subTest(action=action):
                conn = FakeConnection()
                token = self.grant(action, jti=f"c{index:021d}")
                await self.consume(conn, token, action)
                self.assertEqual(len(conn.calls), 1)
                with self.assertRaises(Exception) as replay:
                    await self.consume(conn, token, action)
                self.assertEqual(replay.exception.status_code, 403)

    async def test_grant_for_another_action_fails_before_database(self) -> None:
        conn = FakeConnection()
        token = self.grant("update_secret_key_policy")
        with self.assertRaises(Exception) as rejected:
            await self.consume(conn, token, "revoke_secret_key")
        self.assertEqual(rejected.exception.status_code, 403)
        self.assertEqual(conn.calls, [])


if __name__ == "__main__":
    unittest.main()
