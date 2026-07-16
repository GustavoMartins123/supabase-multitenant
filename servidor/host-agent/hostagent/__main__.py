"""Entrypoint: ``python -m hostagent --root /caminho/para/servidor``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .agent import run_agent
from .config import ConfigError, load_config


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hostagent",
        description="Host-agent do Supabase multitenant (comandos fechados).",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("HOST_AGENT_ROOT", ""),
        help="Diretorio 'servidor' do repositorio (contem .env, projects/ e generateProject/).",
    )
    parser.add_argument("--verbose", action="store_true", help="Logs em nivel DEBUG.")
    options = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not options.root:
        print("Informe --root ou HOST_AGENT_ROOT.", file=sys.stderr)
        return 2

    try:
        config = load_config(options.root)
    except ConfigError as exc:
        print(f"Configuracao invalida: {exc}", file=sys.stderr)
        return 2

    try:
        asyncio.run(run_agent(config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
