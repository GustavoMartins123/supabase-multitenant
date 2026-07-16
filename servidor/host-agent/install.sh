#!/usr/bin/env bash
# Instala o host-agent como servico systemd no host do servidor principal.
set -euo pipefail

die() { echo "❌ $*" >&2; exit 1; }
say() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVIDOR_DIR="$(dirname "$AGENT_DIR")"
UNIT_NAME="supabase-host-agent.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"

[[ "$(id -u)" -eq 0 ]] || die "Execute como root (systemd + docker)."
command -v docker >/dev/null || die "docker nao encontrado no host."
command -v bash >/dev/null || die "bash nao encontrado no host."
command -v jq >/dev/null || die "jq e requisito dos scripts de lifecycle."
command -v rsync >/dev/null || die "rsync e requisito do duplicate_project."
command -v openssl >/dev/null || die "openssl e requisito dos scripts."

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null || die "python3 nao encontrado."
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "python >= 3.10 e obrigatorio."

[[ -f "$SERVIDOR_DIR/.env" ]] || die "servidor/.env nao encontrado. Rode o setup antes."
grep -Eq '^HOST_AGENT_HMAC_SECRET=..+' "$SERVIDOR_DIR/.env" \
  || die "HOST_AGENT_HMAC_SECRET ausente em servidor/.env (rode o setup atualizado)."
if grep -Eq '^HOST_AGENT_HMAC_SECRET=pass$' "$SERVIDOR_DIR/.env"; then
  die "HOST_AGENT_HMAC_SECRET ainda e placeholder em servidor/.env."
fi

say "Criando virtualenv em $AGENT_DIR/.venv ..."
"$PYTHON_BIN" -m venv "$AGENT_DIR/.venv"
"$AGENT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$AGENT_DIR/.venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
ok "Dependencias instaladas."

say "Instalando unit systemd em $UNIT_PATH ..."
sed \
  -e "s|__SERVIDOR_DIR__|$SERVIDOR_DIR|g" \
  -e "s|__AGENT_DIR__|$AGENT_DIR|g" \
  "$AGENT_DIR/supabase-host-agent.service" > "$UNIT_PATH"
chmod 644 "$UNIT_PATH"

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME"
ok "Servico $UNIT_NAME instalado e iniciado."
say "Logs: journalctl -u $UNIT_NAME -f"
