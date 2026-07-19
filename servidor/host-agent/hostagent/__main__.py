"""Entrypoint: ``python -m hostagent --root /caminho/para/servidor``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .agent import run_agent
from .config import ConfigError, load_config
from .db import HostAgentSchemaTimeout, wait_for_host_agent_schema


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
    schema_mode = parser.add_mutually_exclusive_group()
    schema_mode.add_argument(
        "--check-schema",
        action="store_true",
        help="Verifica uma vez se a Projects API ja criou o schema do agent.",
    )
    schema_mode.add_argument(
        "--wait-for-schema",
        action="store_true",
        help="Aguarda o schema do agent antes de encerrar com sucesso.",
    )
    parser.add_argument(
        "--schema-timeout",
        type=float,
        help="Timeout da espera; por padrao usa HOST_AGENT_SCHEMA_WAIT_TIMEOUT.",
    )
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

    if options.check_schema or options.wait_for_schema:
        timeout = 0.0 if options.check_schema else (
            options.schema_timeout
            if options.schema_timeout is not None
            else config.schema_wait_timeout
        )
        if timeout < 0:
            print("--schema-timeout nao pode ser negativo.", file=sys.stderr)
            return 2
        try:
            asyncio.run(
                wait_for_host_agent_schema(config.dsn, timeout=timeout)
            )
        except HostAgentSchemaTimeout as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print("Schema do host-agent pronto.")
        return 0

    try:
        asyncio.run(run_agent(config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
