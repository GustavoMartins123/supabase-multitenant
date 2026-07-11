from __future__ import annotations

import json
import os
import time
import unittest

from tests.smoke.common import (
    build_internal_push_headers,
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
        shared_token = os.environ["SMOKE_SHARED_TOKEN"]
        token = build_user_token(secret, user_id)
        headers = {
            "X-Shared-Token": shared_token,
            "X-User-Token": token,
        }
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
        )
        self.assertEqual(tampered_status, 403)

        first_status, _ = request(
            "POST",
            push_url,
            headers=signed_headers,
            raw_body=body,
        )
        self.assertNotIn(first_status, {401, 403, 405})

        replay_status, _ = request(
            "POST",
            push_url,
            headers=signed_headers,
            raw_body=body,
        )
        self.assertEqual(replay_status, 401)


if __name__ == "__main__":
    unittest.main()
