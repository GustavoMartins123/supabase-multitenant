from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import sys
import time
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException
from starlette.requests import Request

from tests.smoke.common import build_internal_push_headers, build_user_token


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

USER_SECRET = "user-hmac-smoke-secret"
INTERNAL_SECRET = "internal-hmac-smoke-secret"
security_tokens = importlib.import_module("app.security_tokens")
internal_hmac = importlib.import_module("app.internal_hmac")


def request_with_user_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-user-token", token.encode())],
        }
    )


class UserHmacContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = uuid.uuid4()
        self.now = int(time.time())

    def test_accepts_valid_signed_subject(self) -> None:
        token = build_user_token(USER_SECRET, str(self.user_id), now=self.now)
        resolved = security_tokens.resolve_user_id_from_hmac_token(
            request_with_user_token(token),
            secret=USER_SECRET,
            max_clock_skew_seconds=30,
            now=self.now,
        )
        self.assertEqual(resolved, self.user_id)

    def test_verified_claims_preserve_login_session(self) -> None:
        login_session = "a" * 43
        payload = {
            "sub": str(self.user_id),
            "iat": self.now,
            "exp": self.now + 300,
            "login_session": login_session,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        signature = hmac.new(
            USER_SECRET.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        token = f"v1.{encoded}.{signature}"

        resolved, claims = security_tokens.resolve_user_claims_from_hmac_token(
            request_with_user_token(token),
            secret=USER_SECRET,
            max_clock_skew_seconds=30,
            now=self.now,
        )
        self.assertEqual(self.user_id, resolved)
        self.assertEqual(login_session, claims["login_session"])

    def test_rejects_tampering_and_expiration(self) -> None:
        token = build_user_token(USER_SECRET, str(self.user_id), now=self.now)
        encoded = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=="))
        payload["sub"] = str(uuid.uuid4())
        tampered = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        tampered_token = f"v1.{tampered}.{token.split('.')[2]}"
        with self.assertRaises(HTTPException) as invalid:
            security_tokens.resolve_user_id_from_hmac_token(
                request_with_user_token(tampered_token),
                secret=USER_SECRET,
                max_clock_skew_seconds=30,
                now=self.now,
            )
        self.assertEqual(invalid.exception.status_code, 401)

        expired = build_user_token(
            USER_SECRET,
            str(self.user_id),
            now=self.now - 600,
            ttl_seconds=60,
        )
        with self.assertRaises(HTTPException) as old:
            security_tokens.resolve_user_id_from_hmac_token(
                request_with_user_token(expired),
                secret=USER_SECRET,
                max_clock_skew_seconds=30,
                now=self.now,
            )
        self.assertEqual(old.exception.status_code, 401)


class InternalPushHmacContractTest(unittest.TestCase):
    def test_worker_headers_match_gateway_canonical_contract(self) -> None:
        url = "https://studio.example/api/internal/push?tenant=demo"
        body = b'{"project":"demo","body":"hello"}'
        timestamp = 1_750_000_000
        nonce = "ab" * 16
        worker_headers = internal_hmac.build_internal_hmac_headers(
            INTERNAL_SECRET,
            "POST",
            url,
            body,
            timestamp=timestamp,
            nonce=nonce,
        )
        reference = build_internal_push_headers(
            INTERNAL_SECRET,
            url,
            body,
            timestamp=timestamp,
            nonce=nonce,
        )
        self.assertEqual(worker_headers, reference)

        changed_hash = hashlib.sha256(body + b"!").hexdigest()
        canonical = "\n".join(
            [
                "push-v2",
                "POST",
                "/api/internal/push?tenant=demo",
                str(timestamp),
                nonce,
                changed_hash,
            ]
        )
        changed_signature = hmac.new(
            INTERNAL_SECRET.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertNotEqual(
            changed_signature,
            worker_headers["X-Internal-Signature"],
        )

        changed_query_headers = internal_hmac.build_internal_hmac_headers(
            INTERNAL_SECRET,
            "POST",
            "https://studio.example/api/internal/push?tenant=other",
            body,
            timestamp=timestamp,
            nonce=nonce,
        )
        self.assertNotEqual(
            changed_query_headers["X-Internal-Signature"],
            worker_headers["X-Internal-Signature"],
        )


class InternalServiceHmacContractTest(unittest.TestCase):
    def test_service_identity_method_target_and_body_are_bound_to_mac(self) -> None:
        secret = "studio-gateway-derived-secret"
        body = b'{"project":"demo"}'
        timestamp = 1_750_000_123
        nonce = "cd" * 16
        url = "https://api.example/api/projects/demo/start?force=1"

        headers = internal_hmac.build_internal_hmac_headers(
            secret,
            "POST",
            url,
            body,
            service="studio-gateway",
            timestamp=timestamp,
            nonce=nonce,
        )
        self.assertEqual(headers["X-Internal-Version"], "internal-hmac-v1")
        self.assertEqual(headers["X-Internal-Service"], "studio-gateway")
        self.assertNotIn("X-Internal-Caller", headers)

        target = "/api/projects/demo/start?force=1"
        self.assertTrue(
            internal_hmac.verify_internal_hmac_signature(
                secret,
                service="studio-gateway",
                method="POST",
                target=target,
                body=body,
                timestamp=timestamp,
                nonce=nonce,
                signature=headers["X-Internal-Signature"],
            )
        )

        for changed in (
            {"service": "projects-api"},
            {"method": "DELETE"},
            {"target": "/api/projects/demo/stop?force=1"},
            {"body": body + b"!"},
        ):
            values = {
                "service": "studio-gateway",
                "method": "POST",
                "target": target,
                "body": body,
            }
            values.update(changed)
            self.assertFalse(
                internal_hmac.verify_internal_hmac_signature(
                    secret,
                    service=values["service"],
                    method=values["method"],
                    target=values["target"],
                    body=values["body"],
                    timestamp=timestamp,
                    nonce=nonce,
                    signature=headers["X-Internal-Signature"],
                )
            )

    def test_scope_target_preserves_raw_path_and_query(self) -> None:
        target = internal_hmac.request_target_from_scope(
            {
                "path": "/api/projects/demo",
                "raw_path": b"/api/projects/demo",
                "query_string": b"cursor=a%2Fb&limit=20",
            }
        )
        self.assertEqual(target, "/api/projects/demo?cursor=a%2Fb&limit=20")


if __name__ == "__main__":
    unittest.main()
