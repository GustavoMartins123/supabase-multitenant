from __future__ import annotations

import base64
import json
import os
import ssl
import unittest
import urllib.error
import urllib.parse
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
        if not cls.base_url or not cls.cookie:
            raise unittest.SkipTest(
                "STUDIO_BASE_URL and STUDIO_TEST_COOKIE are required"
            )
        cls.context = ssl.create_default_context()
        if os.getenv("STUDIO_TEST_VERIFY_TLS", "1") != "1":
            cls.context.check_hostname = False
            cls.context.verify_mode = ssl.CERT_NONE

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
        *,
        cookie: str | None = None,
        follow_redirects: bool = True,
    ):
        headers = {"Accept": "*/*"}
        selected_cookie = self.cookie if cookie is None else cookie
        if selected_cookie:
            headers["Cookie"] = selected_cookie
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.context),
            *([] if follow_redirects else [_NoRedirect()]),
        )
        try:
            with opener.open(request, timeout=15) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_profile_patch_and_avatar_cross_traefik(self) -> None:
        if not self.allow_mutation:
            self.skipTest("STUDIO_PROFILE_TEST_ALLOW_MUTATION=1 is required")
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

        status, upload_body, _ = self.request(
            "PUT",
            "/api/user/me/avatar",
            PNG_1X1,
            "image/png",
        )
        self.assertEqual(200, status)
        updated = json.loads(upload_body)
        picture = updated.get("picture", "")
        canonical_path = urllib.parse.urlsplit(picture).path
        self.assertRegex(canonical_path, r"^/api/users/[0-9a-f-]{36}/avatar$")

        status, avatar, headers = self.request("GET", canonical_path)
        self.assertEqual(200, status)
        self.assertEqual("image/webp", headers.get_content_type())
        self.assertEqual(b"RIFF", avatar[:4])
        self.assertEqual(b"WEBP", avatar[8:12])

        status, _, _ = self.request("GET", "/api/user/me/avatar")
        self.assertEqual(405, status, "a rota me sem UUID é apenas para PUT/DELETE")

        status, _, _ = self.request("DELETE", "/api/user/me/avatar")
        self.assertEqual(200, status)

    def test_malformed_and_unknown_uuid_are_rejected(self) -> None:
        status, _, _ = self.request("GET", "/api/users/not-a-uuid/avatar")
        self.assertEqual(400, status)
        status, _, _ = self.request(
            "GET",
            "/api/users/ffffffff-ffff-ffff-ffff-ffffffffffff/avatar",
        )
        self.assertEqual(404, status)

    def _assert_optional_avatar(self, env_name: str, expected: int) -> None:
        user_id = os.getenv(env_name, "")
        if not user_id:
            self.skipTest(f"{env_name} is required for this scenario")
        status, _, _ = self.request("GET", f"/api/users/{user_id}/avatar")
        self.assertEqual(expected, status)

    def test_active_user_without_common_project_is_visible(self) -> None:
        self._assert_optional_avatar("STUDIO_TEST_UNRELATED_ACTIVE_UUID", 200)

    def test_active_ex_member_is_visible(self) -> None:
        self._assert_optional_avatar("STUDIO_TEST_EX_MEMBER_UUID", 200)

    def test_inactive_target_is_hidden(self) -> None:
        self._assert_optional_avatar("STUDIO_TEST_INACTIVE_UUID", 404)

    def test_global_admin_uses_the_same_authenticated_directory_policy(self) -> None:
        admin_cookie = os.getenv("STUDIO_TEST_GLOBAL_ADMIN_COOKIE", "")
        target = os.getenv("STUDIO_TEST_GLOBAL_ADMIN_TARGET_UUID", "")
        if not admin_cookie or not target:
            self.skipTest("global admin cookie and target UUID are required")
        status, _, _ = self.request(
            "GET",
            f"/api/users/{target}/avatar",
            cookie=admin_cookie,
        )
        self.assertEqual(200, status)

    def test_avatar_without_session_redirects_to_authentication(self) -> None:
        status, _, _ = self.request(
            "GET",
            "/api/users/ffffffff-ffff-ffff-ffff-ffffffffffff/avatar",
            cookie="",
            follow_redirects=False,
        )
        self.assertEqual(302, status)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == "__main__":
    unittest.main()
