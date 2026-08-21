from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import types
import unittest
import warnings
from typing import Literal

from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse


ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICE = ROOT / "servidor/api-internal/app/opaque_key_service.py"
ROUTER = ROOT / "servidor/api-internal/app/routers/opaque_keys.py"
SCHEDULER = ROOT / "servidor/api-internal/app/automatic_opaque_key_rotation.py"
AUTHORIZER = ROOT / "servidor/key-authorizer/app.py"
MIGRATION = (
    ROOT
    / "servidor/api-internal/app/migrations"
    / "0003_opaque_api_key_optional_expiration.sql"
)
BASELINE = (
    ROOT
    / "servidor/api-internal/app/migrations"
    / "0001_control_plane_baseline.sql"
)
PERSISTENT_REVEALS = (
    ROOT
    / "servidor/api-internal/app/migrations"
    / "0004_persistent_api_key_reveals.sql"
)
STUDIO_MODEL = (
    ROOT / "studio/seletor_de_projetos/lib/models/opaque_api_key.dart"
)
STUDIO_WIDGET = (
    ROOT
    / "studio/seletor_de_projetos/lib/widgets/project_settings"
    / "opaque_api_keys_section.dart"
)


def _load_pure_service_function(name: str):
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    pure_function_names = {
        "_expiration_for_policy_transition",
        "_expiration_from_policy",
        "_validate_slot_lifecycle",
    }
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in pure_function_names
    ]
    module = ast.Module(body=functions, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"dt": dt, "OpaqueKeyLifecycleError": ValueError}
    exec(compile(module, str(SERVICE), "exec"), namespace)
    return namespace[name]


def _load_router_models():
    wanted = {
        "OpaqueKeyRequest",
        "CreateApiKeySlot",
        "UpdateApiKeySlotPolicy",
    }
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    module = ast.Module(body=classes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "ALLOWED_SERVICES": {
            "auth",
            "rest",
            "graphql",
            "realtime",
            "storage",
            "functions",
        },
        "BaseModel": BaseModel,
        "DEFAULT_ROTATION_INTERVAL_DAYS": 90,
        "Field": Field,
        "Literal": Literal,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        exec(compile(module, str(ROUTER), "exec"), namespace)
    namespace["CreateApiKeySlot"].model_rebuild(_types_namespace=namespace)
    namespace["UpdateApiKeySlotPolicy"].model_rebuild(
        _types_namespace=namespace
    )
    return namespace


def _load_issued_response():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_issued_response"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "JSONResponse": JSONResponse,
        "NO_STORE_HEADERS": {
            "Cache-Control": "no-store, max-age=0",
        },
    }
    exec(compile(module, str(ROUTER), "exec"), namespace)
    return namespace["_issued_response"]


class OptionalOpaqueKeyExpirationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.scheduler = SCHEDULER.read_text(encoding="utf-8")
        cls.authorizer = AUTHORIZER.read_text(encoding="utf-8")
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.studio_model = STUDIO_MODEL.read_text(encoding="utf-8")
        cls.studio_widget = STUDIO_WIDGET.read_text(encoding="utf-8")

    def test_creation_policy_calculates_timestamp_or_never(self) -> None:
        expiration_from_policy = _load_pure_service_function(
            "_expiration_from_policy"
        )
        now = dt.datetime(2026, 8, 12, tzinfo=dt.timezone.utc)
        self.assertIsNone(expiration_from_policy(now, None))
        self.assertEqual(
            expiration_from_policy(now, 90),
            now + dt.timedelta(days=90),
        )
        self.assertIn(
            "expires_at=_expiration_from_policy(now, interval)", self.service
        )

    def test_policy_transitions_cover_both_directions_without_resurrection(
        self,
    ) -> None:
        transition = _load_pure_service_function(
            "_expiration_for_policy_transition"
        )
        now = dt.datetime(2026, 8, 12, tzinfo=dt.timezone.utc)
        self.assertIsNone(
            transition(
                now=now,
                current_expires_at=now + dt.timedelta(days=10),
                rotation_interval_days=None,
            )
        )
        self.assertEqual(
            transition(
                now=now,
                current_expires_at=None,
                rotation_interval_days=180,
            ),
            now + dt.timedelta(days=180),
        )
        with self.assertRaisesRegex(
            ValueError,
            "an expired API key cannot be revived by a policy change",
        ):
            transition(
                now=now,
                current_expires_at=now,
                rotation_interval_days=None,
            )

    def test_never_policy_cannot_enable_automatic_rotation(self) -> None:
        validate_slot_lifecycle = _load_pure_service_function(
            "_validate_slot_lifecycle"
        )
        validate_slot_lifecycle(
            automatic_rotation_enabled=False,
            rotation_interval_days=None,
        )
        validate_slot_lifecycle(
            automatic_rotation_enabled=True,
            rotation_interval_days=90,
        )
        with self.assertRaisesRegex(
            ValueError,
            "automatic rotation requires a temporal expiration interval",
        ):
            validate_slot_lifecycle(
                automatic_rotation_enabled=True,
                rotation_interval_days=None,
            )

    def test_authorizer_accepts_never_but_rejects_expired_timed_key(self) -> None:
        self.assertIn(
            "(k.expires_at IS NULL OR k.expires_at > now())",
            self.authorizer,
        )
        self.assertNotIn("COALESCE(k.expires_at", self.authorizer)
        self.assertNotIn("9999", self.authorizer)

    def test_revocation_disable_and_allowed_services_remain_authoritative(self) -> None:
        for contract in (
            "s.status = 'active'",
            "k.status = 'active'",
            "k.status = 'pending'",
            'target_service not in key["allowed_services"]',
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.authorizer)
        self.assertIn("status IN ('active', 'pending')", self.service)

    def test_scheduler_ignores_never_for_expiration_and_lead_time(self) -> None:
        candidates = self.scheduler[self.scheduler.index("candidates =") :]
        self.assertIn("s.rotation_interval_days IS NOT NULL", candidates)
        self.assertIn("k.expires_at IS NOT NULL", candidates)
        self.assertIn(
            "k.expires_at <= now() + make_interval(days => $1)", candidates
        )
        expired = self.scheduler[
            self.scheduler.index("expired =") : self.scheduler.index(
                "candidates ="
            )
        ]
        self.assertIn("k.expires_at IS NOT NULL", expired)

    def test_scheduler_and_authorizer_keep_manual_pending_cutover(self) -> None:
        self.assertIn(
            "(k.expires_at IS NULL OR k.expires_at > now())", self.scheduler
        )
        self.assertIn(
            "expires_at=_expiration_from_policy(\n"
            "            activate_at, slot[\"rotation_interval_days\"]",
            self.service,
        )
        for source in (self.authorizer, self.service):
            due = source[source.index("FROM project_api_keys due") :]
            self.assertIn("due.confirmed_at IS NOT NULL", due)

    def test_hard_rotation_preserves_never_policy(self) -> None:
        rotation = self.service[
            self.service.index("async def rotate_slot_immediately") :
            self.service.index("async def prepare_slot_rotation")
        ]
        self.assertIn(
            "expires_at=_expiration_from_policy(", rotation
        )
        self.assertIn('slot["rotation_interval_days"]', rotation)
        self.assertIn("SET status = 'revoked', revoked_at = now()", rotation)

    def test_key_plaintext_survives_every_read(self) -> None:
        migration = PERSISTENT_REVEALS.read_text(encoding="utf-8")
        self.assertIn(
            "ALTER TABLE project_api_key_reveals\n    DROP COLUMN IF EXISTS expires_at",
            migration,
        )
        self.assertNotIn("REVEAL_TTL_MINUTES", self.service)
        self.assertNotIn("r.expires_at", self.service)
        self.assertNotIn("reveal_once", self.router)

        claim = self.service[
            self.service.index("async def claim_key_reveal") :
            self.service.index("async def list_slots")
        ]
        self.assertNotIn("DELETE FROM project_api_key_reveals", claim)
        self.assertIn("SELECT r.ciphertext", claim)
        self.assertIn("coalesce(revealed_at, now())", claim)

    def test_api_and_studio_serialize_and_render_never(self) -> None:
        self.assertIn(
            "issued.expires_at.isoformat() if issued.expires_at else None",
            self.router,
        )
        self.assertIn("DateTime? expiresAt", self.studio_model)
        self.assertIn("int? rotationIntervalDays", self.studio_model)
        self.assertIn("Não expira", self.studio_widget)
        self.assertIn("Personalizado", self.studio_widget)

        issued_response = _load_issued_response()
        response = issued_response(
            types.SimpleNamespace(
                slot_id="slot-id",
                key_id="key-id",
                token="plaintext-once",
                token_hint="sb_publishable_abc...xyz",
                kind="publishable",
                status="active",
                activate_at=None,
                expires_at=None,
            ),
            2,
            status_code=201,
        )
        payload = json.loads(response.body)
        self.assertIsNone(payload["expires_at"])
        self.assertNotIn("reveal_once", payload)

    def test_api_distinguishes_omitted_interval_from_explicit_null(self) -> None:
        models = _load_router_models()
        update_model = models["UpdateApiKeySlotPolicy"]
        omitted = update_model()
        never = update_model(rotation_interval_days=None)
        self.assertNotIn("rotation_interval_days", omitted.model_fields_set)
        self.assertIn("rotation_interval_days", never.model_fields_set)

        create_model = models["CreateApiKeySlot"]
        created = create_model(
            name="web-production",
            kind="publishable",
            automatic_rotation_enabled=False,
            rotation_interval_days=None,
        )
        self.assertIsNone(created.rotation_interval_days)

    def test_policy_transitions_are_explicit_and_cannot_resurrect(self) -> None:
        self.assertIn("rotation_interval_days_provided", self.service)
        self.assertIn(
            "expiration policy cannot change while the slot has a pending key",
            self.service,
        )
        self.assertIn(
            "an expired API key cannot be revived by a policy change",
            self.service,
        )
        self.assertIn(
            "AND (expires_at IS NULL OR expires_at > now())", self.service
        )
        self.assertIn("model_fields_set", self.router)

    def test_migration_is_additive_and_preserves_existing_expirations(self) -> None:
        self.assertIn("ALTER COLUMN expires_at DROP NOT NULL", self.migration)
        self.assertIn(
            "ALTER COLUMN rotation_interval_days DROP NOT NULL", self.migration
        )
        self.assertIn(
            "expires_at IS NULL OR expires_at > created_at", self.migration
        )
        self.assertIn(
            "WHERE status = 'active' AND expires_at IS NOT NULL", self.migration
        )
        self.assertNotIn("UPDATE project_api_keys", self.migration)
        self.assertNotIn("UPDATE project_api_key_slots", self.migration)


if __name__ == "__main__":
    unittest.main()
