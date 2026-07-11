from __future__ import annotations

import importlib
import sys
import unittest
import uuid
from pathlib import Path

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

secrets = importlib.import_module("app.project_secrets")


class ProjectSecretEnvelopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.master = Fernet.generate_key().decode()
        self.manager = secrets.ProjectSecretManager(
            self.master,
            wrapping_key_id="master-2026-07",
        )
        self.project_id = uuid.uuid4()
        self.envelope, self.dek = self.manager.create_envelope()

    def test_round_trip_and_project_binding(self) -> None:
        ciphertext = self.manager.encrypt(
            project_id=self.project_id,
            purpose="service_role",
            key_id=self.envelope.key_id,
            dek=self.dek,
            plaintext="super-secret",
        )
        self.assertTrue(secrets.ProjectSecretManager.is_v2(ciphertext))
        self.assertEqual(
            self.manager.decrypt(
                project_id=self.project_id,
                purpose="service_role",
                key_id=self.envelope.key_id,
                dek=self.dek,
                ciphertext=ciphertext,
            ),
            "super-secret",
        )
        with self.assertRaises(secrets.ProjectSecretError):
            self.manager.decrypt(
                project_id=uuid.uuid4(),
                purpose="service_role",
                key_id=self.envelope.key_id,
                dek=self.dek,
                ciphertext=ciphertext,
            )

    def test_previous_master_key_can_unwrap_existing_envelope(self) -> None:
        old_master = Fernet.generate_key().decode()
        old_manager = secrets.ProjectSecretManager(
            old_master,
            wrapping_key_id="master-old",
        )
        envelope, dek = old_manager.create_envelope()
        new_manager = secrets.ProjectSecretManager(
            self.master,
            wrapping_key_id="master-new",
            previous_master_keys=(old_master,),
        )
        self.assertEqual(new_manager.unwrap_dek(envelope), dek)


if __name__ == "__main__":
    unittest.main()
