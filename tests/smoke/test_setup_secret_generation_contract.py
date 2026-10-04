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
import os
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]

IDENTITY_PASSWORD_RE = re.compile(
    r"^(KEY_AUTHORIZER|HOST_AGENT|PLATFORM_READER|PLATFORM_APP|META_ADMIN|CLIENT_CONFIGURATION)"
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
                self.assertIsNotNone(
                    re.search(
                        rf"{key}=\$\(env_secret \S+ {key} generate_key_authorizer_password\)",
                        self.setup,
                    )
                )
                if key == 'CLIENT_CONFIGURATION_DB_PASSWORD':
                    self.assertIn("content = _set_env_value(content, key, os.environ[key])", self.setup)
                else:
                    self.assertIn(f'safe_sed "s|{key}=pass|{key}=${key}|g"', self.setup)

    def test_discovery_identity_is_added_to_existing_env_without_touching_other_secrets(self):
        marker = 'CLIENT_CONFIGURATION_DB_PASSWORD="$CLIENT_CONFIGURATION_DB_PASSWORD" python3 - <<\'PYEOF\'\n'
        code = self.setup.split(marker, 1)[1].split('\nPYEOF', 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary) / 'servidor'
            directory.mkdir()
            env_file = directory / '.env'
            values = {**os.environ, 'PYTHONPATH': str(ROOT), 'CLIENT_CONFIGURATION_DB_PASSWORD': 'a'*64}
            for original in ('OTHER_SECRET=preserved\n', 'OTHER_SECRET=preserved\nCLIENT_CONFIGURATION_DB_PASSWORD=pass\n'):
                env_file.write_text(original, encoding='utf-8')
                subprocess.run([sys.executable, '-c', code], cwd=temporary, env=values, check=True, capture_output=True)
                self.assertEqual(env_file.read_text(), 'OTHER_SECRET=preserved\nCLIENT_CONFIGURATION_DB_PASSWORD='+'a'*64+'\n')
            env_file.write_text('CLIENT_CONFIGURATION_DB_PASSWORD=pass\nCLIENT_CONFIGURATION_DB_PASSWORD=pass\n', encoding='utf-8')
            self.assertNotEqual(subprocess.run([sys.executable, '-c', code], cwd=temporary, env=values, capture_output=True).returncode, 0)

    def test_generated_values_match_the_format_validators(self) -> None:
        # generate_key_authorizer_password produz hex de 64 caracteres,
        # aceito pelos validadores [A-Za-z0-9_-]{32,128} de
        # control_plane_roles.py e install.sh.
        self.assertIn("generate_key_authorizer_password() {", self.setup)
        body = self.setup[
            self.setup.index("generate_key_authorizer_password() {"):
        ]
        self.assertRegex(body, r"openssl rand -hex 32\n")

    def test_setup_provisions_shared_service_hmacs_before_runtime(self) -> None:
        for key in ("STUDIO_GATEWAY_HMAC_SECRET", "PROJECTS_API_HMAC_SECRET"):
            self.assertIn(
                f"{key}=$(env_secret servidor/.env {key} generate_hmac_secret)",
                self.setup,
            )
            for env in ("servidor/.env", "studio/.env"):
                self.assertIn(
                    f'safe_sed "s|^{key}=.*|{key}=${key}|g" {env}', self.setup
                )

    def test_analytics_secret_is_required_only_in_studio(self) -> None:
        self.assertNotIn(
            "for required_key in STUDIO_GATEWAY_HMAC_SECRET PROJECTS_API_HMAC_SECRET STUDIO_ANALYTICS_HMAC_SECRET",
            self.setup,
        )
        self.assertIn("read_env_value studio/.env STUDIO_ANALYTICS_HMAC_SECRET", self.setup)

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
