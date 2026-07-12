from pathlib import Path

sync_path = Path("studio/nginx/lua/admin_api/user_sync.lua")
sync_path.write_text(
    '''local cjson = require("cjson.safe")
local http = require("resty.http")

local API_ORIGIN = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local TOKEN = os.getenv("NGINX_SHARED_TOKEN") or ""

local M = {}

local function request_sync(body)
    if API_ORIGIN == "" then
        return nil, "SERVER_DOMAIN ausente"
    end

    local host = string.match(API_ORIGIN, "//([^/:]+)") or "localhost"
    local httpc = http.new()
    httpc:set_timeout(3000)

    return httpc:request_uri(
        API_ORIGIN .. "/api/projects/internal/users/sync",
        {
            method = "POST",
            body = body,
            ssl_verify = false,
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Shared-Token"] = TOKEN,
                ["Host"] = host,
                ["User-Agent"] = "studio-nginx-internal/1.0",
            }
        }
    )
end

function M.sync_user(payload)
    if TOKEN == "" then
        return nil, "NGINX_SHARED_TOKEN ausente"
    end
    if API_ORIGIN == "" then
        return nil, "SERVER_DOMAIN ausente"
    end

    local body = cjson.encode(payload)
    if not body then
        return nil, "falha ao serializar payload"
    end

    local res, err = request_sync(body)
    if not res then
        return nil, err or "falha ao acessar a API por SERVER_DOMAIN"
    end
    if res.status < 200 or res.status >= 300 then
        return nil, string.format("sync retornou status %s: %s", res.status, res.body or "")
    end

    local decoded = cjson.decode(res.body or "{}")
    return decoded or true, nil
end

return M
''',
    encoding="utf-8",
)

schema_path = Path("servidor/api-internal/app/database_schema.py")
schema = schema_path.read_text(encoding="utf-8")
old = '''                ADD COLUMN IF NOT EXISTS profile_version BIGINT NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ;'''
new = '''                ADD COLUMN IF NOT EXISTS profile_version BIGINT NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;'''
if schema.count(old) != 1:
    raise SystemExit("identity schema columns block not found exactly once")
schema = schema.replace(old, new)
old_index = "            CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);"
new_index = '''            CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);
            CREATE INDEX IF NOT EXISTS idx_users_last_seen_at ON users(last_seen_at);'''
if schema.count(old_index) != 1:
    raise SystemExit("last sync index not found exactly once")
schema = schema.replace(old_index, new_index)
schema_path.write_text(schema, encoding="utf-8")

main_path = Path("servidor/api-internal/app/main.py")
main = main_path.read_text(encoding="utf-8")
old_activity = '''        if user_row:
            await conn.execute(
                """
                UPDATE users
                SET last_login_at = now(), updated_at = now()
                WHERE id = $1
                """,
                user_row["id"],
            )'''
new_activity = '''        if user_row:
            await conn.execute(
                """
                UPDATE users
                SET last_seen_at = now(), updated_at = now()
                WHERE id = $1
                  AND (
                      last_seen_at IS NULL
                      OR last_seen_at < now() - interval '5 minutes'
                  )
                """,
                user_row["id"],
            )'''
if main.count(old_activity) != 1:
    raise SystemExit("authenticated activity block not found exactly once")
main = main.replace(old_activity, new_activity)
main_path.write_text(main, encoding="utf-8")

profile_test_path = Path("tests/smoke/test_user_profile_contract.py")
profile_test = profile_test_path.read_text(encoding="utf-8")
old_test = '''    def test_user_sync_prefers_direct_api_and_keeps_remote_fallback(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_sync.lua"
        ).read_text(encoding="utf-8")

        self.assertIn('os.getenv("PROJECTS_API_INTERNAL_URL")', source)
        self.assertIn('INTERNAL_DSN = "http://projects-api:18000"', source)
        self.assertIn("table.insert(origins, EXTERNAL_DSN)", source)
        self.assertIn('"User-Agent"] = "studio-nginx-internal/1.0"', source)
'''
new_test = '''    def test_user_sync_uses_only_server_domain(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_sync.lua"
        ).read_text(encoding="utf-8")

        self.assertIn('os.getenv("SERVER_DOMAIN")', source)
        self.assertIn('return nil, "SERVER_DOMAIN ausente"', source)
        self.assertNotIn("PROJECTS_API_INTERNAL_URL", source)
        self.assertNotIn("projects-api:18000", source)
        self.assertNotIn("origins", source)
        self.assertIn('"User-Agent"] = "studio-nginx-internal/1.0"', source)
'''
if profile_test.count(old_test) != 1:
    raise SystemExit("old user sync contract test not found exactly once")
profile_test = profile_test.replace(old_test, new_test)
profile_test_path.write_text(profile_test, encoding="utf-8")

Path("tests/smoke/test_studio_api_transport_and_activity.py").write_text(
    '''from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StudioApiTransportAndActivityTests(unittest.TestCase):
    def test_studio_nginx_has_no_direct_projects_api_origin(self) -> None:
        root = ROOT / "studio/nginx"
        violations = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "projects-api:18000" in source or "PROJECTS_API_INTERNAL_URL" in source:
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations)

    def test_user_sync_requires_server_domain_without_network_fallback(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_sync.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('local API_ORIGIN = (os.getenv("SERVER_DOMAIN") or "")', source)
        self.assertIn('return nil, "SERVER_DOMAIN ausente"', source)
        self.assertEqual(1, source.count("httpc:request_uri("))
        self.assertNotIn("for _, origin", source)

    def test_authenticated_requests_update_sampled_last_seen_only(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/main.py"
        ).read_text(encoding="utf-8")
        start = source.index("async def resolve_authenticated_user(")
        end = source.index("async def ensure_project_member_access(", start)
        block = source[start:end]
        self.assertIn("SET last_seen_at = now(), updated_at = now()", block)
        self.assertIn("last_seen_at < now() - interval '5 minutes'", block)
        self.assertNotIn("SET last_login_at = now()", block)

    def test_identity_schema_exposes_last_seen_at(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/database_schema.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ", source)
        self.assertIn("idx_users_last_seen_at", source)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

integration_dir = Path("tests/integration")
integration_dir.mkdir(parents=True, exist_ok=True)
Path("tests/integration/test_profile_via_traefik.py").write_text(
    '''from __future__ import annotations

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
''',
    encoding="utf-8",
)
