"""E2E opt-in da plataforma em instalacao descartavel dedicada.

Cobre a matriz prioritaria da revisao arquitetural que os contratos estaticos
nao conseguem: ciclo de vida real (create com perfil de recursos), isolamento
fail-closed do gateway sem credencial e comportamento com o key-authorizer
fora do ar. Requer acesso ao host da instalacao (docker) e as variaveis:

    RUN_PLATFORM_E2E=1
    SMOKE_API_URL=https://<ip>:9091        (gateway do Studio)
    SMOKE_PUBLIC_BASE_URL=https://<ip>     (data plane publico)
    SMOKE_STUDIO_GATEWAY_HMAC_SECRET=...
    SMOKE_PROJECTS_API_HMAC_SECRET=...     (se exigido pelo sign_internal)
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import time
import unittest

from tests.smoke.common import env_flag, request, wait_for_job

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "servidor" / "projects"


def _project_env(project: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (
        (PROJECTS_DIR / project / ".env").read_text(encoding="utf-8").splitlines()
    ):
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


@unittest.skipUnless(
    env_flag("RUN_PLATFORM_E2E"),
    "set RUN_PLATFORM_E2E=1 on a disposable dedicated installation",
)
class PlatformLifecycleE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api_url = os.environ["SMOKE_API_URL"].rstrip("/")
        cls.public_base = os.environ["SMOKE_PUBLIC_BASE_URL"].rstrip("/")
        cls.suffix = str(int(time.time()))
        cls.projects: list[str] = []

    @classmethod
    def tearDownClass(cls) -> None:
        for project in reversed(cls.projects):
            try:
                status, payload = request(
                    "DELETE",
                    f"{cls.api_url}/api/projects/{project}",
                    payload={"confirm": project},
                )
                assert status in {200, 202}, (status, payload)
            except Exception:
                pass

    def _create(self, name: str, profile: str) -> None:
        status, payload = request(
            "POST",
            f"{self.api_url}/api/projects",
            payload={"name": name, "resource_profile": profile},
        )
        self.assertIn(status, {200, 202}, payload)
        wait_for_job(self.api_url, payload["job_id"])
        self.projects.append(name)

    def test_01_create_applies_resource_profile_to_project_env(self) -> None:
        expected = {
            "small": ("256m", "1.85", "128"),
            "medium": ("1g", "2.00", "384"),
        }
        for index, (profile, (mem, cpus, pids)) in enumerate(expected.items()):
            with self.subTest(profile=profile):
                name = f"e2e{index}{self.suffix}"
                self._create(name, profile)
                env = _project_env(name)
                self.assertEqual(env.get("PROJECT_MEM_LIMIT"), mem)
                self.assertEqual(env.get("PROJECT_CPUS"), cpus)
                self.assertEqual(env.get("PROJECT_PIDS_LIMIT"), pids)

    def test_02_gateway_fails_closed_without_any_credential(self) -> None:
        target = self.projects[0]
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"{self.public_base}/{target}/rest/v1/",
            method="GET",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("rota publica aceitou requisicao sem chave")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 401)

    def test_03_key_authorizer_down_is_fail_closed_and_recovers(self) -> None:
        target = self.projects[0]

        def rest_status() -> int | None:
            import urllib.error
            import urllib.request

            try:
                req = urllib.request.Request(
                    f"{self.public_base}/{target}/rest/v1/", method="GET"
                )
                urllib.request.urlopen(req, timeout=10)
                return 200
            except urllib.error.HTTPError as exc:
                return exc.code
            except Exception:
                return None

        subprocess.run(
            ["docker", "stop", "supabase-key-authorizer"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        try:
            time.sleep(2)
            down = rest_status()
            self.assertIsNotNone(down)
            self.assertGreaterEqual(down, 500)
        finally:
            subprocess.run(
                ["docker", "start", "supabase-key-authorizer"],
                check=True,
                capture_output=True,
                timeout=60,
            )
        deadline = time.time() + 90
        while time.time() < deadline:
            if rest_status() == 401:
                return
            time.sleep(3)
        self.fail("key-authorizer nao voltou a servir dentro do prazo")


if __name__ == "__main__":
    unittest.main()
