from __future__ import annotations

import pathlib
import sys
import unittest
import uuid


ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.opaque_keys import (
    OpaqueKeyError,
    generate_opaque_key,
    normalize_slot_name,
    parse_opaque_key,
    should_preserve_authorization,
    validate_allowed_services,
)
from app.project_env_secrets import read_project_secret_keys


class OpaqueKeyProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_id = uuid.UUID("11111111-2222-4333-8444-555555555555")
        self.entropy = bytes(range(32))

    def test_publishable_and_secret_keys_use_256_bits_and_parse(self) -> None:
        for kind, prefix, role in (
            ("publishable", "sb_publishable_", "anon"),
            ("secret", "sb_secret_", "service_role"),
        ):
            generated = generate_opaque_key(
                self.project_id,
                kind,
                random_bytes=self.entropy,
            )
            self.assertTrue(generated.token.startswith(prefix))
            parsed = parse_opaque_key(self.project_id, generated.token)
            self.assertEqual(parsed.digest, generated.digest)
            self.assertEqual(parsed.kind, kind)
            self.assertEqual(parsed.role, role)
            self.assertNotIn(generated.token, generated.token_hint)

    def test_checksum_binds_key_to_exact_project(self) -> None:
        generated = generate_opaque_key(
            self.project_id,
            "secret",
            random_bytes=self.entropy,
        )
        with self.assertRaises(OpaqueKeyError):
            parse_opaque_key(uuid.uuid4(), generated.token)

    def test_tampering_and_legacy_jwt_are_rejected_before_lookup(self) -> None:
        generated = generate_opaque_key(
            self.project_id,
            "publishable",
            random_bytes=self.entropy,
        )
        tampered = generated.token[:-1] + (
            "A" if generated.token[-1] != "A" else "B"
        )
        with self.assertRaises(OpaqueKeyError):
            parse_opaque_key(self.project_id, tampered)
        with self.assertRaises(OpaqueKeyError):
            parse_opaque_key(self.project_id, "eyJhbGciOiJIUzI1NiJ9.payload.sig")

    def test_authorization_is_unambiguous(self) -> None:
        generated = generate_opaque_key(
            self.project_id,
            "publishable",
            random_bytes=self.entropy,
        )
        self.assertFalse(should_preserve_authorization(generated.token, None))
        self.assertFalse(
            should_preserve_authorization(
                generated.token, f"Bearer {generated.token}"
            )
        )
        self.assertTrue(
            should_preserve_authorization(
                generated.token, "Bearer header.payload.signature"
            )
        )
        other = generate_opaque_key(
            self.project_id,
            "publishable",
            random_bytes=bytes(reversed(range(32))),
        )
        with self.assertRaises(OpaqueKeyError):
            should_preserve_authorization(
                generated.token, f"Bearer {other.token}"
            )
        with self.assertRaises(OpaqueKeyError):
            should_preserve_authorization(generated.token, "Basic abc")
        with self.assertRaises(OpaqueKeyError):
            should_preserve_authorization(
                generated.token, "Bearer header.payload\tsignature"
            )

    def test_slot_names_and_services_are_canonical(self) -> None:
        self.assertEqual(normalize_slot_name("billing_worker"), "billing_worker")
        self.assertEqual(
            validate_allowed_services(["storage", "rest"]),
            ("rest", "storage"),
        )
        with self.assertRaises(OpaqueKeyError):
            normalize_slot_name("x")
        with self.assertRaises(OpaqueKeyError):
            normalize_slot_name(" Billing_Worker ")
        with self.assertRaises(OpaqueKeyError):
            validate_allowed_services(["storage", "storage"])
        with self.assertRaises(OpaqueKeyError):
            validate_allowed_services(["database"])

    def test_entropy_and_token_encoding_are_exact(self) -> None:
        with self.assertRaises(OpaqueKeyError):
            generate_opaque_key(
                self.project_id,
                "publishable",
                random_bytes=b"short",
            )
        generated = generate_opaque_key(
            self.project_id,
            "publishable",
            random_bytes=self.entropy,
        )
        for noncanonical in (
            f" {generated.token}",
            f"{generated.token} ",
            generated.token.upper(),
            f"{generated.token}=",
        ):
            with self.subTest(noncanonical=noncanonical):
                with self.assertRaises(OpaqueKeyError):
                    parse_opaque_key(self.project_id, noncanonical)

    def test_project_secret_lookup_rejects_path_traversal_before_io(self) -> None:
        for project_name in ("..", "valid/../../escape", "UPPERCASE"):
            with self.subTest(project_name=project_name):
                with self.assertRaises(RuntimeError):
                    read_project_secret_keys(project_name)


class OpaqueKeyContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = (API_ROOT / "app" / "opaque_key_service.py").read_text(
            encoding="utf-8"
        )
        cls.router = (
            API_ROOT / "app" / "routers" / "opaque_keys.py"
        ).read_text(encoding="utf-8")
        cls.main = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        cls.authorizer = (
            ROOT / "servidor" / "key-authorizer" / "app.py"
        ).read_text(encoding="utf-8")
        cls.nginx = (
            ROOT / "servidor" / "generateProject" / "nginxtemplate"
        ).read_text(encoding="utf-8")
        cls.compose = (
            ROOT / "servidor" / "docker-compose-api.yml"
        ).read_text(encoding="utf-8")
        cls.traefik = (
            ROOT / "servidor" / "traefik" / "traefik.yml"
        ).read_text(encoding="utf-8")
        cls.scheduler = (
            API_ROOT / "app" / "automatic_opaque_key_rotation.py"
        ).read_text(encoding="utf-8")
        cls.host_protocol_api = (
            API_ROOT / "app" / "host_agent_protocol.py"
        ).read_text(encoding="utf-8")
        cls.host_protocol_agent = (
            ROOT
            / "servidor"
            / "host-agent"
            / "hostagent"
            / "host_agent_protocol.py"
        ).read_text(encoding="utf-8")

    def test_schema_enforces_one_active_and_pending_key_per_slot(self) -> None:
        self.assertIn("idx_project_api_keys_one_active", self.service)
        self.assertIn("WHERE status = 'active'", self.service)
        self.assertIn("idx_project_api_keys_one_pending", self.service)
        self.assertIn("WHERE status = 'pending'", self.service)
        self.assertIn("secret_hash BYTEA NOT NULL UNIQUE", self.service)

    def test_management_routes_are_canonical_and_no_store(self) -> None:
        self.assertIn('/{project_name}/api-key-slots"', self.router)
        self.assertIn('/{project_name}/api-key-slots/{slot_id}/rotation"', self.router)
        self.assertIn('/{project_name}/api-key-slots/{slot_id}/activation"', self.router)
        self.assertIn('/{project_name}/api-key-reveals/{key_id}/claim"', self.router)
        self.assertIn('"Cache-Control": "no-store, max-age=0"', self.router)
        self.assertIn('extra = "forbid"', self.router)
        self.assertIn("host-agent omitted error_code", self.router)
        self.assertNotIn('command["message"]\n                or', self.router)
        self.assertNotIn("/legacy-api-key", self.router.lower())

    def test_schema_and_router_are_registered_at_startup(self) -> None:
        self.assertIn("app.include_router(opaque_keys_router)", self.main)
        self.assertIn("await ensure_opaque_key_schema(pool)", self.main)

    def test_authorizer_binds_key_to_project_gateway_and_service(self) -> None:
        for contract in (
            "api_gateway_token_hash",
            "hmac.compare_digest(provided_gateway_hash, stored_gateway_hash)",
            "s.project_id = $1",
            "k.secret_hash = $2",
            "target_service not in key[\"allowed_services\"]",
            "k.expires_at > now()",
            "k.confirmed_at IS NOT NULL",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.authorizer)
        self.assertIn("status_code=503", self.authorizer)
        self.assertNotIn("ANON_KEY_PROJETO", self.authorizer)
        self.assertNotIn("SERVICE_ROLE_KEY_PROJETO", self.authorizer)
        self.assertNotIn('x_allow_missing_key or "0"', self.authorizer)

    def test_scheduled_cutover_is_monotonic_even_after_pending_expiry(self) -> None:
        for source in (self.authorizer, self.service):
            due_start = source.index("FROM project_api_keys due")
            due_clause = source[due_start : due_start + 500]
            self.assertIn("due.confirmed_at IS NOT NULL", due_clause)
            self.assertNotIn("due.expires_at > now()", due_clause)
        self.assertIn(
            "an effective pending API key cannot be cancelled", self.service
        )
        self.assertIn(
            "effective pending API key replacement conflicted", self.service
        )
        self.assertIn(
            "activate_at cannot be later than the active API key expiration",
            self.service,
        )
        self.assertIn('await conn.fetchval("SELECT now()")', self.service)
        self.assertNotIn("_utcnow", self.service)
        self.assertGreaterEqual(self.service.count("activate_at <= now()"), 3)

    def test_nginx_uses_fail_closed_auth_subrequests_for_protected_services(self) -> None:
        self.assertIn("internal;", self.nginx)
        self.assertIn("proxy_pass_request_headers off;", self.nginx)
        self.assertGreaterEqual(
            self.nginx.count("auth_request /_internal/opaque-key-authorize;"),
            7,
        )
        for service in (
            "auth",
            "rest",
            "graphql",
            "realtime",
            "storage",
            "functions",
        ):
            self.assertIn(f"set $opaque_target_service {service};", self.nginx)
        self.assertIn("proxy_set_header x-api-key $opaque_upstream_apikey;", self.nginx)
        realtime_start = self.nginx.index(
            "location ^~ /realtime/v1/websocket"
        )
        realtime_end = self.nginx.index(
            "location /storage/v1/", realtime_start
        )
        self.assertIn(
            "proxy_set_header Authorization $opaque_upstream_authorization;",
            self.nginx[realtime_start:realtime_end],
        )
        self.assertIn("access_log off;", self.nginx[realtime_start:realtime_end])
        self.assertIn("queryParameters:", self.traefik)
        self.assertIn("defaultMode: drop", self.traefik)
        for public_auth_path in ("verify", "callback", "authorize"):
            self.assertIn(
                f"location = /auth/v1/{public_auth_path} {{",
                self.nginx,
            )
        self.assertNotIn("map $http_apikey $is_valid_key", self.nginx)
        self.assertNotIn('"anon_key"', self.nginx)

    def test_data_plane_database_role_is_least_privilege(self) -> None:
        for contract in (
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT",
            "NOREPLICATION NOBYPASSRLS",
            "REVOKE ALL ON ALL TABLES IN SCHEMA public",
            "GRANT SELECT (",
            "GRANT UPDATE (last_used_at)",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.service)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertIn("cap_drop:", self.compose)

    def test_migration_is_preflighted_before_gateway_cutover(self) -> None:
        preflight = self.router.index("await validate_prepared_project_opaque_keys(")
        cutover_state = self.router.index(
            "SET opaque_gateway_cutover_started_at = COALESCE("
        )
        stage = self.router.index('command="stage_opaque_gateway"')
        activation = self.router.index("await activate_prepared_project_opaque_keys(")
        self.assertLess(preflight, cutover_state)
        self.assertLess(cutover_state, stage)
        self.assertLess(stage, activation)
        self.assertIn("revealed_at", self.service)
        self.assertIn("confirmed_at", self.service)
        self.assertIn("cannot be aborted after cutover starts", self.service)

    def test_automatic_rotation_only_runs_for_ready_opaque_gateways(self) -> None:
        self.assertIn(
            "p.opaque_gateway_ready_at IS NOT NULL",
            self.scheduler,
        )
        self.assertIn("pending_replacement_not_confirmed_before_cutover", self.scheduler)
        self.assertIn("active_key_expired_without_pending_replacement", self.scheduler)
        self.assertIn(
            "DELETE FROM project_api_key_reveals WHERE expires_at <= now()",
            self.scheduler,
        )
        self.assertGreaterEqual(
            self.scheduler.count("k.rotation_trigger = 'automatic'"), 2
        )

    def test_host_agent_protocol_copies_are_identical(self) -> None:
        self.assertEqual(self.host_protocol_api, self.host_protocol_agent)
        self.assertIn('"ensure_opaque_gateway_token": 120', self.host_protocol_api)
        self.assertIn('"stage_opaque_gateway": 600', self.host_protocol_api)


if __name__ == "__main__":
    unittest.main()
