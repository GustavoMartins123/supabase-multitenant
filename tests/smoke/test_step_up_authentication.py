from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

from app.step_up_auth import (  # noqa: E402
    STEP_UP_KEY_CONTEXT,
    consume_step_up_grant,
    resolve_step_up_grant,
)


SECRET = "step-up-contract-secret"


def build_grant(
    *,
    subject: uuid.UUID,
    login_session: str,
    action: str,
    project: str,
    resource: str,
    issued_at: int,
    expires_at: int | None = None,
    jti: str = "a" * 22,
) -> str:
    payload = json.dumps(
        {
            "sub": str(subject),
            "iat": issued_at,
            "exp": expires_at if expires_at is not None else issued_at + 300,
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


class StepUpAuthenticationContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = int(time.time())
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.session = "s" * 43
        self.key_id = str(uuid.uuid4())
        self.token = build_grant(
            subject=self.user_id,
            login_session=self.session,
            action="reveal_secret_key",
            project="demo_project",
            resource=self.key_id,
            issued_at=self.now,
        )
        self.auth_user = {
            "db_user_id": self.user_id,
            "login_session": self.session,
        }

    def test_valid_grant_is_action_session_and_resource_bound(self) -> None:
        claims = resolve_step_up_grant(
            self.token,
            secret=SECRET,
            max_clock_skew_seconds=30,
            now=self.now,
        )
        self.assertEqual(claims["sub"], str(self.user_id))
        self.assertEqual(claims["action"], "reveal_secret_key")
        self.assertEqual(claims["resource"], self.key_id)

        tampered = self.token.replace("su1.", "v1.", 1)
        with self.assertRaises(HTTPException) as wrong_domain:
            resolve_step_up_grant(
                tampered,
                secret=SECRET,
                max_clock_skew_seconds=30,
                now=self.now,
            )
        self.assertEqual(wrong_domain.exception.status_code, 403)

    async def test_consumption_is_one_time_and_records_no_bearer(self) -> None:
        conn = FakeConnection()
        await consume_step_up_grant(
            conn,
            token=self.token,
            secret=SECRET,
            max_clock_skew_seconds=30,
            auth_user=self.auth_user,
            action="reveal_secret_key",
            project_id=self.project_id,
            project_ref="demo_project",
            resource_id=self.key_id,
        )
        self.assertEqual(len(conn.calls), 1)
        query, values = conn.calls[0]
        self.assertIn("ON CONFLICT (jti) DO NOTHING", query)
        self.assertNotIn(self.token, values)

        with self.assertRaises(HTTPException) as replay:
            await consume_step_up_grant(
                conn,
                token=self.token,
                secret=SECRET,
                max_clock_skew_seconds=30,
                auth_user=self.auth_user,
                action="reveal_secret_key",
                project_id=self.project_id,
                project_ref="demo_project",
                resource_id=self.key_id,
            )
        self.assertEqual(replay.exception.status_code, 403)

    async def test_wrong_session_or_action_fails_before_database(self) -> None:
        for auth_user, action in (
            ({**self.auth_user, "login_session": "x" * 43}, "reveal_secret_key"),
            (self.auth_user, "rotate_secret_key"),
        ):
            conn = FakeConnection()
            with self.assertRaises(HTTPException) as rejected:
                await consume_step_up_grant(
                    conn,
                    token=self.token,
                    secret=SECRET,
                    max_clock_skew_seconds=30,
                    auth_user=auth_user,
                    action=action,
                    project_id=self.project_id,
                    project_ref="demo_project",
                    resource_id=self.key_id,
                )
            self.assertEqual(rejected.exception.status_code, 403)
            self.assertEqual(conn.calls, [])

    def test_expired_or_overlong_grant_is_rejected(self) -> None:
        for token in (
            build_grant(
                subject=self.user_id,
                login_session=self.session,
                action="delete_project",
                project="demo_project",
                resource="demo_project",
                issued_at=self.now - 301,
                expires_at=self.now,
            ),
            build_grant(
                subject=self.user_id,
                login_session=self.session,
                action="delete_project",
                project="demo_project",
                resource="demo_project",
                issued_at=self.now,
                expires_at=self.now + 301,
            ),
        ):
            with self.assertRaises(HTTPException) as rejected:
                resolve_step_up_grant(
                    token,
                    secret=SECRET,
                    max_clock_skew_seconds=30,
                    now=self.now,
                )
            self.assertEqual(rejected.exception.status_code, 403)

    def test_migration_persists_bindings_but_not_password_or_token(self) -> None:
        migration = (
            API_ROOT
            / "app"
            / "migrations"
            / "0002_step_up_grants.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("studio_step_up_grant_consumptions", migration)
        self.assertIn("login_session_hash", migration)
        self.assertIn("resource_id", migration)
        self.assertNotIn("password", migration.lower())
        self.assertNotIn("step_up_token", migration)


if __name__ == "__main__":
    unittest.main()
