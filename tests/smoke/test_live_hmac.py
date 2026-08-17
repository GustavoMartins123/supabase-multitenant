from __future__ import annotations

import json
import os
import time
import unittest

from tests.smoke.common import (
    build_internal_push_headers,
    build_internal_service_headers,
    build_user_token,
    env_flag,
    request,
)


@unittest.skipUnless(env_flag("RUN_HMAC_SMOKE"), "set RUN_HMAC_SMOKE=1")
class LiveHmacSmokeTest(unittest.TestCase):
    def test_user_hmac_accepts_valid_and_rejects_tampered_token(self) -> None:
        api_url = os.environ["SMOKE_API_URL"].rstrip("/")
        user_id = os.environ["SMOKE_USER_ID"]
        secret = os.environ["SMOKE_NGINX_HMAC_SECRET"]
        os.environ["SMOKE_STUDIO_GATEWAY_HMAC_SECRET"]
        token = build_user_token(secret, user_id)
        headers = {"X-User-Token": token}
        status, body = request(
            "GET",
            f"{api_url}/api/projects",
            headers=headers,
        )
        self.assertEqual(status, 200, body)

        bad_headers = dict(headers)
        bad_headers["X-User-Token"] = token[:-1] + (
            "0" if token[-1] != "0" else "1"
        )
        status, _ = request(
            "GET",
            f"{api_url}/api/projects",
            headers=bad_headers,
        )
        self.assertEqual(status, 401)

    def test_service_hmac_rejects_tamper_expiration_and_replay(self) -> None:
        api_url = os.environ["SMOKE_API_URL"].rstrip("/")
        service_secret = os.environ["SMOKE_STUDIO_GATEWAY_HMAC_SECRET"]
        user_token = build_user_token(
            os.environ["SMOKE_NGINX_HMAC_SECRET"],
            os.environ["SMOKE_USER_ID"],
        )
        url = f"{api_url}/api/projects"
        timestamp = int(time.time())
        nonce = os.urandom(16).hex()
        signed = {
            "X-User-Token": user_token,
            **build_internal_service_headers(
                service_secret,
                "GET",
                url,
                timestamp=timestamp,
                nonce=nonce,
            ),
        }

        tampered = dict(signed)
        tampered["X-Internal-Signature"] = "0" * 64
        status, _ = request("GET", url, headers=tampered, sign_internal=False)
        self.assertEqual(status, 403)

        expired = {
            "X-User-Token": user_token,
            **build_internal_service_headers(
                service_secret,
                "GET",
                url,
                timestamp=timestamp - 600,
            ),
        }
        status, _ = request("GET", url, headers=expired, sign_internal=False)
        self.assertEqual(status, 401)

        first_status, _ = request("GET", url, headers=signed, sign_internal=False)
        self.assertEqual(first_status, 200)
        replay_status, _ = request("GET", url, headers=signed, sign_internal=False)
        self.assertEqual(replay_status, 401)

    def test_internal_push_hmac_rejects_tamper_and_replay(self) -> None:
        push_url = os.environ["SMOKE_PUSH_URL"]
        secret = os.environ["SMOKE_INTERNAL_HMAC_SECRET"]
        payload = {
            "project": os.getenv("SMOKE_PUSH_PROJECT", "smoke_project"),
            "token": os.getenv("SMOKE_PUSH_TOKEN", "invalid-smoke-token"),
            "body": "HMAC smoke test",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        nonce = os.urandom(16).hex()
        timestamp = int(time.time())
        signed_headers = {
            "Content-Type": "application/json",
            **build_internal_push_headers(
                secret,
                push_url,
                body,
                timestamp=timestamp,
                nonce=nonce,
            ),
        }

        tampered_status, _ = request(
            "POST",
            push_url,
            headers=signed_headers,
            raw_body=body + b" ",
            sign_internal=False,
        )
        self.assertEqual(tampered_status, 403)

        first_status, _ = request(
            "POST",
            push_url,
            headers=signed_headers,
            raw_body=body,
            sign_internal=False,
        )
        self.assertNotIn(first_status, {401, 403, 405})

        replay_status, _ = request(
            "POST",
            push_url,
            headers=signed_headers,
            raw_body=body,
            sign_internal=False,
        )
        self.assertEqual(replay_status, 401)


if __name__ == "__main__":
    unittest.main()
