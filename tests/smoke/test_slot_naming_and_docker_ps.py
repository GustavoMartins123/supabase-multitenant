"""Nomes de replication slot sem colisao e docker ps tolerante (LOG-21/22).

Restore usa a mesma lib de nomes dos demais lifecycles (hash quando o
nome nao cabe em 63 chars) e varre candidatos novos+legados no drop. Uma
linha nao-JSON no `docker ps` e ignorada em vez de derrubar a listagem.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
sys.path.insert(0, str(AGENT_ROOT))

from hostagent.commands import docker_ps_all  # noqa: E402

RESTORE = (
    ROOT / "servidor" / "generateProject" / "lib" / "restore_project_impl.sh"
)
SLOTS_LIB = ROOT / "servidor" / "generateProject" / "lib" / "realtime_slots.sh"

LONG_A = "x" * 30 + "a" * 12
LONG_B = "x" * 30 + "b" * 12

if sys.platform != "win32":
    from hostagent.commands import docker_ps_all  # noqa: E402


def bash_eval_restore_slots(project: str) -> tuple[str, str]:
    bash = shutil.which("bash") or "bash"
    source = RESTORE.read_text(encoding="utf-8")
    slot_line = next(
        line
        for line in source.splitlines()
        if line.startswith("SLOT=")
    )
    msg_line = next(
        line
        for line in source.splitlines()
        if line.startswith("MSG_SLOT=")
    )
    script = (
        f'source "{SLOTS_LIB}"; PROJECT="{project}"; {slot_line}; '
        f'{msg_line}; printf "%s\\n%s\\n" "$SLOT" "$MSG_SLOT"'
    )
    result = subprocess.run(
        [bash, "-c", script], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "slot eval falhou")
    slot, msg_slot = result.stdout.split()
    return slot, msg_slot


@unittest.skipIf(sys.platform == "win32", "requires POSIX bash (Linux-only)")
class RestoreSlotNamingTest(unittest.TestCase):
    def test_restore_uses_the_shared_naming_lib(self) -> None:
        source = RESTORE.read_text(encoding="utf-8")
        self.assertIn("realtime_slots.sh", source)
        self.assertIn("realtime_primary_slot", source)
        self.assertNotIn("${SLOT:0:63}", source)
        self.assertNotIn("${MSG_SLOT:0:63}", source)

    def test_long_colliding_projects_get_distinct_valid_slots(self) -> None:
        slot_a, msg_a = bash_eval_restore_slots(LONG_A)
        slot_b, msg_b = bash_eval_restore_slots(LONG_B)
        for name in (slot_a, slot_b, msg_a, msg_b):
            with self.subTest(name=name):
                self.assertLessEqual(len(name), 63)
                self.assertRegex(name, r"^[a-z][a-z0-9_]*$")
        self.assertNotEqual(slot_a, slot_b)
        self.assertNotEqual(msg_a, msg_b)

    def test_short_projects_keep_the_legacy_slot_name(self) -> None:
        slot, msg_slot = bash_eval_restore_slots("abc")
        self.assertEqual(slot, "supabase_realtime_replication_slot_abc")
        self.assertEqual(
            msg_slot, "supabase_realtime_messages_replication_slot_abc"
        )

    def test_drop_sweeps_legacy_and_hashed_candidates(self) -> None:
        source = RESTORE.read_text(encoding="utf-8")
        self.assertIn("realtime_slot_candidates_unique", source)
        self.assertIn('drop_slot_if_exists "$candidate_slot"', source)


class TolerantDockerPsTest(unittest.IsolatedAsyncioTestCase):
    async def test_garbage_line_is_skipped(self) -> None:
        good_one = {"Names": "supabase-nginx-demo", "State": "running"}
        good_two = {"Names": "supabase-auth-demo", "State": "running"}
        stdout = "\n".join(
            [
                json.dumps(good_one),
                "WARNING: daemon Schultz!  (linha nao-JSON)",
                "",
                json.dumps(good_two),
            ]
        )

        async def _ps(*args: object, **kwargs: object):
            return 0, stdout, ""

        with mock.patch("hostagent.commands._run_short", _ps):
            containers = await docker_ps_all()
        self.assertEqual(
            [entry["Names"] for entry in containers],
            ["supabase-nginx-demo", "supabase-auth-demo"],
        )

    async def test_all_garbage_returns_empty_instead_of_raising(self) -> None:
        async def _ps(*args: object, **kwargs: object):
            return 0, "not json at all\n", ""

        with mock.patch("hostagent.commands._run_short", _ps):
            self.assertEqual(await docker_ps_all(), [])


if __name__ == "__main__":
    unittest.main()
