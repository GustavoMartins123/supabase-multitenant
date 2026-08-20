"""Contrato do upload resumable (tus) do Storage Explorer.

O Studio nunca recebe a service key: o create e os PATCH do tus atravessam o
gateway do Studio, que injeta a credencial, aplica o limite do projeto e
reancora o Location devolvido pelo Storage na origem publica do Studio.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LUA = ROOT / "studio/nginx/lua"
LOCATION_FILTER = LUA / "proxy_rewrites/storage_resumable_location.lua"
UPLOAD_LIMIT = LUA / "security/storage_upload_limit.lua"
UPLOAD_GUARD = LUA / "security/upload_route_guard.lua"
STUDIO_NGINX = ROOT / "studio/nginx/nginx.conf"
STUDIO_PATCH = ROOT / "studio/studio-slug/studio-project-context.patch"
PROJECT_NGINX = ROOT / "servidor/generateProject/nginxtemplate"
SERVER_COMPOSE = ROOT / "servidor/docker-compose.yml"
SERVER_ENV = ROOT / "servidor/.env.example"
STORAGE_LIFECYCLE = ROOT / "servidor/generateProject/lib/storage_multitenant.sh"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class ResumableUploadTargetsTheStudioGatewayTest(unittest.TestCase):
    def test_studio_uploads_to_its_own_origin_with_the_project_ref(self) -> None:
        patch = read(STUDIO_PATCH)

        self.assertIn(
            "+      const resumableUploadUrl = `${window.location.origin}"
            "/storage/v1/upload/resumable`",
            patch,
        )
        self.assertIn("+                'X-Studio-Project-Ref': state.projectRef,", patch)

    def test_gateway_route_injects_the_key_and_streams_the_chunks(self) -> None:
        nginx = read(STUDIO_NGINX)
        guard = read(UPLOAD_GUARD)
        limit = read(UPLOAD_LIMIT)

        storage_start = nginx.index("location /storage/v1 {")
        storage_block = nginx[storage_start : nginx.index("\n        }", storage_start)]

        self.assertIn("security/inject_service_key.lua", storage_block)
        self.assertIn(
            "header_filter_by_lua_file "
            "/usr/local/openresty/lualib/proxy_rewrites/storage_resumable_location.lua",
            storage_block,
        )
        self.assertIn("proxy_request_buffering off;", storage_block)
        self.assertIn('uri:find("^/storage/v1")', guard)
        self.assertIn('uri:find("^/storage/v1/upload/resumable")', limit)


class ResumableLocationRewriteTest(unittest.TestCase):
    def test_location_is_reanchored_on_the_studio_origin(self) -> None:
        runtime = shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        script = f'''
local filter = "{LOCATION_FILTER.as_posix()}"

local function run(location, origin)
    _G.ngx = {{
        ERR = "err",
        log = function() end,
        header = {{ Location = location }},
        var = {{ studio_public_origin = origin }},
    }}
    dofile(filter)
    return _G.ngx.header.Location
end

local origin = "https://studio.exemplo:9091"

assert(
    run(
        "http://a1672222-d532-44bd-a437-7d13731a755f.storage.internal"
            .. "/meu_projeto/storage/v1/upload/resumable/YWJj",
        origin
    ) == origin .. "/storage/v1/upload/resumable/YWJj"
)

assert(
    run("http://10.0.0.1/meu_projeto/storage/v1/upload/resumable/YWJj", origin)
        == origin .. "/storage/v1/upload/resumable/YWJj"
)

assert(
    run("http://10.0.0.1/meu_projeto/storage/v1/object/publico/a.png", origin)
        == "http://10.0.0.1/meu_projeto/storage/v1/object/publico/a.png"
)

assert(run(nil, origin) == nil)

local unchanged = "http://interno/meu_projeto/storage/v1/upload/resumable/YWJj"
assert(run(unchanged, "") == unchanged)
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_lua_syntax_when_compiler_is_available(self) -> None:
        compiler = shutil.which("luac5.1") or shutil.which("luac")
        if compiler is None:
            self.skipTest("luac nao esta instalado")

        subprocess.run([compiler, "-p", str(LOCATION_FILTER)], check=True)


class ProjectGatewayPublishesUsableTusUrlsTest(unittest.TestCase):
    def test_tus_location_leaves_the_internal_tenant_host(self) -> None:
        template = read(PROJECT_NGINX)

        self.assertIn(
            "proxy_redirect ~^https?://[^/]+/{{project_id}}/storage/v1/upload/resumable/(.*)$"
            " $real_scheme://$http_host/{{project_id}}/storage/v1/upload/resumable/$1;",
            template,
        )
        self.assertIn("proxy_request_buffering off;", template)


class StorageWritesTheTenantNamespaceTest(unittest.TestCase):
    def test_storage_runs_as_the_owner_of_the_shared_volume(self) -> None:
        compose = read(SERVER_COMPOSE)
        env = read(SERVER_ENV)

        self.assertIn(
            "user: ${STORAGE_RUN_AS_USER:?defina STORAGE_RUN_AS_USER}", compose
        )
        self.assertIn("STORAGE_RUN_AS_USER=", env)
        self.assertIn("cap_drop:", compose)

    def test_tenant_namespaces_are_created_for_that_identity(self) -> None:
        lifecycle = read(STORAGE_LIFECYCLE)

        self.assertIn("storage_enforce_namespace_ownership()", lifecycle)
        self.assertIn('storage_global_env_value STORAGE_RUN_AS_USER', lifecycle)
        self.assertEqual(
            lifecycle.count('storage_enforce_namespace_ownership "'),
            3,
            "toda materializacao de namespace precisa do guard de propriedade",
        )


if __name__ == "__main__":
    unittest.main()
