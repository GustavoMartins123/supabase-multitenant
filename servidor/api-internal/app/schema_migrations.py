"""Migrations versionadas do control plane.

O schema do database `postgres` pertence aos arquivos `.sql` de
`app/migrations`. Cada arquivo recebe uma versao de quatro digitos, e o ledger
`control_plane_schema_migrations` registra o que ja foi aplicado, com checksum,
autor e duracao.

Duas fronteiras separam quem pode alterar o schema:

* o comando privilegiado ``python -m app.schema_migrations apply`` aplica as
  versoes pendentes e provisiona as identidades de banco. Ele roda com o DSN
  administrativo, uma vez por deploy, antes de qualquer processo servir
  trafego;
* o processo que atende requisicoes chama apenas
  :func:`verify_control_plane_schema`, que le o ledger e falha fechado quando o
  banco esta atras da imagem. Nenhum DDL sai desse caminho.

Rollback de schema nao e suportado: a correcao de uma migration aplicada e uma
nova versao (forward-fix). Editar um arquivo ja aplicado muda o checksum e e
recusado explicitamente.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass

import asyncpg


MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"
LEDGER_TABLE = "control_plane_schema_migrations"
LEDGER_REGCLASS = f"public.{LEDGER_TABLE}"
MIGRATION_FILENAME_RE = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

# Chave fixa do advisory lock que serializa dois migradores concorrentes.
MIGRATION_ADVISORY_LOCK_KEY = 7_243_118_905_412_667_001

# Um deploy encontra o processo anterior ainda no ar. Sem limite, um ALTER
# ficaria enfileirado atras dele e travaria o deploy inteiro sem diagnostico.
MIGRATION_LOCK_TIMEOUT = "30s"

LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    version TEXT PRIMARY KEY CHECK (version ~ '^[0-9]{{4}}$'),
    name TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{{64}}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by TEXT NOT NULL DEFAULT current_user,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0)
)
"""

APPLY_COMMAND = "python -m app.schema_migrations apply"


class SchemaMigrationError(RuntimeError):
    """Estado de schema incompativel ou conjunto de migrations invalido."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: pathlib.Path
    sql: str
    checksum: str

    @property
    def label(self) -> str:
        return f"{self.version}_{self.name}"


@dataclass(frozen=True)
class SchemaVerification:
    current_version: str | None
    applied_versions: tuple[str, ...]
    unknown_versions: tuple[str, ...]


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(
    directory: pathlib.Path | None = None,
) -> tuple[Migration, ...]:
    """Le o diretorio de migrations e valida a sequencia de versoes."""

    base = directory or MIGRATIONS_DIR
    if not base.is_dir():
        raise SchemaMigrationError(f"diretorio de migrations ausente: {base}")

    migrations: list[Migration] = []
    for path in sorted(base.iterdir()):
        if path.is_dir() or path.suffix != ".sql":
            continue
        match = MIGRATION_FILENAME_RE.fullmatch(path.name)
        if match is None:
            raise SchemaMigrationError(
                f"nome de migration fora do padrao NNNN_nome.sql: {path.name}"
            )
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise SchemaMigrationError(f"migration vazia: {path.name}")
        migrations.append(
            Migration(
                version=match.group("version"),
                name=match.group("name"),
                path=path,
                sql=sql,
                checksum=_checksum(sql),
            )
        )

    if not migrations:
        raise SchemaMigrationError(f"nenhuma migration encontrada em {base}")

    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise SchemaMigrationError("versoes de migration duplicadas")
    expected = [f"{index:04d}" for index in range(1, len(migrations) + 1)]
    if versions != expected:
        raise SchemaMigrationError(
            "sequencia de migrations com buracos: "
            f"esperado {expected[0]}..{expected[-1]}, encontrado {versions}"
        )
    return tuple(migrations)


async def _ledger_exists(conn: asyncpg.Connection) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", LEDGER_REGCLASS))


async def read_ledger(conn: asyncpg.Connection) -> dict[str, str]:
    """Retorna `versao -> checksum` do que ja foi aplicado."""

    if not await _ledger_exists(conn):
        return {}
    rows = await conn.fetch(
        f"SELECT version, checksum FROM {LEDGER_TABLE} ORDER BY version"
    )
    return {row["version"]: row["checksum"] for row in rows}


def _pending(
    migrations: tuple[Migration, ...], applied: dict[str, str]
) -> list[Migration]:
    return [
        migration for migration in migrations if migration.version not in applied
    ]


def _drifted(
    migrations: tuple[Migration, ...], applied: dict[str, str]
) -> list[Migration]:
    return [
        migration
        for migration in migrations
        if migration.version in applied
        and applied[migration.version] != migration.checksum
    ]


def _assert_no_drift(drifted: list[Migration]) -> None:
    if not drifted:
        return
    labels = ", ".join(migration.label for migration in drifted)
    raise SchemaMigrationError(
        "migrations ja aplicadas foram editadas: "
        f"{labels}. Corrija criando uma nova versao (forward-fix) e restaure o "
        "conteudo original dos arquivos."
    )


async def apply_migrations(
    conn: asyncpg.Connection,
    *,
    migrations: tuple[Migration, ...] | None = None,
) -> list[Migration]:
    """Aplica as versoes pendentes em ordem e devolve o que foi aplicado."""

    catalog = migrations if migrations is not None else discover_migrations()
    await conn.execute(f"SET lock_timeout = '{MIGRATION_LOCK_TIMEOUT}'")
    await conn.execute(
        "SELECT pg_advisory_lock($1)", MIGRATION_ADVISORY_LOCK_KEY
    )
    try:
        await conn.execute(LEDGER_DDL)
        applied = await read_ledger(conn)
        _assert_no_drift(_drifted(catalog, applied))

        executed: list[Migration] = []
        for migration in _pending(catalog, applied):
            started = time.monotonic()
            try:
                async with conn.transaction():
                    await conn.execute(migration.sql)
                    duration_ms = int((time.monotonic() - started) * 1000)
                    await conn.execute(
                        f"""
                        INSERT INTO {LEDGER_TABLE}(
                            version, name, checksum, duration_ms
                        ) VALUES($1, $2, $3, $4)
                        """,
                        migration.version,
                        migration.name,
                        migration.checksum,
                        duration_ms,
                    )
            except asyncpg.PostgresError as exc:
                raise SchemaMigrationError(
                    f"{migration.label} falhou e foi revertida: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            executed.append(migration)
        return executed
    finally:
        await conn.execute(
            "SELECT pg_advisory_unlock($1)", MIGRATION_ADVISORY_LOCK_KEY
        )


async def verify_control_plane_schema(
    pool: asyncpg.Pool,
    *,
    migrations: tuple[Migration, ...] | None = None,
) -> SchemaVerification:
    """Confere o ledger sem alterar o banco. Falha fechado se houver pendencia.

    Versoes presentes no banco e ausentes na imagem sao devolvidas em
    ``unknown_versions``: o banco esta a frente do codigo e a correcao e
    avancar a imagem, nunca reverter o schema.
    """

    catalog = migrations if migrations is not None else discover_migrations()
    async with pool.acquire() as conn:
        if not await _ledger_exists(conn):
            raise SchemaMigrationError(
                f"tabela {LEDGER_TABLE} ausente: o schema do control plane "
                f"nunca foi migrado. Execute `{APPLY_COMMAND}` com o DSN "
                "administrativo antes de subir a Projects API."
            )
        applied = await read_ledger(conn)

    pending = _pending(catalog, applied)
    if pending:
        labels = ", ".join(migration.label for migration in pending)
        raise SchemaMigrationError(
            f"schema do control plane desatualizado; faltam: {labels}. "
            f"Execute `{APPLY_COMMAND}` com o DSN administrativo."
        )
    _assert_no_drift(_drifted(catalog, applied))

    known = {migration.version for migration in catalog}
    return SchemaVerification(
        current_version=max(applied) if applied else None,
        applied_versions=tuple(sorted(applied)),
        unknown_versions=tuple(sorted(set(applied) - known)),
    )


async def _connect_pool(dsn: str, *, wait_timeout: float) -> asyncpg.Pool:
    deadline = time.monotonic() + max(0.0, wait_timeout)
    last_error: Exception | None = None
    while True:
        try:
            return await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        except (OSError, asyncpg.PostgresError) as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            raise SchemaMigrationError(
                "nao foi possivel conectar no control plane em "
                f"{wait_timeout:g}s: {type(last_error).__name__}"
            )
        await asyncio.sleep(2.0)


def _require_dsn() -> str:
    dsn = (os.getenv("DB_DSN") or "").strip()
    if not dsn:
        raise SchemaMigrationError("DB_DSN e obrigatorio")
    return dsn


async def _command_apply(*, wait_timeout: float, skip_roles: bool) -> int:
    from app.control_plane_roles import ensure_host_agent_rw_role, ensure_key_authorizer_role

    key_authorizer_password = (
        os.getenv("KEY_AUTHORIZER_DB_PASSWORD") or ""
    ).strip()
    if not skip_roles and not key_authorizer_password:
        raise SchemaMigrationError("KEY_AUTHORIZER_DB_PASSWORD e obrigatorio")
    host_agent_password = (
        os.getenv("HOST_AGENT_DB_PASSWORD") or ""
    ).strip()
    if not skip_roles and not host_agent_password:
        raise SchemaMigrationError("HOST_AGENT_DB_PASSWORD e obrigatorio")

    catalog = discover_migrations()
    pool = await _connect_pool(_require_dsn(), wait_timeout=wait_timeout)
    try:
        async with pool.acquire() as conn:
            executed = await apply_migrations(conn, migrations=catalog)
        if executed:
            for migration in executed:
                print(f"[migrations] aplicada {migration.label}")
        else:
            print("[migrations] nenhuma versao pendente")
        print(f"[migrations] versao atual {catalog[-1].version}")

        if skip_roles:
            print("[migrations] provisionamento de roles ignorado")
        else:
            await ensure_key_authorizer_role(
                pool, password=key_authorizer_password
            )
            print("[migrations] identidade key_authorizer provisionada")
            await ensure_host_agent_rw_role(
                pool, password=host_agent_password
            )
            print("[migrations] identidade host_agent_rw provisionada")
    finally:
        await pool.close()
    return 0


async def _command_status(*, wait_timeout: float) -> int:
    catalog = discover_migrations()
    pool = await _connect_pool(_require_dsn(), wait_timeout=wait_timeout)
    try:
        async with pool.acquire() as conn:
            applied = await read_ledger(conn)
    finally:
        await pool.close()

    for migration in catalog:
        checksum = applied.get(migration.version)
        if checksum is None:
            state = "pendente"
        elif checksum != migration.checksum:
            state = "checksum divergente"
        else:
            state = "aplicada"
        print(f"{migration.label:52s} {state}")
    for version in sorted(set(applied) - {m.version for m in catalog}):
        print(f"{version:52s} aplicada no banco e ausente nesta imagem")
    return 0


async def _command_verify(*, wait_timeout: float) -> int:
    pool = await _connect_pool(_require_dsn(), wait_timeout=wait_timeout)
    try:
        verification = await verify_control_plane_schema(pool)
    finally:
        await pool.close()
    print(f"[migrations] versao atual {verification.current_version}")
    if verification.unknown_versions:
        print(
            "[migrations] banco a frente desta imagem: "
            + ", ".join(verification.unknown_versions)
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.schema_migrations",
        description="Aplica e inspeciona as migrations do control plane.",
    )
    parser.add_argument(
        "command",
        choices=("apply", "status", "verify"),
        help=(
            "apply aplica pendencias e provisiona identidades de banco; "
            "status lista o ledger; verify confere sem alterar nada."
        ),
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=120.0,
        help="Segundos aguardando o Postgres aceitar conexoes (padrao: 120).",
    )
    parser.add_argument(
        "--skip-roles",
        action="store_true",
        help="Aplica somente as migrations, sem provisionar identidades.",
    )
    options = parser.parse_args(argv)
    if options.wait_timeout < 0:
        print("--wait-timeout nao pode ser negativo.", file=sys.stderr)
        return 2

    try:
        if options.command == "apply":
            return asyncio.run(
                _command_apply(
                    wait_timeout=options.wait_timeout,
                    skip_roles=options.skip_roles,
                )
            )
        if options.command == "status":
            return asyncio.run(
                _command_status(wait_timeout=options.wait_timeout)
            )
        return asyncio.run(_command_verify(wait_timeout=options.wait_timeout))
    except SchemaMigrationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
