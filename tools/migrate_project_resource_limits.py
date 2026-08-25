#!/usr/bin/env python3
"""Aplica o perfil de recursos aos .env de projetos existentes.

Os containers nginx/auth/rest de cada projeto passaram a consumir
PROJECT_MEM_LIMIT, PROJECT_CPUS e PROJECT_PIDS_LIMIT via interpolacao com ':?'
no dockercomposetemplate. Projetos criados depois dessa mudanca recebem as
chaves do lifecycle; os anteriores precisam deste migrador antes do proximo
recreate. Idempotente: pode rodar quantas vezes quiser.

Por padrao apenas mostra o plano (--dry-run). Use --apply para gravar.
O script nao imprime nenhum segredo.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER_ENV = ROOT / "servidor" / ".env"
DEFAULT_PROJECTS_DIR = ROOT / "servidor" / "projects"

PROFILE_KEYS = ("MEMORY", "CPUS", "PIDS")
TARGET_KEYS = {
    "MEMORY": "PROJECT_MEM_LIMIT",
    "CPUS": "PROJECT_CPUS",
    "PIDS": "PROJECT_PIDS_LIMIT",
}
PROFILE_KEY = "PROJECT_RESOURCE_PROFILE"
VALID_PROFILES = {"small", "medium", "large"}
ASSIGNMENT_RE = re.compile(
    r"(?m)^(?:export[ \t]+)?"
    r"(PROJECT_(?:RESOURCE_PROFILE|MEM_LIMIT|CPUS|PIDS_LIMIT))[ \t]*=(.*)$"
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


def resolve_limits(root_env: Path, profile: str) -> dict[str, str]:
    content = root_env.read_text(encoding="utf-8")
    upper = profile.upper()
    limits: dict[str, str] = {}
    for suffix in PROFILE_KEYS:
        raw = value_for(content, f"PROJECT_RES_{upper}_{suffix}")
        if not raw or raw == "pass":
            raise MigrationError(
                f"PROJECT_RES_{upper}_{suffix} ausente ou placeholder no {root_env}; "
                "atualize o arquivo a partir do .env.example"
            )
        limits[TARGET_KEYS[suffix]] = raw
    # A API de settings le o perfil do .env do projeto: sem esta chave o
    # seletor do Studio abre vazio, mesmo com os limites corretos aplicados.
    limits[PROFILE_KEY] = profile
    return limits


def upsert(project_env: Path, limits: dict[str, str]) -> tuple[list[str], list[str]]:
    """Retorna (adicionadas, atualizadas) sem gravar nada."""
    content = project_env.read_text(encoding="utf-8")
    existing = {
        match.group(1): match.group(2).strip()
        for match in ASSIGNMENT_RE.finditer(content)
    }
    added: list[str] = []
    updated: list[str] = []
    for key, new_value in limits.items():
        current = existing.get(key)
        if current is None:
            added.append(key)
        elif current != new_value:
            updated.append(key)
    return added, updated


def write_limits(project_env: Path, limits: dict[str, str]) -> None:
    lines = [
        line
        for line in project_env.read_text(encoding="utf-8").splitlines()
        if not ASSIGNMENT_RE.match(line)
    ]
    lines.extend(f"{key}={value}" for key, value in limits.items())
    # Reescreve no mesmo inode para preservar dono e permissoes (600).
    with project_env.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


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

    changed = 0
    for project_dir in sorted(args.projects_dir.iterdir()):
        project_env = project_dir / ".env"
        if not project_dir.is_dir() or not project_env.is_file():
            continue
        try:
            limits = resolve_limits(
                args.server_env, profile_for(project_env, args.server_env)
            )
            added, updated = upsert(project_env, limits)
        except MigrationError as error:
            print(f"Erro em {project_dir.name}: {error}", file=sys.stderr)
            return 1
        if not (added or updated):
            print(f"[ok] {project_dir.name}: limites ja aplicados")
            continue
        plan = ", ".join(added + [f"{key} (valor divergente)" for key in updated])
        if args.apply:
            write_limits(project_env, limits)
            print(f"[migrado] {project_dir.name}: {plan}")
        else:
            print(f"[pendente] {project_dir.name}: {plan}")
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
