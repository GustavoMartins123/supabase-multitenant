"""Boot de projetos com isolamento de falha (LOG-20).

Um projeto com compose quebrado nao pode impedir os demais nem o Studio:
cada falha e registrada, o boot segue e o exit final e nao-zero com resumo.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


if sys.platform == "win32":
    raise unittest.SkipTest("requires POSIX bash (Linux-only)")


ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "servidor" / "generateProject" / "lib" / "project_boot.sh"
START = ROOT / "start.sh"

FAKE_DOCKER = """#!/usr/bin/env bash
echo "$@" >> "$CALL_LOG"
for arg in "$@"; do
    if [[ "$arg" == "-p" ]]; then
        want_name=1
        continue
    fi
    if [[ "${want_name:-0}" == "1" ]]; then
        want_name=0
        if [[ "$arg" == "broken" ]]; then
            echo "fake docker: compose invalido" >&2
            exit 1
        fi
    fi
done
exit 0
"""


def run_boot(projects: dict[str, bool]) -> subprocess.CompletedProcess:
    bash = shutil.which("bash") or "bash"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        projects_root = tmp_path / "projects"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(FAKE_DOCKER, encoding="utf-8")
        docker.chmod(0o755)
        call_log = tmp_path / "calls.log"
        call_log.write_text("", encoding="utf-8")
        for name, with_compose in projects.items():
            project_dir = projects_root / name
            project_dir.mkdir(parents=True)
            (project_dir / ".env").write_text("X=1\n", encoding="utf-8")
            if with_compose:
                (project_dir / "docker-compose.yml").write_text(
                    "services: {}\n", encoding="utf-8"
                )
        server_env = tmp_path / ".env"
        server_env.write_text("X=1\n", encoding="utf-8")
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "CALL_LOG": str(call_log),
        }
        result = subprocess.run(
            [
                bash,
                "-c",
                f'source "{LIB}"; start_all_projects "{projects_root}" "{server_env}"',
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        result.calls = call_log.read_text(encoding="utf-8")
        return result


class ProjectBootIsolationTest(unittest.TestCase):
    def test_broken_project_does_not_block_the_rest(self) -> None:
        result = run_boot({"aaa": True, "broken": True, "zzz": True})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("-p aaa", result.calls)
        self.assertIn("-p zzz", result.calls)
        self.assertIn("broken", result.stderr)

    def test_healthy_boot_is_quiet_and_zero(self) -> None:
        result = run_boot({"aaa": True, "zzz": True})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-p aaa", result.calls)
        self.assertIn("-p zzz", result.calls)

    def test_directory_without_compose_is_skipped(self) -> None:
        result = run_boot({"aaa": True, "empty": False})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("-p empty", result.calls)

    def test_start_uses_the_shared_boot_helper(self) -> None:
        start = START.read_text(encoding="utf-8")
        self.assertIn("generateProject/lib/project_boot.sh", start)
        self.assertIn("start_all_projects", start)
        self.assertIn("BOOT_PROJECT_FAILURES", start)


if __name__ == "__main__":
    unittest.main()
