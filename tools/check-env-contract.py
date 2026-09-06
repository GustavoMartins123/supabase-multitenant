"""Contrato estatico das variaveis de ambiente da plataforma.

Compara o que os `.env.example` declaram com o que o codigo realmente
consome (Python, Compose, Lua), valida higiene de valores (placeholders
restantes, espacos, subnet/gateway, labels do Traefik) e, opcionalmente,
roda `docker compose config -q` nos dois perfis de topologia.

Uso:
    python3 tools/check-env-contract.py [--compose] [--env-file DIR]

Sem `--compose`, nao precisa de Docker nem de `.env` gerados: e puro
estatico e roda no CI. Com `--compose`, valida a interpolacao real dos
Composes (pula com aviso se `docker compose` nao existir).
"""

from __future__ import annotations

import ipaddress
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXAMPLE_FILES = [
    "servidor/.env.example",
    "servidor/.analytics.env.example",
    "servidor/.storage.env.example",
    "studio/.env.example",
    "studio/.analytics.env.example",
]

REAL_FILES = [
    "servidor/.env",
    "servidor/.analytics.env",
    "servidor/.storage.env",
    "studio/.env",
    "studio/.analytics.env",
]

PYTHON_SCAN_DIRS = [
    "servidor/api-internal/app",
    "servidor/host-agent",
    "servidor/traefik",
    "tools",
]

COMPOSE_FILES = [
    "servidor/docker-compose.yml",
    "servidor/docker-compose-api.yml",
    "servidor/docker-compose.single-node.yml",
    "servidor/docker-compose.split-node.yml",
    "servidor/traefik/docker-compose.yml",
    "studio/docker-compose.yml",
]

LUA_SCAN_DIR = "studio/nginx/lua"

SETUP_SCRIPT = "setup.sh"

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
PY_GETENV_RE = re.compile(r"os\.getenv\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")
PY_ENVIRON_RE = re.compile(
    r"os\.environ(?:\.get)?\[\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']"
)
COMPOSE_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}")
ENV_ASSIGN_RE = re.compile(r"^\s*(?:-\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]")
PLACEHOLDER_TOKEN_RE = re.compile(r"<[^<>\s]+>")

KNOWN_OPTIONAL = {
    "ANALYTICS_INTERNAL_URL": "default em runtime_config.py",
    "DB_DSN": "computado no environment do Compose",
    "LEGACY_FERNET_SECRET": "migracao opt-in (migrate_project_secrets.py)",
    "META_ADMIN_DSN": "computado no environment do Compose",
    "PG_META_ALLOWED_HOSTS": "default em runtime_config.py + Compose",
    "PG_META_INTERNAL_URL": "default em runtime_config.py",
    "PLATFORM_LOAD_ANON_KEY": "ferramenta manual (platform_load_probe.py)",
    "PLATFORM_LOAD_SERVICE_KEY": "ferramenta manual (platform_load_probe.py)",
    "REALTIME_INTERNAL_URL": "default em runtime_config.py",
    "SERVER_ENV_PATH": "default em project_settings.py",
    "STUDIO_CACHE_INVALIDATION_URL": "default em runtime_config.py",
    "SUPAVISOR_INTERNAL_URL": "default em runtime_config.py",
}

REAL_FILE_PASS_ALLOWLIST = {
    "TRAEFIK_ACME_EMAIL": "exigido apenas com TRAEFIK_TLS_MODE=acme",
}

REQUIRED_IN_REAL_ENV = [
    "PROJECT_SECRETS_MASTER_KEY",
    "PG_META_CRYPTO_KEY",
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
    "NGINX_HMAC_SECRET",
    "STUDIO_GATEWAY_HMAC_SECRET",
    "PROJECTS_API_HMAC_SECRET",
    "LOGFLARE_PRIVATE_ACCESS_TOKEN",
    "HOST_AGENT_HMAC_SECRET",
]

OPTIONAL_EMPTY_IN_REAL_ENV = {
    "PROJECT_SECRETS_PREVIOUS_MASTER_KEYS",
    "FUNCTIONS_SUPABASE_ANON_KEY",
    "FUNCTIONS_SUPABASE_SERVICE_ROLE_KEY",
    "OPENAI_API_KEY",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def render(self) -> int:
        for message in self.errors:
            print(f"ERROR: {message}")
        for message in self.warnings:
            print(f"WARNING: {message}")
        print(
            f"env-contract: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s)"
        )
        return 1 if self.errors else 0


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = KEY_RE.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def load_declared() -> dict[str, list[str]]:
    declared: dict[str, list[str]] = {}
    for relative in EXAMPLE_FILES:
        path = ROOT / relative
        for key in parse_env_file(path):
            declared.setdefault(key, []).append(relative)
    return declared


def scan_python() -> set[str]:
    names: set[str] = set()
    for relative in PYTHON_SCAN_DIRS:
        for path in (ROOT / relative).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            names.update(PY_GETENV_RE.findall(text))
            names.update(PY_ENVIRON_RE.findall(text))
    return names


def scan_compose_vars() -> set[str]:
    names: set[str] = set()
    for relative in COMPOSE_FILES:
        path = ROOT / relative
        if path.is_file():
            names.update(COMPOSE_VAR_RE.findall(path.read_text(encoding="utf-8")))
    return names


def scan_compose_defined() -> set[str]:
    names: set[str] = set()
    for relative in COMPOSE_FILES:
        path = ROOT / relative
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = ENV_ASSIGN_RE.match(line)
            if match:
                names.add(match.group(1))
    return names


def scan_lua() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / LUA_SCAN_DIR).rglob("*.lua"):
        names.update(PY_GETENV_RE.findall(path.read_text(encoding="utf-8")))
    return names


def check_parity(report: Report) -> None:
    declared = load_declared()
    python_names = scan_python()
    compose_names = scan_compose_vars()
    compose_defined = scan_compose_defined()
    known = set(declared) | compose_defined | set(KNOWN_OPTIONAL)
    for name in sorted(python_names - known):
        report.error(
            f"Python consome {name} mas nenhuma fonte declara "
            "(adicione ao .env.example ou a KNOWN_OPTIONAL)"
        )
    for name in sorted(compose_names - set(declared) - compose_defined):
        report.error(
            f"Compose interpola {name} mas nenhum .env.example declara"
        )
    setup_text = (ROOT / SETUP_SCRIPT).read_text(encoding="utf-8")
    pass_keys: set[str] = set()
    for relative in EXAMPLE_FILES:
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
            if line.endswith("=pass"):
                pass_keys.add(line[:-len("=pass")])
    for key in sorted(pass_keys):
        if key not in setup_text:
            report.warning(
                f"{key}=pass no example sem geracao no setup.sh "
                "(intencional? documente ou gere)"
            )


def check_example_hygiene(report: Report) -> None:
    for relative in EXAMPLE_FILES:
        path = ROOT / relative
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in raw:
                report.error(f"{relative}:{lineno}: linha sem '=': {raw!r}")
                continue
            key, _, value = raw.partition("=")
            if key != key.strip() or " " in key:
                report.error(
                    f"{relative}:{lineno}: chave com espaco: {key!r}"
                )
            if value != value.strip():
                report.error(
                    f"{relative}:{lineno}: valor com espaco nas bordas: "
                    f"{key}={value!r}"
                )


def _cidr_list(value: str, *, allow_placeholders: bool) -> list[str]:
    problems: list[str] = []
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        problems.append("lista vazia")
    for item in items:
        if allow_placeholders and PLACEHOLDER_TOKEN_RE.search(item):
            continue
        candidate = item.split("/")[0]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            problems.append(f"IP/CIDR invalido: {item!r}")
            continue
        if "/" in item:
            try:
                ipaddress.ip_network(item, strict=False)
            except ValueError:
                problems.append(f"CIDR invalido: {item!r}")
    return problems


def check_network(report: Report, values: dict[str, str], origin: str) -> None:
    subnet_raw = values.get("SUPABASE_NETWORK_SUBNET", "")
    gateway_raw = values.get("SUPABASE_NETWORK_GATEWAY", "")
    ip_range_raw = values.get("SUPABASE_NETWORK_IP_RANGE", "")
    if not subnet_raw or PLACEHOLDER_TOKEN_RE.search(subnet_raw):
        return
    try:
        subnet = ipaddress.ip_network(subnet_raw.strip(), strict=False)
    except ValueError:
        report.error(f"{origin}: SUPABASE_NETWORK_SUBNET invalida: {subnet_raw!r}")
        return
    if gateway_raw and not PLACEHOLDER_TOKEN_RE.search(gateway_raw):
        try:
            gateway = ipaddress.ip_address(gateway_raw.strip())
        except ValueError:
            report.error(
                f"{origin}: SUPABASE_NETWORK_GATEWAY invalido: {gateway_raw!r}"
            )
        else:
            if gateway not in subnet:
                report.error(
                    f"{origin}: gateway {gateway} fora da subnet {subnet}"
                )
    if ip_range_raw and not PLACEHOLDER_TOKEN_RE.search(ip_range_raw):
        try:
            ip_range = ipaddress.ip_network(ip_range_raw.strip(), strict=False)
        except ValueError:
            report.error(
                f"{origin}: SUPABASE_NETWORK_IP_RANGE invalido: {ip_range_raw!r}"
            )
        else:
            if isinstance(subnet, ipaddress.IPv4Network):
                contained = isinstance(
                    ip_range, ipaddress.IPv4Network
                ) and ip_range.subnet_of(subnet)
            else:
                contained = isinstance(
                    ip_range, ipaddress.IPv6Network
                ) and ip_range.subnet_of(subnet)
            if not contained:
                report.error(
                    f"{origin}: ip-range {ip_range} fora da subnet {subnet}"
                )
    allowed = values.get("PROJECTS_API_ALLOWED_IP_RANGES", "")
    if allowed:
        for problem in _cidr_list(
            allowed, allow_placeholders=origin.endswith(".example")
        ):
            report.error(f"{origin}: PROJECTS_API_ALLOWED_IP_RANGES: {problem}")


def check_traefik_labels(report: Report) -> None:
    for relative in COMPOSE_FILES:
        path = ROOT / relative
        if not path.is_file():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if "traefik.http." not in line:
                continue
            if line.count("`") % 2:
                report.error(
                    f"{relative}:{lineno}: crases desbalanceadas em label: "
                    f"{line.strip()[:100]}"
                )
            for host in re.findall(r"`([^`]*)`", line):
                if host != host.strip():
                    report.error(
                        f"{relative}:{lineno}: hostname com espaco: {host!r}"
                    )
                if "," in host:
                    report.error(
                        f"{relative}:{lineno}: virgula dentro de hostname: "
                        f"{host!r}"
                    )


def check_real_files(
    report: Report, real_files: list[str] | None = None
) -> None:
    targets = real_files if real_files is not None else REAL_FILES
    missing = [r for r in targets if not (ROOT / r).is_file()]
    if missing:
        report.warning(
            "arquivos .env reais ausentes (setup.sh ainda nao rodou?): "
            + ", ".join(missing)
        )
        return
    merged: dict[str, str] = {}
    for relative in targets:
        values = parse_env_file(ROOT / relative)
        for key, value in values.items():
            merged.setdefault(key, value)
        for key in REQUIRED_IN_REAL_ENV:
            if relative != "servidor/.env" and key in (
                "PROJECT_SECRETS_MASTER_KEY",
                "PG_META_CRYPTO_KEY",
                "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
                "NGINX_HMAC_SECRET",
                "HOST_AGENT_HMAC_SECRET",
            ):
                continue
            if key in values and (
                not values[key].strip() or values[key].strip() == "pass"
            ) and key not in REAL_FILE_PASS_ALLOWLIST:
                report.error(
                    f"{relative}: {key} vazio ou placeholder apos setup"
                )
        for key, value in values.items():
            if key in OPTIONAL_EMPTY_IN_REAL_ENV:
                continue
            if value != value.strip():
                report.error(
                    f"{relative}: {key} com espaco nas bordas: {value!r}"
                )
            if PLACEHOLDER_TOKEN_RE.search(value):
                report.error(
                    f"{relative}: {key} com placeholder nao substituido: "
                    f"{value!r}"
                )
            if value.strip() == "pass" and key not in REAL_FILE_PASS_ALLOWLIST:
                report.error(f"{relative}: {key}=pass apos setup")
    check_network(report, merged, "real .env files")


def _example_env_for_compose(relative: str, tmpdir: pathlib.Path) -> pathlib.Path:
    values = parse_env_file(ROOT / relative)
    lines = [
        f"{key}={value if value.strip() else 'dummy'}"
        for key, value in values.items()
    ]
    target = tmpdir / (pathlib.Path(relative).parent.name + ".env")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def check_compose_profiles(report: Report) -> None:
    import tempfile

    docker = shutil.which("docker")
    if docker is None:
        report.warning("docker ausente: pulando `compose config -q`")
        return
    combos = [
        (["servidor/docker-compose.yml"], "servidor/.env.example"),
        (
            [
                "servidor/docker-compose-api.yml",
                "servidor/docker-compose.single-node.yml",
            ],
            "servidor/.env.example",
        ),
        (
            [
                "servidor/docker-compose-api.yml",
                "servidor/docker-compose.split-node.yml",
            ],
            "servidor/.env.example",
        ),
        (["servidor/traefik/docker-compose.yml"], "servidor/.env.example"),
        (["studio/docker-compose.yml"], "studio/.env.example"),
    ]
    with tempfile.TemporaryDirectory(prefix="env-contract-") as tmp:
        tmpdir = pathlib.Path(tmp)
        for files, env in combos:
            env_file = _example_env_for_compose(env, tmpdir)
            cmd = [docker, "compose", "--env-file", str(env_file)]
            for relative in files:
                cmd += ["-f", str(ROOT / relative)]
            cmd += ["config", "-q"]
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                report.error(f"compose {'+'.join(files)}: falha ao executar: {exc}")
                continue
            if completed.returncode != 0:
                report.error(
                    f"compose {'+'.join(files)}: config -q falhou: "
                    f"{completed.stderr.strip()[:500]}"
                )


def main() -> int:
    report = Report()
    check_parity(report)
    check_example_hygiene(report)
    for relative in EXAMPLE_FILES:
        values = parse_env_file(ROOT / relative)
        check_network(report, values, relative)
    check_traefik_labels(report)
    check_real_files(report)
    if "--compose" in sys.argv[1:]:
        check_compose_profiles(report)
    return report.render()


if __name__ == "__main__":
    raise SystemExit(main())
