import datetime as dt
import sys
import types
import unittest
import uuid
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2] / "servidor" / "api-internal"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")
    asyncpg_stub.Pool = object
    asyncpg_stub.Connection = object
    asyncpg_stub.Record = dict
    sys.modules["asyncpg"] = asyncpg_stub

from app.jobs import IDEMPOTENT_ACTIONS, is_action_idempotent, serialize_job


class JobsContractTest(unittest.TestCase):
    def test_only_safe_project_actions_are_retryable(self):
        self.assertEqual(
            IDEMPOTENT_ACTIONS,
            {"start", "stop", "restart", "recreate_services"},
        )
        for action in IDEMPOTENT_ACTIONS:
            self.assertTrue(is_action_idempotent(action))
        for action in {"create", "duplicate", "delete", "rename", "rotate_key"}:
            self.assertFalse(is_action_idempotent(action))

    def test_job_serialization_exposes_durable_progress_and_retry_metadata(self):
        now = dt.datetime.now(dt.timezone.utc)
        job_id = uuid.uuid4()
        project_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        row = {
            "job_id": job_id,
            "project": "example",
            "project_uuid": project_id,
            "created_by": actor_id,
            "action": "start",
            "status": "failed",
            "message": "stopped",
            "progress": 50,
            "current_step": "container_2",
            "total_steps": 4,
            "started_at": now,
            "finished_at": now,
            "error_code": "container_failed",
            "is_idempotent": True,
            "retryable": True,
            "retry_of": None,
            "attempt": 1,
            "created_at": now,
            "updated_at": now,
            "stdout_tail": "stdout",
            "stderr_tail": "stderr",
        }

        result = serialize_job(row, include_output=True)

        self.assertEqual(result["job_id"], str(job_id))
        self.assertEqual(result["project_uuid"], str(project_id))
        self.assertEqual(result["created_by"], str(actor_id))
        self.assertEqual(result["progress"], 50)
        self.assertEqual(result["current_step"], "container_2")
        self.assertEqual(result["total_steps"], 4)
        self.assertEqual(result["stdout_tail"], "stdout")
        self.assertEqual(result["stderr_tail"], "stderr")
        self.assertTrue(result["retryable"])


if __name__ == "__main__":
    unittest.main()
