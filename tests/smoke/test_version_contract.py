"""Trava a versao unica da plataforma e os artefatos de release formal.

`VERSION` na raiz e canonico. `tools/check-version-parity.py` propaga o numero
para o runtime da API, o OpenAPI publicado, o cliente Dart, o app Flutter, o
script de geracao e a matriz de compatibilidade. Este contrato garante que a
ferramenta existe, que ela reprova divergencia e que os documentos de release
citados pelo runbook estao presentes.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check-version-parity.py"
VERSION_FILE = ROOT / "VERSION"
MATRIX = ROOT / "COMPATIBILITY_MATRIX.md"
UPGRADES_EN = ROOT / "docs" / "operations" / "upgrades.md"
UPGRADES_PT = ROOT / "docs" / "pt-br" / "operations" / "upgrades.md"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")

DERIVED_FILES = (
    "servidor/api-internal/app/version.py",
    "studio/projects_api_client/pubspec.yaml",
    "studio/projects_api_client/README.md",
    "tools/generate_dart_client.sh",
    "studio/seletor_de_projetos/pubspec.yaml",
    "COMPATIBILITY_MATRIX.md",
    "docs/api/openapi.json",
)


def _run_tool(cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / "tools" / "check-version-parity.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )


class VersionParityToolTest(unittest.TestCase):
    def test_tool_exists(self) -> None:
        self.assertTrue(TOOL.is_file(), "tools/check-version-parity.py ausente")

    def test_version_file_is_single_semver_line(self) -> None:
        raw = VERSION_FILE.read_text(encoding="utf-8")
        self.assertEqual(raw, raw.strip() + "\n", "VERSION deve ter uma linha + newline")
        self.assertRegex(raw.strip(), SEMVER_RE)

    def test_repository_is_in_parity(self) -> None:
        completed = _run_tool(ROOT)
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )

    def test_every_derived_file_is_covered(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        for relative in DERIVED_FILES:
            with self.subTest(file=relative):
                self.assertIn(relative, source)

    def test_tool_rejects_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp) / "repo"
            for relative in ("VERSION", *DERIVED_FILES, "tools/check-version-parity.py"):
                target = clone / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            version_py = clone / "servidor/api-internal/app/version.py"
            version_py.write_text(
                'API_VERSION = "9.9.9-divergente"\n', encoding="utf-8", newline="\n"
            )
            completed = _run_tool(clone)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("9.9.9-divergente", completed.stdout)

    def test_tool_rejects_invalid_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clone = pathlib.Path(tmp) / "repo"
            (clone / "tools").mkdir(parents=True)
            shutil.copy2(TOOL, clone / "tools" / "check-version-parity.py")
            (clone / "VERSION").write_text("nao-e-semver\n", encoding="utf-8", newline="\n")
            completed = _run_tool(clone)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("semver", completed.stdout)


class ReleaseArtifactsTest(unittest.TestCase):
    def test_release_documents_exist(self) -> None:
        for path in (MATRIX, UPGRADES_EN, UPGRADES_PT):
            with self.subTest(doc=path.name):
                self.assertTrue(path.is_file(), f"{path} ausente")

    def test_matrix_declares_the_canonical_version(self) -> None:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
        self.assertRegex(
            MATRIX.read_text(encoding="utf-8"),
            re.compile(rf"(?m)^\| \*\*Plataforma\*\* \| `{re.escape(version)}` \|"),
        )

    def test_matrix_lists_every_patched_upstream_file(self) -> None:
        patched = [
            "studio/studio-slug/studio-project-context.patch",
            "servidor/volumes/realtime/replication_connection.ex",
            "servidor/volumes/realtime/metrics_controller.ex",
            "servidor/volumes/realtime/router.ex",
            "servidor/volumes/analytics/dialect_translation.ex",
            "servidor/volumes/analytics/sql.ex",
        ]
        text = MATRIX.read_text(encoding="utf-8")
        for relative in patched:
            with self.subTest(file=relative):
                self.assertTrue((ROOT / relative).is_file(), f"{relative} sumiu do repo")
                self.assertIn(relative, text, f"{relative} fora da matriz")

    def test_upgrade_runbook_covers_the_three_layers(self) -> None:
        for path in (UPGRADES_EN, UPGRADES_PT):
            text = path.read_text(encoding="utf-8")
            with self.subTest(doc=path.name):
                self.assertIn("recreate-services", text)
                self.assertIn("check-version-parity.py", text)
                self.assertIn("COMPATIBILITY_MATRIX.md", text)


if __name__ == "__main__":
    unittest.main()
