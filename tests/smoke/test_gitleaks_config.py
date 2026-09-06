"""Trava as regras customizadas do gitleaks para as chaves de API.

Dois formatos convivem:

* opaque keys - o formato canonico vive em
  `servidor/api-internal/app/opaque_keys.py` (TOKEN_RE):
  `sb_publishable_|sb_secret_` + 43 base64url + `_` + 8 checksum;
* chaves legadas anon/service_role - JWT HS256 emitido por `generate_jwt()`
  em `servidor/generateProject/lib/*.sh` e `rotate_key.sh`, cujo payload
  sempre comeca por `{"role":"anon",` ou `{"role":"service_role",`.

As regras em `.gitleaks.toml` precisam aceitar exatamente esses formatos e
recusar os placeholders/fixtures que o repo usa em docs e testes.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import secrets
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".gitleaks.toml"

OPAQUE_RULE_IDS = (
    "supabase-multitenant-publishable-key",
    "supabase-multitenant-secret-key",
)

JWT_RULE_IDS = (
    "supabase-multitenant-anon-key-jwt",
    "supabase-multitenant-service-role-key-jwt",
    "supabase-multitenant-role-key-assignment",
)

RULE_IDS = OPAQUE_RULE_IDS + JWT_RULE_IDS

LOOSE_FIXTURES = (
    "sb_publishable_*",
    "sb_secret_*",
    "sb_publishable_<43-char-base64url>_<8-char-checksum>",
    "sb_secret_<43-char-base64url>_<8-char-checksum>",
    '"publishable": "sb_publishable_"',
    '"secret": "sb_secret_"',
    "sb_publishable_one_time_plaintext",
    "sb_secret_widget_one_time_plaintext",
    "token_hint: sb_publishable_abc...xyz",
    "sb_publishable_...test",
    "sb_secret_...test",
)


PROJECT_UUID = "3f1c8a52-9b0e-4d77-8a11-6c2f0d9e4b31"

SYNTHETIC_JWT_FIXTURE = (
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJl"
)

JWT_LOOSE_FIXTURES = (
    "ANON_KEY_PROJETO={{anon_key}}",
    "SERVICE_ROLE_KEY_PROJETO={{service_role_key}}",
    "FUNCTIONS_SUPABASE_ANON_KEY=",
    "FUNCTIONS_SUPABASE_SERVICE_ROLE_KEY=",
    "SERVICE_ROLE_KEY_PROJETO=${SERVICE_ROLE_KEY_PROJETO}",
    "SUPABASE_ANON_KEY=<sua-anon-key>",
    'f"ANON_KEY_PROJETO={jwt}"',
    '"service_role": "sb_secret_widget_one_time_plaintext"',
    f'jwt = "{SYNTHETIC_JWT_FIXTURE}"',
)

ROLE_KEY_HOLDERS = (
    "ANON_KEY_PROJETO",
    "SERVICE_ROLE_KEY_PROJETO",
    "FUNCTIONS_SUPABASE_ANON_KEY",
    "FUNCTIONS_SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GLOBAL_ANON_TOKEN",
    "PLATFORM_LOAD_ANON_KEY",
    "PLATFORM_LOAD_SERVICE_KEY",
    "anon_key",
    "service_role",
)


def _seg(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _jwt(payload: dict[str, object]) -> str:
    """Reproduz generate_jwt() de servidor/generateProject/lib/*.sh."""
    header = _seg(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    body = _seg(json.dumps(payload, separators=(",", ":")).encode())
    return f"{header}.{body}.{_seg(secrets.token_bytes(32))}"


def _role_jwt(role: str) -> str:
    return _jwt(
        {
            "role": role,
            "iss": PROJECT_UUID,
            "iat": 1757000000,
            "exp": 1764776000,
            "jti": secrets.token_hex(16),
        }
    )


def _b64url(nbytes: int, length: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(nbytes)).decode().rstrip(
        "="
    )[:length]


def _load_rule_patterns() -> dict[str, re.Pattern[str]]:
    text = CONFIG.read_text(encoding="utf-8")
    patterns: dict[str, re.Pattern[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("id = "):
            rule_id = stripped.split('"')[1]
            current = rule_id if rule_id in RULE_IDS else None
        elif stripped.startswith("regex = ") and current is not None:
            raw = stripped.split("'''")[1]
            patterns[current] = re.compile(raw)
            current = None
    return patterns


class GitleaksOpaqueKeyRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patterns = _load_rule_patterns()

    def test_both_kinds_have_a_rule(self) -> None:
        for rule_id in RULE_IDS:
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id, self.patterns)

    def test_rules_match_canonical_tokens(self) -> None:
        bodies = {
            "supabase-multitenant-publishable-key": f"sb_publishable_{_b64url(32, 43)}_Ab12Cd34",
            "supabase-multitenant-secret-key": f"sb_secret_{_b64url(32, 43)}_Ef56Gh78",
        }
        for rule_id, token in bodies.items():
            with self.subTest(rule=rule_id):
                self.assertRegex(token, self.patterns[rule_id])

    def test_rules_reject_placeholders_and_fixtures(self) -> None:
        for rule_id, pattern in self.patterns.items():
            for fixture in LOOSE_FIXTURES:
                with self.subTest(rule=rule_id, fixture=fixture):
                    self.assertIsNone(pattern.search(fixture), fixture)

    def test_rules_do_not_cross_match_kinds(self) -> None:
        publishable = f"sb_publishable_{_b64url(32, 43)}_Ab12Cd34"
        secret = f"sb_secret_{_b64url(32, 43)}_Ef56Gh78"
        self.assertIsNone(
            self.patterns["supabase-multitenant-secret-key"].search(publishable)
        )
        self.assertIsNone(
            self.patterns["supabase-multitenant-publishable-key"].search(secret)
        )


class GitleaksRoleKeyRulesTest(unittest.TestCase):
    """anon/service_role sao internos na arquitetura, mas vazam como JWT."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.patterns = _load_rule_patterns()
        cls.anon = _role_jwt("anon")
        cls.service = _role_jwt("service_role")

    def test_every_jwt_rule_exists(self) -> None:
        for rule_id in JWT_RULE_IDS:
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id, self.patterns)

    def test_payload_rules_match_generated_keys(self) -> None:
        cases = {
            "supabase-multitenant-anon-key-jwt": self.anon,
            "supabase-multitenant-service-role-key-jwt": self.service,
        }
        for rule_id, token in cases.items():
            with self.subTest(rule=rule_id):
                self.assertRegex(token, self.patterns[rule_id])

    def test_payload_rules_do_not_cross_match_roles(self) -> None:
        anon_rule = self.patterns["supabase-multitenant-anon-key-jwt"]
        service_rule = self.patterns[
            "supabase-multitenant-service-role-key-jwt"
        ]
        self.assertIsNone(anon_rule.search(self.service))
        self.assertIsNone(service_rule.search(self.anon))

    def test_assignment_rule_covers_every_holder(self) -> None:
        rule = self.patterns["supabase-multitenant-role-key-assignment"]
        for holder in ROLE_KEY_HOLDERS:
            token = self.service if "service" in holder.lower() else self.anon
            for line in (f"{holder}={token}", f'"{holder}": "{token}"'):
                with self.subTest(holder=holder, line=line[:40]):
                    match = rule.search(line)
                    self.assertIsNotNone(match, line)
                    self.assertEqual(match.group(1), token)

    def test_assignment_rule_catches_foreign_claim_order(self) -> None:
        """Chave colada de fora (role nao e a primeira claim)."""
        foreign = _jwt(
            {"iss": "supabase", "ref": "abcdefghij", "role": "service_role"}
        )
        rule = self.patterns["supabase-multitenant-role-key-assignment"]
        self.assertRegex(f"SUPABASE_SERVICE_ROLE_KEY={foreign}", rule)
        self.assertIsNone(
            self.patterns[
                "supabase-multitenant-service-role-key-jwt"
            ].search(foreign),
            "regra de prefixo so cobre payloads do generate_jwt()",
        )

    def test_jwt_rules_reject_repo_placeholders(self) -> None:
        for rule_id in JWT_RULE_IDS:
            pattern = self.patterns[rule_id]
            for fixture in JWT_LOOSE_FIXTURES:
                with self.subTest(rule=rule_id, fixture=fixture[:40]):
                    self.assertIsNone(pattern.search(fixture), fixture)

    def test_synthetic_fixture_needs_no_extra_allowlist(self) -> None:
        for rule_id in JWT_RULE_IDS:
            with self.subTest(rule=rule_id):
                self.assertIsNone(
                    self.patterns[rule_id].search(SYNTHETIC_JWT_FIXTURE)
                )

    def test_opaque_rules_ignore_jwt_keys(self) -> None:
        for rule_id in OPAQUE_RULE_IDS:
            for token in (self.anon, self.service):
                with self.subTest(rule=rule_id):
                    self.assertIsNone(self.patterns[rule_id].search(token))


if __name__ == "__main__":
    unittest.main()
