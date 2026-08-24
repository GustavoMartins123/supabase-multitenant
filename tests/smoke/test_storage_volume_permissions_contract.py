"""Contrato de permissoes do volume do Storage compartilhado.

Fixa a correcao do chmod 777 (REVISAO_ARQUITETURAL #1): o volume passa a
exigir alinhamento explicito entre o UID do operador/host-agent e o
STORAGE_RUN_AS_USER, com diretorios 2775 (setgid) em vez de world-writable.
"""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPTS = (
    ROOT / "start.sh",
    ROOT / "setup.sh",
    ROOT / "servidor" / "host-agent" / "install.sh",
)


class NoWorldWritableStorageVolumeTest(unittest.TestCase):
    def test_no_script_applies_chmod_777_to_the_storage_volume(self) -> None:
        for script in SCRIPTS:
            with self.subTest(script=str(script)):
                self.assertNotIn("chmod 777", script.read_text(encoding="utf-8"))

    def test_scripts_apply_setgid_group_writable_mode(self) -> None:
        for script in SCRIPTS:
            source = script.read_text(encoding="utf-8")
            with self.subTest(script=str(script)):
                self.assertIn("chmod 2775", source)
                self.assertIn("volumes/storage", source)


class StorageUidAlignmentContractTest(unittest.TestCase):
    def test_start_and_setup_fail_closed_on_uid_mismatch(self) -> None:
        for script_name in ("start.sh", "setup.sh"):
            source = (ROOT / script_name).read_text(encoding="utf-8")
            with self.subTest(script=script_name):
                self.assertIn("STORAGE_RUN_AS_USER=", source)
                self.assertIn('id -u', source)
                self.assertIn("storage_uid", source)

    def test_installer_validates_service_user_against_storage_uid(self) -> None:
        source = (
            ROOT / "servidor" / "host-agent" / "install.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("id -u \"$SERVICE_USER\"", source)
        self.assertIn("HOST_AGENT_USER ou STORAGE_RUN_AS_USER", source)
        # O chown dos diretorios raiz so acontece apos a validacao.
        self.assertLess(
            source.index('storage_run_as="$(sed'),
            source.index('chown "$storage_uid:$storage_uid"'),
        )

    def test_env_example_documents_the_run_as_user(self) -> None:
        import re

        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r"^STORAGE_RUN_AS_USER=\d+:\d+$", example, re.M)
        )


if __name__ == "__main__":
    unittest.main()
