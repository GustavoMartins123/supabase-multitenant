#!/usr/bin/env bash

tenant_reader_error() { echo "Erro: $*" >&2; exit 1; }

psql_exec_stdin() {
    local db="$1"
    shift
    docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$db" "$@"
}

provision_platform_reader_role() {
    [ -n "${PLATFORM_READER_DB_PASSWORD:-}" ] \
        || tenant_reader_error "PLATFORM_READER_DB_PASSWORD ausente no .env raiz; gere com: openssl rand -base64 48 | tr '/+' '_-' | tr -d '=\n'"
    [[ "$PLATFORM_READER_DB_PASSWORD" =~ ^[A-Za-z0-9_-]{32,128}$ ]] \
        || tenant_reader_error "PLATFORM_READER_DB_PASSWORD fora do formato esperado"

    psql_exec_stdin postgres <<SQL \
        || tenant_reader_error "falha ao provisionar a role platform_reader"
\set reader_pwd '${PLATFORM_READER_DB_PASSWORD}'
SELECT format(
    'CREATE ROLE platform_reader LOGIN PASSWORD %L CONNECTION LIMIT 20',
    :'reader_pwd'
) WHERE NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = 'platform_reader'
) \gexec
ALTER ROLE platform_reader SET statement_timeout = '5s';
ALTER ROLE platform_reader SET idle_in_transaction_session_timeout = '15s';
SQL
}

wait_for_auth_sessions() {
    local db="$1" timeout="${2:-60}" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        if docker exec supabase-db psql -U supabase_admin -d "$db" -tAc \
            "SELECT to_regclass('auth.sessions') IS NOT NULL;" 2>/dev/null \
            | grep -qx t; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

grant_platform_reader_on_tenant() {
    local db="$1"
    wait_for_auth_sessions "$db" "${PLATFORM_READER_WAIT_TIMEOUT:-60}" \
        || tenant_reader_error "auth.sessions nao apareceu em $db; o GoTrue do projeto nao migrou"

    psql_exec_stdin "$db" <<SQL \
        || tenant_reader_error "falha ao conceder permissoes de leitura em $db"
REVOKE ALL ON SCHEMA auth FROM platform_reader;
GRANT USAGE ON SCHEMA auth TO platform_reader;
GRANT SELECT ON auth.users, auth.sessions TO platform_reader;
GRANT CONNECT ON DATABASE ${db} TO platform_reader;
SQL
}

provision_platform_reader() {
    local db="$1"
    provision_platform_reader_role
    grant_platform_reader_on_tenant "$db"
}
