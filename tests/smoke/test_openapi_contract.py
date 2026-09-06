"""Contrato de estabilidade do OpenAPI publicado em docs/api/openapi.json."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import unittest
import warnings

ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DB_DSN", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("HOST_AGENT_HMAC_SECRET", "x" * 32)
try:
    from cryptography.fernet import Fernet

    _keys = [Fernet.generate_key().decode() for _ in range(3)]
except Exception:
    _keys = ["x" * 44, "y" * 44, "z" * 44]
os.environ.setdefault("PROJECT_SECRETS_MASTER_KEY", _keys[0])
os.environ.setdefault("PG_META_CRYPTO_KEY", _keys[1])
os.environ.setdefault("STUDIO_SERVICE_KEY_ENCRYPTION_KEY", _keys[2])
os.environ.setdefault("NGINX_HMAC_SECRET", "v" * 32)
os.environ.setdefault("STUDIO_GATEWAY_HMAC_SECRET", "u" * 32)
os.environ.setdefault("PROJECTS_API_HMAC_SECRET", "t" * 32)
os.environ.setdefault("LOGFLARE_PRIVATE_ACCESS_TOKEN", "s" * 16)

EXPECTED_TAGS = {
    "collaboration",
    "internal",
    "jobs",
    "lifecycle",
    "lifecycle-ops",
    "opaque-api-keys",
    "platform-auth",
    "project-insights",
    "project-keys",
    "project-members",
    "project-rename",
    "projects",
    "restore-points",
}


class OpenApiStabilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message=".*Duplicate Operation ID.*")
            from app.asgi import app as asgi_app

            cls.schema = asgi_app.openapi()
        from app.version import API_VERSION

        cls.api_version = API_VERSION

    def test_info_matches_the_single_version_source(self) -> None:
        self.assertEqual(self.schema["info"]["title"], "Supabase Multitenant Projects API")
        self.assertEqual(self.schema["info"]["version"], self.api_version)
        self.assertEqual(self.schema["info"]["license"]["name"], "Apache-2.0")

    def test_every_router_is_tagged(self) -> None:
        tags: set[str] = set()
        for item in self.schema["paths"].values():
            for operation in item.values():
                if isinstance(operation, dict):
                    tags.update(operation.get("tags", []))
        for expected in EXPECTED_TAGS:
            with self.subTest(tag=expected):
                self.assertIn(expected, tags)

    def test_operation_ids_are_unique_and_stable(self) -> None:
        seen: dict[str, str] = {}
        for path, item in self.schema["paths"].items():
            for method, operation in item.items():
                if method == "parameters" or not isinstance(operation, dict):
                    continue
                operation_id = operation.get("operationId")
                self.assertTrue(operation_id, f"{method} {path}")
                label = f"{method.upper()} {path}"
                if operation_id in seen:
                    self.fail(f"duplicate operationId {operation_id}: {seen[operation_id]} vs {label}")
                seen[operation_id] = label
        self.assertGreaterEqual(len(seen), 60)

    def test_committed_artifact_is_in_sync(self) -> None:
        target = ROOT / "docs" / "api" / "openapi.json"
        self.assertTrue(target.is_file(), "run python tools/export_openapi.py")
        rendered = json.dumps(self.schema, indent=2, sort_keys=True) + "\n"
        self.assertEqual(target.read_text(encoding="utf-8"), rendered)


if __name__ == "__main__":
    unittest.main()
