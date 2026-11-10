"""Public callback assets keep admission checks for protected API paths."""

import importlib.util
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
for name, path in (
    ("access_policy", ROOT / "servidor/api-internal/app/access_policy.py"),
    ("mailer_asset_admission", ROOT / "servidor/key-authorizer/admission.py"),
):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

REF = "abcdefghijklmnopqrst"


class MailerPublicAssetRouteTests(unittest.TestCase):
    def test_migrated_callback_pages_and_assets_use_auth_admission(self):
        for path in (
            "/redefinir-senha.html",
            "/verify-success.html",
            "/verify-success.js",
            "/assets/logo.png",
            "/assets/styles/reset.css",
        ):
            with self.subTest(path=path):
                self.assertEqual(module.route("/" + REF + path, REF)[:3], ("auth", True, ""))

    def test_file_extensions_cannot_bypass_api_key_requirements(self):
        for path, service in (
            ("/auth/v1/logout.html", "auth"),
            ("/rest/v1/table.js", "rest"),
            ("/graphql/v1/query.html", "graphql"),
            ("/functions/v1/function.html", "functions"),
        ):
            with self.subTest(path=path):
                self.assertEqual(module.route("/" + REF + path, REF)[:3], (service, False, ""))

    def test_private_and_noncanonical_paths_remain_rejected(self):
        for path in (
            "/.env", "/secrets/mailer/URL_SECRET", "/config.json",
            "/assets/../private.html", "/assets/%2e%2e/private.html",
            "/assets/a%2fprivate.html", "/a//private.html",
            "/folder/private.sql", "/folder/", "/templates/magic_link",
        ):
            with self.subTest(path=path), self.assertRaises(HTTPException):
                module.route("/" + REF + path, REF)

    def test_project_prefix_cannot_be_replaced(self):
        with self.assertRaises(HTTPException):
            module.route("/bcdefghijklmnopqrstu/redefinir-senha.html", REF)
