from __future__ import annotations

import os
import time
import unittest

from tests.smoke.common import env_flag, request, wait_for_job


@unittest.skipUnless(
    env_flag("RUN_TENANT_LIFECYCLE_SMOKE"),
    "set RUN_TENANT_LIFECYCLE_SMOKE=1",
)
class TenantLifecycleSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api_url = os.environ["SMOKE_API_URL"].rstrip("/")
        cls.project = os.getenv("SMOKE_PROJECT_NAME") or f"smoke_{int(time.time())}"
        cls.headers = {
            "X-Shared-Token": os.environ["SMOKE_SHARED_TOKEN"],
            "X-User-Token": os.environ["SMOKE_USER_TOKEN"],
        }
        cls.delete_password = os.environ["SMOKE_DELETE_PASSWORD"]
        cls.created = False

    @classmethod
    def tearDownClass(cls) -> None:
        if not cls.created:
            return
        cleanup_headers = {
            **cls.headers,
            "X-Delete-Password": cls.delete_password,
        }
        status, body = request(
            "DELETE",
            f"{cls.api_url}/api/projects/{cls.project}",
            headers=cleanup_headers,
        )
        if status == 202 and isinstance(body, dict) and body.get("job_id"):
            wait_for_job(cls.api_url, body["job_id"], cls.headers)

    def run_action(self, action: str) -> dict:
        status, body = request(
            "POST",
            f"{self.api_url}/api/projects/{self.project}/{action}",
            headers=self.headers,
        )
        self.assertEqual(status, 202, body)
        self.assertIsInstance(body, dict)
        return wait_for_job(self.api_url, body["job_id"], self.headers)

    def test_full_lifecycle(self) -> None:
        status, body = request(
            "POST",
            f"{self.api_url}/api/projects",
            headers=self.headers,
            payload={"name": self.project},
        )
        self.assertEqual(status, 202, body)
        self.created = True
        created = wait_for_job(self.api_url, body["job_id"], self.headers)
        self.assertEqual(created["progress"], 100)

        status, project_status = request(
            "GET",
            f"{self.api_url}/api/projects/{self.project}/status",
            headers=self.headers,
        )
        self.assertEqual(status, 200, project_status)
        self.assertEqual(project_status.get("status"), "running")

        stopped = self.run_action("stop")
        self.assertEqual(stopped["progress"], 100)
        started = self.run_action("start")
        self.assertEqual(started["progress"], 100)

        delete_headers = {
            **self.headers,
            "X-Delete-Password": self.delete_password,
        }
        status, deleted = request(
            "DELETE",
            f"{self.api_url}/api/projects/{self.project}",
            headers=delete_headers,
        )
        self.assertEqual(status, 202, deleted)
        wait_for_job(self.api_url, deleted["job_id"], self.headers)
        self.created = False


if __name__ == "__main__":
    unittest.main()
