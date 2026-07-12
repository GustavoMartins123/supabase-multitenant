from __future__ import annotations

import base64
import json
import os
import ssl
import unittest
import urllib.error
import urllib.request

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nGQAAAAASUVORK5CYII="
)


class ProfileViaTraefikIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_url = os.getenv("STUDIO_BASE_URL", "").rstrip("/")
        cls.cookie = os.getenv("STUDIO_TEST_COOKIE", "")
        cls.allow_mutation = os.getenv("STUDIO_PROFILE_TEST_ALLOW_MUTATION") == "1"
        if not cls.base_url or not cls.cookie or not cls.allow_mutation:
            raise unittest.SkipTest(
                "STUDIO_BASE_URL, STUDIO_TEST_COOKIE and STUDIO_PROFILE_TEST_ALLOW_MUTATION=1 are required"
            )
        cls.context = ssl.create_default_context()
        if os.getenv("STUDIO_TEST_VERIFY_TLS", "1") != "1":
            cls.context.check_hostname = False
            cls.context.verify_mode = ssl.CERT_NONE

    def request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None):
        headers = {"Cookie": self.cookie, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=15) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            self.fail(f"{method} {path} returned {exc.code}: {exc.read().decode('utf-8', errors='replace')}")

    def test_profile_patch_and_avatar_cross_traefik(self) -> None:
        status, body, _ = self.request("GET", "/api/user/me")
        self.assertEqual(200, status)
        profile = json.loads(body)

        payload = {
            "display_name": profile.get("display_name", ""),
            "given_name": profile.get("given_name", ""),
            "family_name": profile.get("family_name", ""),
            "middle_name": profile.get("middle_name", ""),
            "nickname": profile.get("nickname", ""),
            "gender": profile.get("gender", ""),
            "birthdate": profile.get("birthdate", ""),
            "website": profile.get("website", ""),
            "profile": profile.get("profile", ""),
            "zoneinfo": profile.get("zoneinfo", ""),
            "locale": profile.get("locale", ""),
            "phone_number": profile.get("phone_number", ""),
            "phone_extension": profile.get("phone_extension", ""),
            "street_address": profile.get("street_address", ""),
            "locality": profile.get("locality", ""),
            "region": profile.get("region", ""),
            "postal_code": profile.get("postal_code", ""),
            "country": profile.get("country", ""),
        }
        status, _, _ = self.request(
            "PATCH",
            "/api/user/me",
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )
        self.assertEqual(200, status)

        status, _, _ = self.request(
            "PUT",
            "/api/user/me/avatar",
            PNG_1X1,
            "image/png",
        )
        self.assertEqual(200, status)

        status, _, _ = self.request("DELETE", "/api/user/me/avatar")
        self.assertEqual(200, status)


if __name__ == "__main__":
    unittest.main()
