"""Contrato de limites de recursos por projeto (REVISAO_ARQUITETURAL #6).

Containers nginx/auth/rest passam a subir sempre com mem_limit, cpus e
pids_limit resolvidos do perfil PROJECT_RESOURCE_PROFILE; projeto sem os
limites no .env precisa falhar no compose, nao iniciar sem controle.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
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
    """Cada servico recebe a SUA fatia do perfil, nao o total do projeto.

    Aplicar o mesmo PROJECT_MEM_LIMIT aos tres containers fazia um perfil
    anunciado como 1 GB reservar 3 GB.
    """

    @staticmethod
    def limit_lines(service: str) -> tuple[str, ...]:
        upper = service.upper()
        return (
            f"mem_limit: ${{PROJECT_{upper}_MEM_LIMIT:?defina "
            f"PROJECT_{upper}_MEM_LIMIT no .env do projeto}}",
            f"memswap_limit: ${{PROJECT_{upper}_MEM_LIMIT:?defina "
            f"PROJECT_{upper}_MEM_LIMIT no .env do projeto}}",
            f"cpus: ${{PROJECT_{upper}_CPUS:?defina "
            f"PROJECT_{upper}_CPUS no .env do projeto}}",
            f"pids_limit: ${{PROJECT_{upper}_PIDS_LIMIT:?defina "
            f"PROJECT_{upper}_PIDS_LIMIT no .env do projeto}}",
        )

    def test_no_service_uses_the_project_total_as_its_own_limit(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        for key in ("PROJECT_MEM_LIMIT", "PROJECT_CPUS", "PROJECT_PIDS_LIMIT"):
            with self.subTest(key=key):
                self.assertNotIn("${" + key, source)

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
            for line in self.limit_lines(service):
                with self.subTest(service=service, line=line):
                    self.assertIn(line, block)

    def test_limits_are_fail_closed_interpolations(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        for service in ("NGINX", "AUTH", "REST"):
            for suffix in ("MEM_LIMIT", "CPUS", "PIDS_LIMIT"):
                with self.subTest(service=service, suffix=suffix):
                    self.assertNotIn(f"PROJECT_{service}_{suffix}:-", source)


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
                "PROJECT_RES_SMALL_CPUS=0.75\n"
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
            self.assertIn("PROJECT_CPUS=0.75\n", content)
            self.assertIn("PROJECT_PIDS_LIMIT=128\n", content)
            self.assertEqual(project_env.stat().st_mode & 0o777, 0o600)

    def test_helper_rejects_unknown_profile(self) -> None:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text("PROJECT_RESOURCE_PROFILE=huge\n", encoding="utf-8")
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


class ProfileSplitFunctionalTest(unittest.TestCase):
    """A soma das fatias tem de fechar exatamente com o teto do perfil."""

    ROOT_ENV = (
        "PROJECT_RES_SMALL_MEMORY=256m\nPROJECT_RES_SMALL_CPUS=0.75\n"
        "PROJECT_RES_SMALL_PIDS=128\n"
        "PROJECT_RES_MEDIUM_MEMORY=1g\nPROJECT_RES_MEDIUM_CPUS=1.50\n"
        "PROJECT_RES_MEDIUM_PIDS=384\n"
        "PROJECT_RES_LARGE_MEMORY=4g\nPROJECT_RES_LARGE_CPUS=3.00\n"
        "PROJECT_RES_LARGE_PIDS=768\n"
    )
    EXPECTED = {
        "small": {
            "NGINX": ("32m", "0.07"),
            "AUTH": ("96m", "0.45"),
            "REST": ("128m", "0.23"),
        },
        "medium": {
            "NGINX": ("128m", "0.20"),
            "AUTH": ("384m", "0.70"),
            "REST": ("512m", "0.60"),
        },
        "large": {
            "NGINX": ("512m", "0.45"),
            "AUTH": ("1536m", "1.20"),
            "REST": ("2048m", "1.35"),
        },
    }

    def _apply(self, profile: str) -> dict[str, str]:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / "root.env"
            root_env.write_text(self.ROOT_ENV, encoding="utf-8")
            project_env = pathlib.Path(tmp) / "project.env"
            project_env.write_text("PROJECT_ID=demo\n", encoding="utf-8")
            subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; apply_project_resource_limits '
                    f'"{root_env}" "{project_env}" "{profile}"',
                ],
                check=True,
            )
            return dict(
                line.split("=", 1)
                for line in project_env.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )

    def test_shares_match_the_documented_table(self) -> None:
        for profile, services in self.EXPECTED.items():
            values = self._apply(profile)
            for service, (memory, cpus) in services.items():
                with self.subTest(profile=profile, service=service):
                    self.assertEqual(memory, values[f"PROJECT_{service}_MEM_LIMIT"])
                    self.assertEqual(cpus, values[f"PROJECT_{service}_CPUS"])

    def test_pids_are_floors_not_a_split_of_the_total(self) -> None:
        values = self._apply("small")
        floors = {"NGINX": 128, "AUTH": 256, "REST": 512}
        for service, floor in floors.items():
            with self.subTest(service=service):
                self.assertGreaterEqual(
                    int(values[f"PROJECT_{service}_PIDS_LIMIT"]), floor
                )
        total = sum(int(values[f"PROJECT_{s}_PIDS_LIMIT"]) for s in floors)
        self.assertGreater(total, int(values["PROJECT_PIDS_LIMIT"]))

    def test_shares_sum_exactly_to_the_project_total(self) -> None:
        for profile in ("small", "medium", "large"):
            values = self._apply(profile)
            with self.subTest(profile=profile):
                total_memory = values["PROJECT_MEM_LIMIT"]
                expected_mib = int(total_memory[:-1]) * (
                    1024 if total_memory[-1].lower() == "g" else 1
                )
                self.assertEqual(
                    expected_mib,
                    sum(
                        int(values[f"PROJECT_{service}_MEM_LIMIT"][:-1])
                        for service in ("NGINX", "AUTH", "REST")
                    ),
                )
                self.assertEqual(
                    round(float(values["PROJECT_CPUS"]) * 100),
                    sum(
                        round(float(values[f"PROJECT_{service}_CPUS"]) * 100)
                        for service in ("NGINX", "AUTH", "REST")
                    ),
                )


class GhcHeapCapContract(unittest.TestCase):
    """A fatia do rest so e teto de verdade com o heap do GHC limitado.

    O RTS do GHC cresce ate a memoria disponivel e o PostgREST nao enxerga o
    limite do container (PostgREST#1263). Sem `-M`, `mem_limit` vira um
    convite: o processo ocupa o que tiver e morre por OOM do kernel, sem log.
    """

    def test_template_caps_the_haskell_heap_below_the_container_limit(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("GHCRTS: -c -M${PROJECT_REST_GHC_MAX_HEAP:?", source)

    def test_cap_is_derived_and_below_the_rest_share(self) -> None:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / "root.env"
            root_env.write_text(
                "PROJECT_RES_MEDIUM_MEMORY=1g\nPROJECT_RES_MEDIUM_CPUS=1.50\n"
                "PROJECT_RES_MEDIUM_PIDS=384\n",
                encoding="utf-8",
            )
            project_env = pathlib.Path(tmp) / "p.env"
            project_env.write_text("X=1\n", encoding="utf-8")
            subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; apply_project_resource_limits '
                    f'"{root_env}" "{project_env}" medium',
                ],
                check=True,
            )
            values = dict(
                line.split("=", 1)
                for line in project_env.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
            heap = int(values["PROJECT_REST_GHC_MAX_HEAP"].rstrip("m"))
            share = int(values["PROJECT_REST_MEM_LIMIT"].rstrip("m"))
            self.assertLess(heap, share, "heap tem de caber abaixo do mem_limit")
            self.assertGreater(heap, share // 2, "teto baixo demais viraria crash")


class MemoryFloorContract(unittest.TestCase):
    """Perfil pequeno demais falha alto, em vez de furar o teto em silencio.

    GoTrue tem pico de baseline ~56 MiB: uma fatia menor que isso e um OOM
    latente, que so aparece sob carga real.
    """

    def test_profile_below_the_auth_floor_is_rejected(self) -> None:
        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / "root.env"
            root_env.write_text(
                "PROJECT_RES_SMALL_MEMORY=64m\nPROJECT_RES_SMALL_CPUS=0.75\n"
                "PROJECT_RES_SMALL_PIDS=128\n",
                encoding="utf-8",
            )
            project_env = pathlib.Path(tmp) / "p.env"
            project_env.write_text("X=1\n", encoding="utf-8")
            result = subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; apply_project_resource_limits '
                    f'"{root_env}" "{project_env}" small',
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("minimo seguro", result.stderr)
            # Nada pode ter sido gravado.
            self.assertEqual("X=1\n", project_env.read_text(encoding="utf-8"))

    def test_floors_match_between_bash_and_api(self) -> None:
        import re

        helper = HELPER.read_text(encoding="utf-8")
        settings = (ROOT / "servidor/api-internal/app/project_settings.py").read_text(
            encoding="utf-8"
        )
        bash_floors = re.search(r"(?m)^RESOURCE_MEM_FLOORS_MIB=\(([^)]*)\)", helper)
        api_floors = re.search(r"RESOURCE_MEM_FLOORS_MIB = \(([^)]*)\)", settings)
        self.assertIsNotNone(bash_floors)
        self.assertIsNotNone(api_floors)
        self.assertEqual(
            tuple(int(v) for v in bash_floors.group(1).split()),
            tuple(int(v) for v in api_floors.group(1).split(",") if v.strip()),
        )


class MigratorContractTest(unittest.TestCase):
    def test_migrator_exists_and_defaults_to_dry_run(self) -> None:
        """Sem --apply o migrador nao pode tocar em nenhum .env."""
        source = MIGRATOR.read_text(encoding="utf-8")
        self.assertIn("--apply", source)
        self.assertIn('action="store_true"', source)

        bash_env = tempfile.mkdtemp()
        root_env = pathlib.Path(bash_env) / ".env"
        root_env.write_text(
            "PROJECT_RESOURCE_PROFILE=medium\n"
            "PROJECT_RES_MEDIUM_MEMORY=1g\n"
            "PROJECT_RES_MEDIUM_CPUS=1.50\n"
            "PROJECT_RES_MEDIUM_PIDS=384\n",
            encoding="utf-8",
        )
        projects = pathlib.Path(bash_env) / "projects" / "demo"
        projects.mkdir(parents=True)
        project_env = projects / ".env"
        project_env.write_text("PROJECT_ID=demo\n", encoding="utf-8")
        before = project_env.read_text(encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(MIGRATOR),
                "--server-env",
                str(root_env),
                "--projects-dir",
                str(projects.parent),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("[pendente]", result.stdout)
        self.assertEqual(before, project_env.read_text(encoding="utf-8"))

    def test_migrator_tracks_every_key_the_helper_writes(self) -> None:
        """Chave fora do MANAGED_RE some do diff: reporta "ja aplicado" sem estar.

        Foi o que aconteceu ao introduzir PROJECT_REST_GHC_MAX_HEAP.
        """
        import re

        bash = shutil.which("bash") or "bash"
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / "root.env"
            root_env.write_text(
                "PROJECT_RES_MEDIUM_MEMORY=1g\nPROJECT_RES_MEDIUM_CPUS=1.50\n"
                "PROJECT_RES_MEDIUM_PIDS=384\n",
                encoding="utf-8",
            )
            project_env = pathlib.Path(tmp) / "p.env"
            project_env.write_text("X=1\n", encoding="utf-8")
            subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; apply_project_resource_limits '
                    f'"{root_env}" "{project_env}" medium',
                ],
                check=True,
            )
            written = {
                line.split("=", 1)[0]
                for line in project_env.read_text(encoding="utf-8").splitlines()
                if line.startswith("PROJECT_")
            }

        pattern = re.search(
            r"MANAGED_RE = re\.compile\((.*?)\)\n", MIGRATOR.read_text(), re.S
        )
        self.assertIsNotNone(pattern)
        managed = re.compile("".join(re.findall(r'r"([^"]*)"', pattern.group(1))))
        for key in sorted(written):
            with self.subTest(key=key):
                self.assertIsNotNone(
                    managed.match(f"{key}=x"),
                    f"{key} nao esta no MANAGED_RE do migrador",
                )

    def test_migrator_delegates_to_the_canonical_helper(self) -> None:
        """Uma unica implementacao do rateio: bash, API e migrador."""
        source = MIGRATOR.read_text(encoding="utf-8")
        self.assertIn("apply_project_resource_limits", source)
        self.assertIn("resource_profiles.sh", source)
        # Nao pode reimplementar os pesos.
        for weights in ("1, 3, 4", "(1, 2, 3)", "(2, 5, 5)"):
            with self.subTest(weights=weights):
                self.assertNotIn(weights, source)

    def test_env_example_documents_profiles(self) -> None:
        import re

        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        self.assertIn("PROJECT_RESOURCE_PROFILE=medium", example)
        for suffix in ("SMALL", "MEDIUM", "LARGE"):
            for key in ("MEMORY", "CPUS", "PIDS"):
                with self.subTest(profile=suffix, key=key):
                    self.assertIsNotNone(
                        re.search(rf"^PROJECT_RES_{suffix}_{key}=\S+$", example, re.M)
                    )


if __name__ == "__main__":
    unittest.main()
