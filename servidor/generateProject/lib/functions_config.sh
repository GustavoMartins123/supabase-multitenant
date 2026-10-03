#!/usr/bin/env bash
# Hold locks until script exit, including rollback. Startup sync takes the
# exclusive global lock; lifecycle uses shared global + sorted tenant locks.
declare -A FUNCTIONS_TENANT_LOCK_FDS=()
FUNCTIONS_CONFIG_LOCKED=0
declare -A FUNCTIONS_WITHDRAWN=()

functions_config_lock() {
  local ref fd locks="$PROJECT_ROOT/.functions-locks"
  umask 077
  command -v flock >/dev/null || { echo 'Functions requires flock' >&2; return 1; }
  command -v python3 >/dev/null || { echo 'Functions requires python3' >&2; return 1; }
  [[ ! -L "$locks" ]] || { echo 'Functions lock symlink refused' >&2; return 1; }
  mkdir -p "$locks"
  chmod 700 "$locks"
  [[ ! -L "$locks/global" ]] || return 1
  exec {FUNCTIONS_GLOBAL_LOCK_FD}>"$locks/global"
  flock -s "$FUNCTIONS_GLOBAL_LOCK_FD"
  while IFS= read -r ref; do
    [[ "$ref" =~ ^[a-z_][a-z0-9_]{2,39}$ && ! -L "$locks/$ref" ]] || return 1
    exec {fd}>"$locks/$ref"
    flock -x "$fd"
    FUNCTIONS_TENANT_LOCK_FDS[$ref]="$fd"
  done < <(printf '%s\n' "$@" | LC_ALL=C sort -u)
  FUNCTIONS_CONFIG_LOCKED=1
}

functions_config_action() {
  local action="$1" ref="$2"
  [[ "$FUNCTIONS_CONFIG_LOCKED" == 1 && -n "${FUNCTIONS_TENANT_LOCK_FDS[$ref]:-}" ]] || {
    echo 'Functions lifecycle lock missing' >&2; return 1;
  }
  python3 "$SCRIPT_DIR/functions_config.py" --root "$PROJECT_ROOT" \
    --lock-fd "$FUNCTIONS_GLOBAL_LOCK_FD" \
    --tenant-lock-fd "${FUNCTIONS_TENANT_LOCK_FDS[$ref]}" "$action" "$ref"
}

functions_config_withdraw() {
  FUNCTIONS_WITHDRAWN[$1]=1
  functions_config_action withdraw "$1"
}
functions_config_publish() { functions_config_action publish "$1"; }
