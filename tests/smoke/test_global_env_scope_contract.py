"""Contrato de escopo do `.env` global.

O `.env` de `servidor/` carrega os segredos do control plane: master key de
envelope encryption, chave que decifra o `service_role`, HMAC do host-agent e
senha global do PostgreSQL. Nenhum container que atende tenant pode recebe-lo
inteiro. A interpolacao `${VAR}` dos blocos `environment:` vem do
`--env-file` da linha de comando, entao declarar o `env_file:` no servico so
serve para injetar tudo no processo.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Segredos globais cujo alcance define o blast radius da instalacao.
CONTROL_PLANE_SECRETS = (
    "PROJECT_SECRETS_MASTER_KEY",
    "PROJECT_SECRETS_PREVIOUS_MASTER_KEYS",
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
    "HOST_AGENT_HMAC_SECRET",
    "PROJECTS_API_HMAC_SECRET",
    "STUDIO_GATEWAY_HMAC_SECRET",
    "INTERNAL_HMAC_SECRET",
    "KEY_AUTHORIZER_DB_PASSWORD",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def service_block(compose: str, service: str) -> str:
    lines = compose.splitlines()
    marker = f"  {service}:"
    try:
        start = lines.index(marker) + 1
    except ValueError as exc:
        raise AssertionError(f"servico ausente: {service}") from exc
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        body.append(line)
    return "\n".join(body)


def env_file_entries(block: str) -> list[str]:
    match = re.search(r"^    env_file:\n((?:      - .+\n)+)", block + "\n", re.M)
    if match is None:
        return []
    return [line.strip()[2:] for line in match.group(1).splitlines()]


class TenantContainersDoNotReceiveTheGlobalEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = read("servidor/generateProject/dockercomposetemplate")
        self.server = read("servidor/docker-compose.yml")

    def test_project_services_declare_every_variable(self) -> None:
        # `--env-file` na linha de comando resolve a interpolacao e continua
        # documentado no topo do template; nenhum `env_file:` de servico pode
        # voltar, porque `auth` e `rest` declaram tudo que consomem.
        self.assertNotIn("      - ../../.env", self.template)
        for service in ("auth", "rest"):
            entries = env_file_entries(service_block(self.template, service))
            self.assertEqual(
                entries,
                [],
                f"{service} deve receber apenas o bloco environment declarado",
            )

    def test_shared_services_never_mount_the_global_env(self) -> None:
        for service in ("db", "realtime", "supavisor", "functions", "storage"):
            entries = env_file_entries(service_block(self.server, service))
            self.assertNotIn(
                ".env",
                entries,
                f"{service} recebe o .env global inteiro",
            )

    def test_storage_keeps_its_scoped_env(self) -> None:
        entries = env_file_entries(service_block(self.server, "storage"))
        self.assertEqual(entries, [".storage.env"])

    def test_services_declare_what_they_consume(self) -> None:
        # Variaveis que so chegavam pelo env_file global e passaram a ser
        # declaradas explicitamente.
        db = service_block(self.server, "db")
        self.assertIn("POSTGRES_USER: ${POSTGRES_USER}", db)
        self.assertIn("META_GUEST_PASSWORD: ${META_GUEST_PASSWORD}", db)

        functions = service_block(self.server, "functions")
        for name in ("POSTGRES_USER", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_PASSWORD"):
            self.assertIn(f"{name}: ${{{name}}}", functions)

        auth = service_block(self.template, "auth")
        self.assertIn(
            "GOTRUE_MAILER_EXTERNAL_HOSTS: ${GOTRUE_MAILER_EXTERNAL_HOSTS}", auth
        )

    def test_no_control_plane_secret_is_declared_for_a_tenant_service(self) -> None:
        for service in ("auth", "rest"):
            block = service_block(self.template, service)
            for secret in CONTROL_PLANE_SECRETS:
                self.assertNotIn(secret, block, f"{secret} exposto em {service}")


class EdgeFunctionWorkersGetOnlyTheirTenantEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main = read("servidor/volumes/functions/main/index.ts")

    def test_worker_env_is_not_the_container_env(self) -> None:
        # `...globalEnv` entregava as 133 variaveis do servidor ao worker que
        # executa a function, e de la para `Deno.env`.
        self.assertNotIn("...globalEnv", self.main)
        self.assertIn("let workerEnv: Record<string, string> = {}", self.main)

    def test_worker_env_carries_the_tenant_contract(self) -> None:
        for name in (
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "JWT_SECRET",
            "PROJECT_REF",
        ):
            self.assertIn(f"{name}:", self.main)

    def test_worker_env_never_carries_a_cluster_dsn(self) -> None:
        self.assertNotIn("SUPABASE_DB_URL", self.main)
        self.assertNotIn("POSTGRES_PASSWORD", self.main)


if __name__ == "__main__":
    unittest.main()
