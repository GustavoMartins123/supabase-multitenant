"""Trava as regras customizadas do gitleaks para as opaque API keys.

O formato canonico vive em `servidor/api-internal/app/opaque_keys.py`
(TOKEN_RE): `sb_publishable_|sb_secret_` + 43 base64url + `_` + 8 checksum.
As regras em `.gitleaks.toml` precisam aceitar exatamente esse formato e
recusar os placeholders/fixtures que o repo usa em docs e testes.
"""

from __future__ import annotations

import pathlib
import re
import secrets
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".gitleaks.toml"

RULE_IDS = (
    "supabase-multitenant-publishable-key",
    "supabase-multitenant-secret-key",
)

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


def _b64url(nbytes: int, length: int) -> str:
    import base64

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


if __name__ == "__main__":
    unittest.main()
