#!/usr/bin/env bash
# Sobe (ou derruba) um Postgres descartavel para os testes de autorizacao.
#
#   bash tools/test_postgres.sh start   # imprime a DSN
#   bash tools/test_postgres.sh stop
#
# Os binarios sao procurados no PATH e nos locais usuais de instalacao. Se
# estiverem em outro lugar (por exemplo um zip portatil), aponte PG_BIN:
#
#   PG_BIN=/c/postgresql-15-portatil/pgsql/bin bash tools/test_postgres.sh start
set -u

PG_PORT="${PG_PORT:-55432}"
PG_DATA="${PG_DATA:-${TMPDIR:-/tmp}/supabase-multitenant-testpg/data}"
PG_LOG="$(dirname "$PG_DATA")/postgres.log"

die() { echo "erro: $*" >&2; exit 1; }

has_initdb() { [ -x "$1/initdb" ] || [ -x "$1/initdb.exe" ]; }

discover_pg_bin() {
    if [ -n "${PG_BIN:-}" ]; then
        has_initdb "$PG_BIN" || die "initdb nao encontrado em PG_BIN=$PG_BIN"
        echo "$PG_BIN"
        return
    fi

    local found
    found="$(command -v initdb 2>/dev/null)" && { dirname "$found"; return; }

    # Locais usuais: instalacao Windows, zip portatil, gerenciadores Unix.
    local candidate
    for candidate in \
        "/c/Program Files/PostgreSQL"/*/bin \
        "/c/PostgreSQL"/*/bin \
        /c/postgresql-*/pgsql/bin \
        /usr/lib/postgresql/*/bin \
        /usr/local/opt/postgresql*/bin \
        /opt/homebrew/opt/postgresql*/bin
    do
        has_initdb "$candidate" && { echo "$candidate"; return; }
    done

    die "binarios do Postgres nao encontrados; instale, ou defina PG_BIN=/caminho/para/bin"
}

PG_BIN="$(discover_pg_bin)" || exit 1

case "${1:-start}" in
  start)
    if [ ! -d "$PG_DATA" ]; then
      mkdir -p "$(dirname "$PG_DATA")"
      # trust: instancia efemera em loopback, sem dados reais.
      "$PG_BIN/initdb" -D "$PG_DATA" -U postgres --auth=trust \
        --encoding=UTF8 --no-locale >/dev/null || die "initdb falhou"
    fi
    "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" \
      -o "-p $PG_PORT -c listen_addresses=127.0.0.1" -w start \
      || { [ -f "$PG_LOG" ] && tail -20 "$PG_LOG" >&2; die "pg_ctl start falhou"; }
    echo "Postgres de teste no ar (binarios: $PG_BIN, porta $PG_PORT)"
    echo "CONTROL_PLANE_TEST_DSN=postgresql://postgres@127.0.0.1:$PG_PORT/postgres"
    ;;
  stop)
    if [ -d "$PG_DATA" ]; then
      "$PG_BIN/pg_ctl" -D "$PG_DATA" -m immediate -w stop >/dev/null 2>&1
      rm -rf "$(dirname "$PG_DATA")"
      echo "Postgres de teste derrubado e diretorio removido"
    else
      echo "nada para derrubar"
    fi
    ;;
  status)
    "$PG_BIN/pg_ctl" -D "$PG_DATA" status
    ;;
  *)
    die "uso: $0 {start|stop|status}"
    ;;
esac
