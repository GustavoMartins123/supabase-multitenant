#!/usr/bin/env python3
"""Reaplica o perfil de recursos aos .env de projetos existentes.

O perfil e o teto do PROJETO, rateado entre nginx/auth/rest. Em vez de
reimplementar o rateio (uma terceira copia dos pesos, alem do bash e da
Projects API), este utilitario chama o proprio helper canonico usado pelo
lifecycle — `apply_project_resource_limits`. O modo de simulacao roda o
helper sobre uma COPIA do .env e mostra o diff, entao o plano exibido e
exatamente o que seria gravado.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER_ENV = ROOT / "servidor" / ".env"
DEFAULT_PROJECTS_DIR = ROOT / "servidor" / "projects"
HELPER = ROOT / "servidor" / "generateProject" / "lib" / "resource_profiles.sh"

PROFILE_KEY = "PROJECT_RESOURCE_PROFILE"
VALID_PROFILES = {"small", "medium", "large"}
MANAGED_RE = re.compile(
    r"(?m)^(?:export[ \t]+)?"
    r"(PROJECT_(?:RESOURCE_PROFILE|MEM_LIMIT|CPUS|PIDS_LIMIT"
    r"|(?:NGINX|AUTH|REST)_(?:MEM_LIMIT|CPUS|PIDS_LIMIT)))[ \t]*=(.*)$"
)


class MigrationError(RuntimeError):
    pass


def value_for(content: str, key: str) -> str:
    matches = re.findall(rf"(?m)^{re.escape(key)}=(.*)$", content)
    if len(matches) > 1:
        raise MigrationError(f"{key} possui atribuicoes duplicadas")
    if not matches:
        return ""
    return matches[0].strip().strip('"').strip("'")


def profile_for(project_env: Path, root_env: Path) -> str:
    """Perfil proprio do projeto; so cai no padrao do .env raiz se ausente.

    Sobrescrever um projeto `large` com o default global seria um rebaixamento
    silencioso de capacidade.
    """
    own = value_for(project_env.read_text(encoding="utf-8"), PROFILE_KEY)
    profile = own or value_for(root_env.read_text(encoding="utf-8"), PROFILE_KEY)
    profile = profile or "medium"
    if profile not in VALID_PROFILES:
        origin = project_env if own else root_env
        raise MigrationError(
            f"{PROFILE_KEY} invalido em {origin}: {profile} "
            "(use small, medium ou large)"
        )
    return profile


def managed_values(content: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2).strip()
        for match in MANAGED_RE.finditer(content)
    }


def apply_helper(root_env: Path, project_env: Path, profile: str) -> None:
    """Delega ao helper de lifecycle: uma unica implementacao do rateio."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; apply_project_resource_limits "$2" "$3" "$4"',
            "bash",
            str(HELPER),
            str(root_env),
            str(project_env),
            profile,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MigrationError(
            (result.stderr or result.stdout).strip() or "helper falhou"
        )


def plan_for(root_env: Path, project_env: Path, profile: str) -> dict[str, str]:
    """Roda o helper numa copia e devolve as chaves que mudariam."""
    before = managed_values(project_env.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / ".env"
        shutil.copy2(project_env, copy)
        apply_helper(root_env, copy, profile)
        after = managed_values(copy.read_text(encoding="utf-8"))
    return {
        key: value for key, value in after.items() if before.get(key) != value
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-env", type=Path, default=DEFAULT_SERVER_ENV)
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="grava as alteracoes; sem esta flag apenas mostra o plano",
    )
    args = parser.parse_args()

    if not args.server_env.is_file():
        print(f"servidor/.env ausente em {args.server_env}; rode o setup.", file=sys.stderr)
        return 1
    if not args.projects_dir.is_dir():
        print(f"diretorio de projetos ausente: {args.projects_dir}", file=sys.stderr)
        return 1
    if not HELPER.is_file():
        print(f"helper ausente: {HELPER}", file=sys.stderr)
        return 1

    changed = 0
    for project_dir in sorted(args.projects_dir.iterdir()):
        project_env = project_dir / ".env"
        if not project_dir.is_dir() or not project_env.is_file():
            continue
        try:
            profile = profile_for(project_env, args.server_env)
            pending = plan_for(args.server_env, project_env, profile)
        except MigrationError as error:
            print(f"Erro em {project_dir.name}: {error}", file=sys.stderr)
            return 1
        if not pending:
            print(f"[ok] {project_dir.name}: perfil {profile} ja aplicado")
            continue
        plan = ", ".join(f"{key}={value}" for key, value in sorted(pending.items()))
        if args.apply:
            original = os.stat(project_env)
            try:
                apply_helper(args.server_env, project_env, profile)
            except MigrationError as error:
                print(f"Erro em {project_dir.name}: {error}", file=sys.stderr)
                return 1
            os.chmod(project_env, original.st_mode & 0o777)
            print(f"[migrado] {project_dir.name} ({profile}): {plan}")
        else:
            print(f"[pendente] {project_dir.name} ({profile}): {plan}")
        changed += 1

    if not args.apply and changed:
        print("\nNada foi gravado. Rode novamente com --apply para aplicar.")
    elif changed == 0:
        print("Todos os projetos ja estao com o perfil aplicado.")
    else:
        print(
            "\nRecreate dos projetos necessario para o Compose consumir os novos limites."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
