"""Contratos das correcoes da auditoria de seguranca.

Cada teste amarra uma correcao especifica para que uma regressao futura falhe
aqui em vez de reabrir a vulnerabilidade em silencio. Onde e possivel executar
a logica de verdade (assinatura de tokens, normalizacao de caminho, resolucao
de alvo do signer), o teste executa; onde a logica so existe dentro do nginx ou
do OpenResty, o teste amarra o contrato no arquivo de configuracao.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import pathlib
import re
import sys
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
APP = API_ROOT / "app"
LUA = ROOT / "studio" / "nginx" / "lua"
NGINX_CONF = ROOT / "studio" / "nginx" / "nginx.conf"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def load_module(name: str, path: pathlib.Path):
    """Importa um modulo isolado, sem puxar as dependencias da app inteira."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class InternalNamespaceIsolationTest(unittest.TestCase):
    """O namespace /api/projects/internal/ nao pode ser alcancado pelo cliente."""

    def test_gateway_blocks_the_internal_namespace_before_any_project_route(self):
        conf = read(NGINX_CONF)
        block = 'location ~ "^/api/projects/internal(/|$)"'
        self.assertIn(block, conf)
        self.assertLess(
            conf.index(block),
            conf.index("location ~ ^/api/projects(/.*)?$"),
            "o bloqueio precisa vir antes do catch-all",
        )
        tail = conf[conf.index(block) : conf.index(block) + 200]
        self.assertIn("return 404", tail)

    def test_signer_refuses_to_sign_into_the_internal_namespace(self):
        lua = read(LUA / "security" / "projects_api_signer.lua")
        self.assertIn("is_internal_namespace", lua)
        self.assertIn('uri:find("^/api/projects/internal/")', lua)
        # O alvo derivado tambem passa pela checagem, nao so a URI de entrada.
        self.assertIn("local target = resolve_target(uri)", lua)
        self.assertIn("if target and is_internal_namespace(", lua)

    def test_signer_clears_client_supplied_internal_headers_unconditionally(self):
        lua = read(LUA / "security" / "projects_api_signer.lua")
        clear_at = lua.index("clear_untrusted_internal_headers()\n\n    local target")
        self.assertGreater(clear_at, 0, "a limpeza precisa vir antes do return early")

    def test_service_routes_reject_end_user_context(self):
        internal = read(APP / "routers" / "internal.py")
        self.assertIn("_reject_end_user_context", internal)
        self.assertIn(
            '_END_USER_CONTEXT_HEADERS = ("X-User-Token", "X-User-Groups", "Remote-Groups")',
            internal,
        )
        for route in (
            '@router.post("/api/projects/internal/users/sync")',
            '@router.get("/api/projects/internal/enc-key/{ref}")',
            '@router.get("/api/projects/internal/key-version/{ref}")',
            '@router.get("/api/projects/internal/content-identity/{project_name}")',
        ):
            with self.subTest(route=route):
                start = internal.index(route)
                body = internal[start : start + 1200]
                self.assertIn("_reject_end_user_context(request)", body)

    def test_studio_context_keeps_the_user_scoped_authorization(self):
        internal = read(APP / "routers" / "internal.py")
        start = internal.index('@router.get("/api/projects/internal/studio-context/{ref}")')
        body = internal[start : start + 1500]
        # Esta rota recebe X-User-Token de propósito: nao pode ganhar o guard.
        self.assertNotIn("_reject_end_user_context", body)
        self.assertIn("resolve_authenticated_user", body)
        self.assertIn("ensure_project_member_access", body)

    def test_identity_comes_from_the_verified_middleware_state(self):
        internal = read(APP / "routers" / "internal.py")
        self.assertIn(
            'getattr(request.state, "internal_service", None) != "studio-nginx"',
            internal,
        )
        self.assertNotIn('request.headers.get("X-Internal-Service")', internal)


class AuthAdminProxyAuthorizationTest(unittest.TestCase):
    """auth-admin anexa a service_role do tenant: exige admin do projeto."""

    def setUp(self):
        self.source = read(APP / "routers" / "platform_auth.py")

    def test_proxy_requires_project_admin(self):
        start = self.source.index("async def proxy_project_auth_admin(")
        body = self.source[start : start + 1500]
        self.assertIn("resolve_authenticated_user", body)
        self.assertIn("ensure_project_admin_access", body)
        self.assertIn("_require_studio_nginx(request)", body)

    def test_control_plane_identity_never_reaches_the_tenant_gotrue(self):
        for header in ("x-user-token", "x-user-groups", "x-user-username"):
            with self.subTest(header=header):
                self.assertIn(f'"{header}"', self.source)


class GotruePathNormalizationTest(unittest.TestCase):
    """Executa a normalizacao real; httpx resolve ../ e sairia da whitelist."""

    @classmethod
    def setUpClass(cls):
        source = read(APP / "routers" / "platform_auth.py")
        import ast

        tree = ast.parse(source)

        class _HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code = status_code

        cls.HTTPException = _HTTPException
        namespace = {
            "HTTPException": _HTTPException,
            "ALLOWED_GOTRUE_ROOTS": (
                "auth/v1/admin/",
                "auth/v1/invite",
                "auth/v1/recover",
                "auth/v1/magiclink",
                "auth/v1/otp",
            ),
            "GOTRUE_PUBLIC_PREFIX": "auth/v1/",
            "GOTRUE_INTERNAL_PORT": 9999,
            "urllib": __import__("urllib.parse", fromlist=["parse"]).parse.__self__
            if False
            else __import__("urllib"),
        }
        import urllib.parse  # noqa: F401  (garante urllib.parse carregado)

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in (
                "_normalized_gotrue_path",
                "_gotrue_internal_url",
            ):
                exec(  # noqa: S102 - executa apenas funcoes puras do proprio repo
                    compile(ast.Module(body=[node], type_ignores=[]), "<contract>", "exec"),
                    namespace,
                )
        cls.normalize = staticmethod(namespace["_normalized_gotrue_path"])
        cls.build_url = staticmethod(namespace["_gotrue_internal_url"])

    def test_allowed_admin_paths_pass_through(self):
        for path in (
            "auth/v1/admin/users",
            "auth/v1/admin/users/8f1d0a9c-0000-4000-8000-000000000000",
            "auth/v1/invite",
            "auth/v1/otp",
            "/auth/v1/admin/users",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.normalize(path))

    def test_dot_segments_are_rejected_before_the_whitelist(self):
        for path in (
            "auth/v1/admin/../../settings",
            "auth/v1/admin/./users",
            "auth/v1/admin/a/../../../b",
            "auth/v1/admin/..\\..\\settings",
        ):
            with self.subTest(path=path):
                with self.assertRaises(self.HTTPException) as ctx:
                    self.normalize(path)
                self.assertEqual(ctx.exception.status_code, 400)

    def test_paths_outside_the_whitelist_are_rejected(self):
        for path in ("auth/v1/settings", "auth/v1/token", "admin/users"):
            with self.subTest(path=path):
                with self.assertRaises(self.HTTPException):
                    self.normalize(path)

    def test_encoded_query_and_fragment_cannot_escape_the_path(self):
        for path, forbidden in (
            ("auth/v1/admin/users?redirect=x", "?"),
            ("auth/v1/admin/users#frag", "#"),
        ):
            with self.subTest(path=path):
                url = self.build_url("demo", self.normalize(path))
                # Tudo depois do host precisa continuar sendo caminho.
                self.assertNotIn(forbidden, url.split("9999/", 1)[1])


class JobAuthorizationTest(unittest.TestCase):
    """Retry reexecuta acoes que as rotas diretas exigem admin do projeto."""

    def setUp(self):
        self.source = read(APP / "routers" / "jobs_api.py")

    def test_retry_revalidates_the_current_project_role(self):
        start = self.source.index("async def retry_project_job(")
        body = self.source[start : start + 2000]
        self.assertIn("ensure_project_admin_access", body)
        self.assertIn('source["project_uuid"]', body)

    def test_status_requires_current_project_access_even_for_the_creator(self):
        start = self.source.index("async def project_status(")
        body = self.source[start :]
        self.assertIn("is_creator", body)
        self.assertIn("FROM project_members pm", body)

    def test_routes_left_main_but_kept_their_paths(self):
        for path in (
            '@router.get("/api/jobs")',
            '@router.post("/api/jobs/{job_id}/retry", status_code=202)',
            '@router.get("/api/projects/status/{job_id}")',
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.source)
        self.assertIn("app.include_router(jobs_router)", read(APP / "asgi.py"))


class MemberRemovalGuardTest(unittest.TestCase):
    def test_owner_membership_cannot_be_removed(self):
        source = read(APP / "main.py")
        start = source.index("async def remove_member_by_ref(")
        body = source[start : start + 3000]
        self.assertIn('project_row["owner_id"]', body)
        self.assertIn("transfira a posse antes", body)

    def test_peer_admin_cannot_remove_another_admin(self):
        source = read(APP / "main.py")
        start = source.index("async def remove_member_by_ref(")
        body = source[start : start + 3000]
        self.assertIn('old_role == "admin"', body)
        self.assertIn('auth_user["is_global_admin"]', body)


class StepUpCoverageTest(unittest.TestCase):
    """Criar/rotacionar/revelar/ativar uma secret key exigem reautenticacao."""

    def test_activation_consumes_a_step_up_grant(self):
        source = read(APP / "routers" / "opaque_keys.py")
        start = source.index("async def activate_api_key_slot(")
        body = source[start : start + 2500]
        self.assertIn('alias="X-Step-Up-Token"', body)
        self.assertIn('action="activate_secret_key"', body)
        self.assertIn('if slot_kind == "secret":', body)

    def test_action_whitelists_agree_across_python_lua_and_database(self):
        python_actions = set(
            re.findall(
                r'"([a-z_]+)"',
                re.search(
                    r"STEP_UP_ACTIONS = frozenset\((.*?)\)",
                    read(APP / "step_up_auth.py"),
                    re.S,
                ).group(1),
            )
        )
        lua_actions = set(
            re.findall(
                r"([a-z_]+) = true",
                re.search(
                    r"local ACTIONS = \{(.*?)\}",
                    read(LUA / "security" / "step_up_authenticate.lua"),
                    re.S,
                ).group(1),
            )
        )
        self.assertEqual(python_actions, lua_actions)

        # O CHECK do banco precisa aceitar exatamente as mesmas acoes, senao o
        # consumo do grant falha com violacao de constraint em runtime.
        migrations = sorted((APP / "migrations").glob("*.sql"))
        allowed: set[str] = set()
        for migration in migrations:
            for match in re.finditer(
                r"action IN \((.*?)\)", read(migration), re.S
            ):
                allowed = set(re.findall(r"'([a-z_]+)'", match.group(1)))
        self.assertEqual(
            allowed,
            python_actions,
            "STEP_UP_ACTIONS divergiu do CHECK em studio_step_up_grant_consumptions",
        )


class ForgedIdentityHeaderTest(unittest.TestCase):
    def test_module_lists_both_identity_families(self):
        lua = read(LUA / "security" / "forged_identity.lua")
        for header in (
            "Remote-User",
            "Remote-Email",
            "Remote-Name",
            "Remote-Groups",
            "X-User-Token",
            "X-User-Groups",
            "X-User-Username",
        ):
            with self.subTest(header=header):
                self.assertIn(f'"{header}"', lua)

    def test_subrequests_keep_the_headers_the_gateway_signed(self):
        lua = read(LUA / "security" / "forged_identity.lua")
        self.assertIn("if ngx.is_subrequest then", lua)
        # /_internal_api/ depende de $http_x_user_token herdado do pai.
        self.assertIn("$http_x_user_token", read(NGINX_CONF))

    def test_stripping_runs_in_the_only_server_level_phase(self):
        conf = read(NGINX_CONF)
        self.assertIn(
            "server_rewrite_by_lua_file /usr/local/openresty/lualib/security/"
            "upload_route_guard.lua;",
            conf,
        )
        guard = read(LUA / "security" / "upload_route_guard.lua")
        self.assertIn('require("security.forged_identity").strip()', guard)
        # Precisa rodar antes de qualquer return early do guard.
        self.assertLess(
            guard.index('require("security.forged_identity").strip()'),
            guard.index("ngx.req.set_uri"),
        )


class UserTokenClaimsTest(unittest.TestCase):
    """Executa o verificador real contra tokens forjados a mao."""

    SECRET = "unit-test-secret"

    @classmethod
    def setUpClass(cls):
        cls.tokens = load_module("security_tokens_contract", APP / "security_tokens.py")

    def make_token(self, **claims):
        payload = dict(
            sub=str(uuid.uuid4()),
            aud=self.tokens.USER_TOKEN_AUDIENCE,
            jti="A" * 22,
            iat=int(time.time()),
            exp=int(time.time()) + 300,
        )
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        encoded = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        signature = hmac.new(
            self.SECRET.encode(), encoded.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"v1.{encoded}.{signature}"

    def resolve(self, token):
        class _Request:
            headers = {"X-User-Token": token}

        return self.tokens.resolve_user_id_from_hmac_token(
            _Request(), secret=self.SECRET, max_clock_skew_seconds=30
        )

    def test_token_for_this_audience_is_accepted(self):
        self.assertIsInstance(self.resolve(self.make_token()), uuid.UUID)

    def test_token_minted_for_another_backend_is_rejected(self):
        with self.assertRaises(Exception) as ctx:
            self.resolve(self.make_token(aud="outro-backend"))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

    def test_token_without_audience_is_still_accepted_during_rollout(self):
        # Gateway e API sobem em momentos distintos; ausencia e tolerada.
        self.assertIsInstance(self.resolve(self.make_token(aud=None, jti=None)), uuid.UUID)

    def test_malformed_jti_is_rejected(self):
        with self.assertRaises(Exception) as ctx:
            self.resolve(self.make_token(jti="curto"))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

    def test_lua_and_python_agree_on_the_audience(self):
        lua = read(LUA / "security" / "user_hmac_token.lua")
        audience = re.search(r'local AUDIENCE = "([^"]+)"', lua).group(1)
        self.assertEqual(audience, self.tokens.USER_TOKEN_AUDIENCE)
        self.assertIn("jti = jti,", lua)


class SharedNonceStoreTest(unittest.TestCase):
    def test_replay_protection_uses_shared_storage(self):
        source = read(APP / "internal_service_auth.py")
        self.assertIn("INSERT INTO internal_hmac_nonces", source)
        self.assertIn("ON CONFLICT (service, nonce) DO UPDATE", source)
        # O cache em memoria vira apenas um filtro previo.
        self.assertIn("_claim_nonce_in_memory", source)
        self.assertIn("_claim_nonce_in_database", source)

    def test_store_outage_fails_closed(self):
        source = read(APP / "internal_service_auth.py")
        self.assertIn("Internal replay protection is unavailable", source)
        self.assertIn("503", source)

    def test_table_is_created_by_a_migration(self):
        migrations = "\n".join(
            read(path) for path in sorted((APP / "migrations").glob("*.sql"))
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS internal_hmac_nonces", migrations)
        self.assertIn("PRIMARY KEY (service, nonce)", migrations)


class StaticSecretsTest(unittest.TestCase):
    def test_studio_container_never_holds_the_real_logflare_token(self):
        """O placeholder no compose e deliberado, nao um segredo estatico.

        O hook Node do Studio remove authorization/x-api-key e assina com
        STUDIO_ANALYTICS_HMAC_SECRET; o gateway valida e injeta o token privado
        real do lado servidor. Dar o token de verdade ao container do Studio
        seria uma regressao, nao uma correcao -- por isso o valor literal e o
        ausencia de .analytics.env no servico sao amarrados aqui.
        """
        compose = read(ROOT / "studio" / "docker-compose.yml")
        studio_service = compose[compose.index("\n  studio:\n") :]
        self.assertIn(
            'LOGFLARE_PRIVATE_ACCESS_TOKEN: "internal-proxy-authenticated"',
            studio_service,
        )
        self.assertNotIn("- .analytics.env", studio_service)
        # Quem injeta o token real e a Projects API, atras do guard HMAC.
        self.assertIn(
            '"x-api-key": LOGFLARE_PRIVATE_ACCESS_TOKEN',
            read(APP / "routers" / "internal.py"),
        )

    def test_authelia_runtime_files_are_not_tracked(self):
        gitignore = read(ROOT / ".gitignore")
        for name in (
            "users_database.yml",
            "ids.yml",
            "db.sqlite3",
            "notifications.txt",
        ):
            with self.subTest(name=name):
                self.assertIn(f"studio/authelia/{name}", gitignore)
        for seed in ("users_database.yml.example", "ids.yml.example"):
            with self.subTest(seed=seed):
                self.assertTrue((ROOT / "studio" / "authelia" / seed).is_file())

    def test_setup_seeds_the_authelia_runtime_without_manual_steps(self):
        tool = read(ROOT / "tools" / "configure_studio_runtime.py")
        self.assertIn("seed_authelia_runtime_files", tool)
        self.assertIn("AUTHELIA_RUNTIME_SEEDS", tool)
        # 0644 e o modo que o checkout do git produzia; o Authelia le no boot.
        self.assertIn('("users_database.yml", 0o644)', tool)
        self.assertIn("python3 tools/configure_studio_runtime.py", read(ROOT / "setup.sh"))


class GatewayTlsSplitTest(unittest.TestCase):
    def test_gateway_serves_a_leaf_not_the_ca_keypair(self):
        conf = read(NGINX_CONF)
        self.assertIn("ssl_certificate /config/ssl/server.pem;", conf)
        self.assertIn("ssl_certificate_key /config/ssl/server.key;", conf)
        self.assertNotIn("ssl_certificate_key /config/ssl/ca.key;", conf)
        # ca.pem continua sendo a ancora de confianca.
        self.assertIn("proxy_ssl_trusted_certificate /config/ssl/ca.pem;", conf)

    def test_authelia_serves_the_same_leaf(self):
        template = read(ROOT / "studio" / "authelia" / "configuration.yml.template")
        self.assertIn("/config/ssl/server.pem", template)
        self.assertNotIn("/config/ssl/ca.key", template)

    def test_leaf_cannot_sign_other_certificates(self):
        tool = read(ROOT / "tools" / "configure_studio_runtime.py")
        self.assertIn("basicConstraints=critical,CA:FALSE", tool)
        self.assertIn("extendedKeyUsage=serverAuth", tool)
        self.assertIn("keyUsage=critical,keyCertSign,cRLSign", tool)

    def test_entrypoint_refuses_a_ca_key_inside_the_bind_mount(self):
        entrypoint = read(ROOT / "studio" / "nginx" / "docker-entrypoint.sh")
        self.assertIn("if [ -e /config/ssl/ca.key ]; then", entrypoint)
        self.assertIn("exit 1", entrypoint)

    def test_ca_rotation_is_explicit(self):
        tool = read(ROOT / "tools" / "configure_studio_runtime.py")
        self.assertIn("--rotate-ca", tool)
        self.assertIn("rotate_ca", tool)


if __name__ == "__main__":
    unittest.main()
