"""Contrato das URLs de objeto entregues ao Storage Explorer.

Preview e download sao carregados pelo browser e precisam sair pela origem do
Studio, com o ref no path porque uma tag <img> nao envia cabecalho. A URL
copiada pelo usuario precisa ser a do projeto, que funciona sem sessao.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LUA = ROOT / "studio/nginx/lua"
ROUTER = LUA / "proxy_rewrites/storage_platform_router.lua"
REWRITE = LUA / "proxy_rewrites/storage.lua"
BODY_FILTER = LUA / "proxy_rewrites/storage_body_filter.lua"
PUBLIC_URL = LUA / "proxy_rewrites/storage_public_url.lua"
RESOLVER = LUA / "project_context/project_ref_resolver.lua"
KEY_INJECTOR = LUA / "security/inject_service_key_storage.lua"
STUDIO_NGINX = ROOT / "studio/nginx/nginx.conf"
STUDIO_PATCH = ROOT / "studio/studio-slug/studio-project-context.patch"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def lua_runtime() -> str | None:
    return shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")


def lua_runtime_with_cjson() -> str | None:
    runtime = lua_runtime()
    if runtime is None:
        return None
    probe = subprocess.run([runtime, "-e", 'require("cjson")'], capture_output=True)
    return runtime if probe.returncode == 0 else None


class PlatformRoutesCoverTheExplorerTest(unittest.TestCase):
    def test_public_url_and_sign_multi_are_mapped(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        script = f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local router = require("proxy_rewrites.storage_platform_router")

local multi = router.resolve("/api/platform/storage/p/buckets/efdf/objects/sign-multi", "POST")
assert(multi, "sign-multi nao mapeada")
assert(multi.uri == "/storage/v1/object/sign/efdf", multi.uri)
assert(multi.route_name == "object_sign_multi", multi.route_name)

local public_url = router.resolve("/api/platform/storage/p/buckets/efdf/objects/public-url", "POST")
assert(public_url, "public-url nao mapeada")
assert(public_url.local_response == "object_public_url", tostring(public_url.local_response))
assert(public_url.bucket_id == "efdf", tostring(public_url.bucket_id))

local wrong_method, err = router.resolve(
    "/api/platform/storage/p/buckets/efdf/objects/public-url",
    "GET"
)
assert(not wrong_method and err.status == 405, "public-url deveria exigir POST")
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_public_url_is_answered_after_the_project_is_authorized(self) -> None:
        rewrite = read(REWRITE)
        injector = read(KEY_INJECTOR)
        handler = read(PUBLIC_URL)

        self.assertIn("ngx.ctx.storage_platform_local_response = route", rewrite)
        self.assertIn('require("proxy_rewrites.storage_public_url").handle(context)', injector)
        self.assertLess(
            injector.index("project_access"),
            injector.index("storage_public_url"),
            "a URL publica so pode ser respondida depois de autorizar o projeto",
        )
        self.assertIn("/object/public/", handler)
        self.assertIn("studio_public_origin", handler)


class BrowserLoadsObjectsFromTheStudioOriginTest(unittest.TestCase):
    def test_object_route_carries_the_ref_in_the_path(self) -> None:
        nginx = read(STUDIO_NGINX)
        resolver = read(RESOLVER)

        self.assertIn(
            'location ~ "^/storage/v1/[a-z_][a-z0-9_]{2,39}/object/(?:public|sign)/" {',
            nginx,
        )
        self.assertIn(
            'rewrite "^/storage/v1/[a-z_][a-z0-9_]{2,39}/(object/(?:public|sign)/.+)$"'
            " /storage/v1/$1 break;",
            nginx,
        )
        self.assertIn('"^/storage/v1/([^/]+)/object/",', resolver)

    def test_ref_in_path_never_swallows_the_resumable_upload_route(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        script = f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local resolver = require("project_context.project_ref_resolver")

assert(resolver.ref_from_path("/storage/v1/meu_projeto/object/sign/efdf/a.JPG") == "meu_projeto")
assert(resolver.ref_from_path("/storage/v1/meu_projeto/object/public/efdf/a.png") == "meu_projeto")

-- O tus resolve o projeto pelo header; o path nao pode virar um ref falso.
assert(resolver.ref_from_path("/storage/v1/upload/resumable") == nil)
assert(resolver.ref_from_path("/storage/v1/upload/resumable/YWJj") == nil)
assert(resolver.ref_from_path("/storage/v1/object/sign/efdf/a.JPG") == nil)
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_signed_urls_are_rebuilt_on_the_studio_origin(self) -> None:
        runtime = lua_runtime_with_cjson()
        if runtime is None:
            self.skipTest("runtime Lua com cjson nao esta disponivel")

        script = f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local cjson = require("cjson")
local filter = "{BODY_FILTER.as_posix()}"

local function run(mode, payload)
    _G.ngx = {{
        ERR = "err",
        log = function() end,
        arg = {{ cjson.encode(payload), true }},
        ctx = {{
            process_sign_response = true,
            studio_project_context = {{ ref = "meu_projeto" }},
            sign_response_mode = mode,
        }},
        var = {{ studio_public_origin = "https://studio.exemplo:9091" }},
        header = {{}},
        re = {{ gsub = function(s) return (s:gsub("^/+", "")) end }},
    }}
    dofile(filter)
    return cjson.decode(_G.ngx.arg[1])
end

local single = run(nil, {{ {{ path = "efdf/a.JPG", signedURL = "/object/sign/efdf/a.JPG?token=T" }} }})
assert(
    single.signedUrl
        == "https://studio.exemplo:9091/storage/v1/meu_projeto/object/sign/efdf/a.JPG?token=T",
    tostring(single.signedUrl)
)

local multi = run("multi", {{
    {{ path = "efdf/a.JPG", signedURL = "/object/sign/efdf/a.JPG?token=A" }},
    {{ path = "efdf/b.png", signedURL = "/object/sign/efdf/b.png?token=B" }},
}})
assert(#multi == 2, "sign-multi deve responder em lista")
assert(multi[1].path == "efdf/a.JPG", tostring(multi[1].path))
assert(
    multi[2].signedUrl
        == "https://studio.exemplo:9091/storage/v1/meu_projeto/object/sign/efdf/b.png?token=B",
    tostring(multi[2].signedUrl)
)
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_sign_multi_sends_every_path_to_the_storage_contract(self) -> None:
        rewrite = read(REWRITE)

        self.assertIn('elseif type(body.path) == "table" then', rewrite)
        self.assertIn('ngx.ctx.sign_response_mode = "multi"', rewrite)


class CopiedUrlStaysOnTheProjectTest(unittest.TestCase):
    def test_clipboard_receives_the_project_url(self) -> None:
        patch = read(STUDIO_PATCH)

        self.assertIn("a/apps/studio/components/interfaces/Storage/StorageExplorer/useCopyUrl.tsx", patch)
        self.assertIn(
            "+          ? url.replace(`${window.location.origin}/storage/v1/${projectRef}`,"
            " `${hostEndpoint}/storage/v1`)",
            patch,
        )
        self.assertIn(
            "+    [customEndpoint, getFileUrl, hostEndpoint, isCustomDomainActive, projectRef]",
            patch,
        )


if __name__ == "__main__":
    unittest.main()
