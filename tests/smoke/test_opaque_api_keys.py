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
        self.assertNotIn("/legacy-api-key", self.router.lower())

    def test_schema_and_router_are_registered_at_startup(self) -> None:
        self.assertIn("app.include_router(opaque_keys_router)", self.main)
        self.assertIn("await ensure_opaque_key_schema(pool)", self.main)


if __name__ == "__main__":
    unittest.main()
