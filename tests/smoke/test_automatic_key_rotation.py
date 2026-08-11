from __future__ import annotations

import base64
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.key_rotation import KeyRotationMetadataError, project_key_schedule


def _token(expiry: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": expiry}, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


class KeyScheduleTest(unittest.TestCase):
    def test_schedule_uses_the_shared_expiry_and_configured_lead(self) -> None:
        schedule = project_key_schedule(
            _token(2_000_000_000),
            _token(2_000_000_000),
            lead_days=7,
        )
        self.assertEqual(int(schedule.expires_at.timestamp()), 2_000_000_000)
        self.assertEqual(
            int((schedule.expires_at - schedule.rotate_at).total_seconds()),
            7 * 86_400,
        )

    def test_divergent_or_invalid_metadata_is_rejected(self) -> None:
        with self.assertRaises(KeyRotationMetadataError):
            project_key_schedule(
                _token(2_000_000_000),
                _token(2_000_000_001),
                lead_days=7,
            )
        with self.assertRaises(KeyRotationMetadataError):
            project_key_schedule("invalid", _token(2_000_000_000), lead_days=7)
        with self.assertRaises(KeyRotationMetadataError):
            project_key_schedule(
                _token(10**30),
                _token(10**30),
                lead_days=7,
            )


class AutomaticRotationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        cls.scheduler = (API_ROOT / "app" / "automatic_key_rotation.py").read_text(
            encoding="utf-8"
        )
        cls.schema = (API_ROOT / "app" / "database_schema.py").read_text(
            encoding="utf-8"
        )

    def test_each_project_is_enabled_by_default(self) -> None:
        self.assertIn(
            "automatic_key_rotation_enabled BOOLEAN NOT NULL DEFAULT true",
            self.schema,
        )
        self.assertIn("key_expires_at TIMESTAMPTZ", self.schema)
        self.assertIn("automatic_key_rotation_blocked_at TIMESTAMPTZ", self.schema)

    def test_scanner_is_single_leader_and_does_not_duplicate_active_jobs(self) -> None:
        scanner = self.scheduler[
            self.scheduler.index("async def scan_automatic_key_rotations") :
            self.scheduler.index("async def _automatic_key_rotation_loop")
        ]
        self.assertIn("pg_try_advisory_xact_lock", scanner)
        self.assertIn("FOR UPDATE OF p SKIP LOCKED", scanner)
        self.assertIn("NOT EXISTS", scanner)
        self.assertIn("status IN ('queued', 'running')", scanner)
        self.assertIn('"trigger": "automatic"', scanner)

    def test_failure_blocks_retries_until_explicit_reenable(self) -> None:
        self.assertIn("automatic_key_rotation_blocked_at = now()", self.scheduler)
        self.assertIn("automatic_key_rotation_last_error", self.scheduler)
        self.assertIn(
            '@app.put("/api/projects/{project_name}/automatic-key-rotation")',
            self.main,
        )
        self.assertIn("WHEN $2 THEN NULL", self.main)

    def test_manual_and_automatic_rotation_share_the_canonical_runner(self) -> None:
        self.assertIn(
            "async def _rotate_project_key_background(",
            self.main,
        )
        self.assertIn(
            'args={"trigger": "automatic"} if trigger == "automatic" else {}',
            self.main,
        )
        self.assertIn('action="project_keys_rotated"', self.main)


if __name__ == "__main__":
    unittest.main()
