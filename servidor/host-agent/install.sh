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
  local servidor_dir="$1" agent_dir="$2" service_user="$3" destination="$4"
  local servidor_value agent_value service_user_replacement
  local servidor_replacement agent_replacement

  [[ "$servidor_dir" != *$'\n'* && "$servidor_dir" != *$'\r'* ]] \
    || die "Caminho do servidor contem quebra de linha."
  [[ "$agent_dir" != *$'\n'* && "$agent_dir" != *$'\r'* ]] \
    || die "Caminho do host-agent contem quebra de linha."
  [[ "$service_user" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] \
    || die "Usuario do host-agent invalido: $service_user"

  servidor_value="$(escape_systemd_value "$servidor_dir")"
  agent_value="$(escape_systemd_value "$agent_dir")"
  servidor_replacement="$(escape_sed_replacement "$servidor_value")"
  agent_replacement="$(escape_sed_replacement "$agent_value")"
  service_user_replacement="$(escape_sed_replacement "$service_user")"

  sed \
    -e "s|__SERVIDOR_DIR__|$servidor_replacement|g" \
    -e "s|__AGENT_DIR__|$agent_replacement|g" \
    -e "s|__HOST_AGENT_USER__|$service_user_replacement|g" \
    "$AGENT_DIR/supabase-host-agent.service" > "$destination"
}

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVIDOR_DIR="$(dirname "$AGENT_DIR")"
UNIT_NAME="supabase-host-agent.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
SERVICE_USER=""
SERVICE_GROUP=""

resolve_service_user() {
  local candidate="${HOST_AGENT_USER:-}"
  if [[ -z "$candidate" && -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    candidate="$SUDO_USER"
  fi
  if [[ -z "$candidate" ]]; then
    candidate="$(stat -c '%U' "$SERVIDOR_DIR/.env")"
  fi
  [[ -n "$candidate" && "$candidate" != "root" ]] \
    || die "Nao foi possivel detectar o usuario operador. Use: sudo HOST_AGENT_USER=<usuario> bash '$AGENT_DIR/install.sh'"
  id "$candidate" >/dev/null 2>&1 \
    || die "Usuario do host-agent nao existe: $candidate"
  printf '%s' "$candidate"
}

run_as_service_user() {
  runuser -u "$SERVICE_USER" -- "$@"
}

migrate_runtime_ownership() {
  local runtime_dir
  say "Ajustando arquivos de lifecycle para $SERVICE_USER:$SERVICE_GROUP ..."
  for runtime_dir in "$SERVIDOR_DIR/projects" "$SERVIDOR_DIR/backups"; do
    [[ -e "$runtime_dir" ]] || continue
    find "$runtime_dir" -xdev -uid 0 \
      -exec chown "$SERVICE_USER:$SERVICE_GROUP" {} +
  done
  find "$SERVIDOR_DIR/projects" -mindepth 2 -maxdepth 2 -type f -name .env \
    -exec chmod 600 {} +
  ok "Ownership do lifecycle alinhado ao usuario do host-agent."
}

main() {
  [[ "$(id -u)" -eq 0 ]] || die "Execute como root (systemd + docker)."
  command -v docker >/dev/null || die "docker nao encontrado no host."
  command -v bash >/dev/null || die "bash nao encontrado no host."
  command -v jq >/dev/null || die "jq e requisito dos scripts de lifecycle."
  command -v rsync >/dev/null || die "rsync e requisito do duplicate_project."
  command -v openssl >/dev/null || die "openssl e requisito dos scripts."
  command -v runuser >/dev/null || die "runuser e requisito para executar o host-agent sem root."
  command -v find >/dev/null || die "find e requisito para migrar as permissoes do lifecycle."

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

  SERVICE_USER="$(resolve_service_user)"
  SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
  run_as_service_user test -r "$SERVIDOR_DIR/.env" \
    || die "O usuario $SERVICE_USER nao consegue ler servidor/.env. Rode o setup como esse usuario."
  run_as_service_user docker info >/dev/null 2>&1 \
    || die "O usuario $SERVICE_USER nao consegue acessar o Docker. Adicione-o ao grupo docker e abra uma nova sessao."
  ok "Host-agent sera executado como $SERVICE_USER:$SERVICE_GROUP."

  say "Criando virtualenv em $AGENT_DIR/.venv ..."
  "$python_bin" -m venv "$AGENT_DIR/.venv"
  "$AGENT_DIR/.venv/bin/pip" install --quiet --upgrade pip
  "$AGENT_DIR/.venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
  ok "Dependencias instaladas."

  if systemctl is-active --quiet "$UNIT_NAME"; then
    say "Parando a unit antiga antes de migrar o ownership ..."
    systemctl stop "$UNIT_NAME"
  fi
  migrate_runtime_ownership

  say "Instalando unit systemd em $UNIT_PATH ..."
  render_unit "$SERVIDOR_DIR" "$AGENT_DIR" "$SERVICE_USER" "$UNIT_PATH"
  chmod 644 "$UNIT_PATH"

  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
  ok "Servico $UNIT_NAME instalado e habilitado."
  say "O start.sh iniciara banco/API e depois ativara o host-agent."
  say "Em reinicializacoes, o ExecStartPre aguardara o schema antes de iniciar o worker."
  say "Logs: journalctl -u $UNIT_NAME -f"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
