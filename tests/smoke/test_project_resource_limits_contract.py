"""Contrato de limites de recursos por projeto (REVISAO_ARQUITETURAL #6).

Containers nginx/auth/rest passam a subir sempre com mem_limit, cpus e
pids_limit resolvidos do perfil PROJECT_RESOURCE_PROFILE; projeto sem os
limites no .env precisa falhar no compose, nao iniciar sem controle.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "servidor" / "generateProject" / "dockercomposetemplate"
HELPER = ROOT / "servidor" / "generateProject" / "lib" / "resource_profiles.sh"
MIGRATOR = ROOT / "tools" / "migrate_project_resource_limits.py"

HOOKED_SCRIPTS = (
    ROOT / "servidor" / "generateProject" / "lib" / "generate_project_impl.sh",
    ROOT / "servidor" / "generateProject" / "lib" / "duplicate_project_impl.sh",
    ROOT / "servidor" / "generateProject" / "lib" / "rename_project_impl.sh",
    ROOT / "servidor" / "generateProject" / "rotate_key.sh",
)


class TemplateResourceLimitsTest(unittest.TestCase):
    LIMIT_LINES = (
        'mem_limit: ${PROJECT_MEM_LIMIT:?defina PROJECT_MEM_LIMIT no .env do projeto}',
        'memswap_limit: ${PROJECT_MEM_LIMIT:?defina PROJECT_MEM_LIMIT no .env do projeto}',
        'cpus: ${PROJECT_CPUS:?defina PROJECT_CPUS no .env do projeto}',
        'pids_limit: ${PROJECT_PIDS_LIMIT:?defina PROJECT_PIDS_LIMIT no .env do projeto}',
    )

    def test_every_project_service_declares_the_limits(self) -> None:
        import re

        source = TEMPLATE.read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^(?=  [\w-]+:\n)", source)
        for service, container in (
            ("nginx", "supabase-nginx-{{project_id}}"),
            ("auth", "supabase-auth-{{project_id}}"),
            ("rest", "supabase-rest-{{project_id}}"),
        ):
            block = next(
                (b for b in blocks if f"container_name: {container}" in b),
                None,
            )
            self.assertIsNotNone(block, f"servico {service} ausente no template")
            for line in self.LIMIT_LINES:
                with self.subTest(service=service, line=line):
                    self.assertIn(line, block)

    def test_limits_are_fail_closed_interpolations(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("PROJECT_MEM_LIMIT:-", source)
        self.assertNotIn("PROJECT_CPUS:-", source)
        self.assertNotIn("PROJECT_PIDS_LIMIT:-", source)


class LifecycleHookTest(unittest.TestCase):
    def test_lifecycle_scripts_source_and_apply_the_profile(self) -> None:
        for script in HOOKED_SCRIPTS:
            source = script.read_text(encoding="utf-8")
            with self.subTest(script=str(script.relative_to(ROOT))):
                self.assertIn("lib/resource_profiles.sh", source)
                self.assertIn(
                    'apply_project_resource_limits "$PROJECT_ROOT/.env"',
                    source,
                )


class ProfileHelperFunctionalTest(unittest.TestCase):
    def test_helper_is_idempotent_and_preserves_content(self) -> None:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(
                "PROJECT_RESOURCE_PROFILE=small\n"
                "PROJECT_RES_SMALL_MEMORY=256m\n"
                "PROJECT_RES_SMALL_CPUS=0.50\n"
                "PROJECT_RES_SMALL_PIDS=128\n",
                encoding="utf-8",
            )
            project_env = pathlib.Path(tmp) / "project.env"
            project_env.write_text(
                "PROJECT_ID=demo\nJWT_SECRET_PROJETO=segredo\n",
                encoding="utf-8",
            )
            project_env.chmod(0o600)
            script = (
                f'source "{HELPER}"; '
                f'apply_project_resource_limits "{root_env}" "{project_env}"; '
                f'apply_project_resource_limits "{root_env}" "{project_env}"'
            )
            subprocess.run([bash, "-c", script], check=True)
            content = project_env.read_text(encoding="utf-8")
            self.assertIn("PROJECT_ID=demo\n", content)
            self.assertIn("JWT_SECRET_PROJETO=segredo\n", content)
            self.assertEqual(content.count("PROJECT_MEM_LIMIT="), 1)
            self.assertIn("PROJECT_MEM_LIMIT=256m\n", content)
            self.assertIn("PROJECT_CPUS=0.50\n", content)
            self.assertIn("PROJECT_PIDS_LIMIT=128\n", content)
            self.assertEqual(project_env.stat().st_mode & 0o777, 0o600)

    def test_helper_rejects_unknown_profile(self) -> None:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(
                "PROJECT_RESOURCE_PROFILE=huge\n", encoding="utf-8"
            )
            project_env = pathlib.Path(tmp) / "project.env"
            project_env.write_text("A=1\n", encoding="utf-8")
            result = subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; '
                    f'apply_project_resource_limits "{root_env}" "{project_env}"',
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PROJECT_RESOURCE_PROFILE invalido", result.stderr)


class MigratorContractTest(unittest.TestCase):
    def test_migrator_exists_and_defaults_to_dry_run(self) -> None:
        source = MIGRATOR.read_text(encoding="utf-8")
        self.assertIn("--apply", source)
        self.assertIn("--dry-run", source)
        self.assertIn("action=\"store_true\"", source)

    def test_env_example_documents_profiles(self) -> None:
        import re

        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        self.assertIn("PROJECT_RESOURCE_PROFILE=medium", example)
        for suffix in ("SMALL", "MEDIUM", "LARGE"):
            for key in ("MEMORY", "CPUS", "PIDS"):
                with self.subTest(profile=suffix, key=key):
                    self.assertIsNotNone(
                        re.search(
                            rf"^PROJECT_RES_{suffix}_{key}=\S+$", example, re.M
                        )
                    )


if __name__ == "__main__":
    unittest.main()
