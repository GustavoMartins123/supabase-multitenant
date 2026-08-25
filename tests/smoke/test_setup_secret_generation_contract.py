"""Toda senha de identidade nova precisa nascer preenchida pelo setup.sh.

O cutover estrito das identidades de banco (host_agent_rw, platform_app,
platform_meta_admin, platform_reader, key_authorizer) e fail-closed: se o
setup esquecer de gerar uma delas, a instalacao limpa quebra na porta
seguinte (install.sh do agent ou compose das migrations). Este contrato
deriva as chaves diretamente do .env.example para que uma nova identidade
adicionada la precise, obrigatoriamente, de geracao no setup.
"""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]

IDENTITY_PASSWORD_RE = re.compile(
    r"^(KEY_AUTHORIZER|HOST_AGENT|PLATFORM_READER|PLATFORM_APP|META_ADMIN)"
    r"_DB_PASSWORD=(pass)$"
)


class SetupSecretGenerationContract(unittest.TestCase):
    def setUp(self) -> None:
        self.example = (
            ROOT / "servidor" / ".env.example"
        ).read_text(encoding="utf-8")
        self.setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

    def _identity_keys(self) -> list[str]:
        keys = [
            match.group(0).split("=", 1)[0]
            for line in self.example.splitlines()
            if (match := IDENTITY_PASSWORD_RE.match(line))
        ]
        self.assertGreaterEqual(len(keys), 5, "identidades de banco mudaram?")
        return sorted(set(keys))

    def test_setup_generates_every_identity_password(self) -> None:
        for key in self._identity_keys():
            with self.subTest(key=key):
                self.assertIn(f"{key}=$(generate_key_authorizer_password)", self.setup)
                self.assertIn(f'safe_sed "s|{key}=pass|{key}=${key}|g"', self.setup)

    def test_generated_values_match_the_format_validators(self) -> None:
        # generate_key_authorizer_password produz hex de 64 caracteres,
        # aceito pelos validadores [A-Za-z0-9_-]{32,128} de
        # control_plane_roles.py e install.sh.
        self.assertIn("generate_key_authorizer_password() {", self.setup)
        body = self.setup[
            self.setup.index("generate_key_authorizer_password() {"):
        ]
        self.assertRegex(body, r"openssl rand -hex 32\n")

    def test_env_example_has_no_other_placeholder_db_password(self) -> None:
        leftovers = [
            line.split("=", 1)[0]
            for line in self.example.splitlines()
            if line.startswith(("DB_PASSWORD=", "PASSWORD=")) or
            ("_PASSWORD=pass" in line and not IDENTITY_PASSWORD_RE.match(line)
             and not line.startswith(("#", "POSTGRES_PASSWORD=", "SMTP_PASS",
                                      "DASHBOARD_PASSWORD=", "META_GUEST_PASSWORD=")))
        ]
        self.assertEqual(leftovers, [], f"senhas sem contrato de geracao: {leftovers}")


if __name__ == "__main__":
    unittest.main()
