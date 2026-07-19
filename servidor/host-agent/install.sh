#!/usr/bin/env bash
# Instala o host-agent como servico systemd no host do servidor principal.
set -euo pipefail

die() { echo "❌ $*" >&2; exit 1; }
say() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

escape_systemd_value() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//%/%%}"
  printf '%s' "$value"
}

escape_sed_replacement() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//&/\\&}"
  value="${value//|/\\|}"
  printf '%s' "$value"
}

render_unit() {
  local servidor_dir="$1" agent_dir="$2" destination="$3"
  local servidor_value agent_value
  local servidor_replacement agent_replacement

  [[ "$servidor_dir" != *$'\n'* && "$servidor_dir" != *$'\r'* ]] \
    || die "Caminho do servidor contem quebra de linha."
  [[ "$agent_dir" != *$'\n'* && "$agent_dir" != *$'\r'* ]] \
    || die "Caminho do host-agent contem quebra de linha."

  servidor_value="$(escape_systemd_value "$servidor_dir")"
  agent_value="$(escape_systemd_value "$agent_dir")"
  servidor_replacement="$(escape_sed_replacement "$servidor_value")"
  agent_replacement="$(escape_sed_replacement "$agent_value")"

  sed \
    -e "s|__SERVIDOR_DIR__|$servidor_replacement|g" \
    -e "s|__AGENT_DIR__|$agent_replacement|g" \
    "$AGENT_DIR/supabase-host-agent.service" > "$destination"
}

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVIDOR_DIR="$(dirname "$AGENT_DIR")"
UNIT_NAME="supabase-host-agent.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"

main() {
  [[ "$(id -u)" -eq 0 ]] || die "Execute como root (systemd + docker)."
  command -v docker >/dev/null || die "docker nao encontrado no host."
  command -v bash >/dev/null || die "bash nao encontrado no host."
  command -v jq >/dev/null || die "jq e requisito dos scripts de lifecycle."
  command -v rsync >/dev/null || die "rsync e requisito do duplicate_project."
  command -v openssl >/dev/null || die "openssl e requisito dos scripts."

  local python_bin="${PYTHON_BIN:-python3}"
  command -v "$python_bin" >/dev/null || die "python3 nao encontrado."
  "$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "python >= 3.10 e obrigatorio."

  [[ -f "$SERVIDOR_DIR/.env" ]] || die "servidor/.env nao encontrado. Rode o setup antes."
  grep -Eq '^HOST_AGENT_HMAC_SECRET=..+' "$SERVIDOR_DIR/.env" \
    || die "HOST_AGENT_HMAC_SECRET ausente em servidor/.env (rode o setup atualizado)."
  if grep -Eq '^HOST_AGENT_HMAC_SECRET=pass$' "$SERVIDOR_DIR/.env"; then
    die "HOST_AGENT_HMAC_SECRET ainda e placeholder em servidor/.env."
  fi

  say "Criando virtualenv em $AGENT_DIR/.venv ..."
  "$python_bin" -m venv "$AGENT_DIR/.venv"
  "$AGENT_DIR/.venv/bin/pip" install --quiet --upgrade pip
  "$AGENT_DIR/.venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
  ok "Dependencias instaladas."

  say "Instalando unit systemd em $UNIT_PATH ..."
  render_unit "$SERVIDOR_DIR" "$AGENT_DIR" "$UNIT_PATH"
  chmod 644 "$UNIT_PATH"

  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
  local schema_wait_timeout="${HOST_AGENT_INSTALL_SCHEMA_WAIT_TIMEOUT:-15}"
  say "Aguardando o schema do host-agent por ate ${schema_wait_timeout}s ..."
  if "$AGENT_DIR/.venv/bin/python" -m hostagent \
      --root "$SERVIDOR_DIR" \
      --wait-for-schema \
      --schema-timeout "$schema_wait_timeout"; then
    systemctl restart "$UNIT_NAME"
    ok "Servico $UNIT_NAME instalado e iniciado."
  else
    local schema_check_status=$?
    if [[ "$schema_check_status" -ne 3 ]]; then
      die "Nao foi possivel validar a configuracao/schema do host-agent."
    fi
    ok "Servico $UNIT_NAME instalado e habilitado."
    say "A Projects API ainda nao publicou o schema; o servico nao foi iniciado."
    say "Ao rodar start.sh, o ExecStartPre aguardara o schema antes de iniciar o agent."
  fi
  say "Logs: journalctl -u $UNIT_NAME -f"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
