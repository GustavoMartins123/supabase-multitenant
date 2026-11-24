#!/usr/bin/env bash
set -euo pipefail

HBA_PATH="${PG_HBA_OUTPUT_PATH:-/etc/postgresql/pg_hba.conf}"
HBA_DIR="$(dirname "$HBA_PATH")"
TMP_FILE="${HBA_PATH}.tmp.$$"

mkdir -p "$HBA_DIR"

valid_cidr() {
  case "$1" in
    0.0.0.0/0|::/0|::0/0|"") return 1 ;;
    */*) return 0 ;;
    *) return 1 ;;
  esac
}

append_unique_cidrs() {
  local cidr
  for cidr in "$@"; do
    cidr="$(printf '%s' "$cidr" | tr -d ' \t\r\n')"
    valid_cidr "$cidr" || continue
    if grep -Fxq "$cidr" "$TMP_DENY_CIDRS" 2>/dev/null; then
      continue
    fi
    if ! grep -Fxq "$cidr" "$TMP_CIDRS" 2>/dev/null; then
      printf '%s\n' "$cidr" >> "$TMP_CIDRS"
    fi
  done
}

append_unique_deny_cidrs() {
  local cidr
  for cidr in "$@"; do
    cidr="$(printf '%s' "$cidr" | tr -d ' \t\r\n')"
    valid_cidr "$cidr" || continue
    if ! grep -Fxq "$cidr" "$TMP_DENY_CIDRS" 2>/dev/null; then
      printf '%s\n' "$cidr" >> "$TMP_DENY_CIDRS"
    fi
  done
}

detect_proc_route_cidrs() {
  [[ -r /proc/net/route ]] || return 0
  awk '
    NR == 1 { next }
    $3 == "00000000" && $8 != "00000000" {
      dest = strtonum("0x" $2)
      mask = strtonum("0x" $8)
      a = and(dest, 255)
      b = and(rshift(dest, 8), 255)
      c = and(rshift(dest, 16), 255)
      d = and(rshift(dest, 24), 255)
      if (a == 127) next
      bits = 0
      m = mask
      while (m > 0) {
        bits += and(m, 1)
        m = rshift(m, 1)
      }
      if (bits > 0 && bits <= 32) {
        printf "%d.%d.%d.%d/%d\n", a, b, c, d, bits
      }
    }
  ' /proc/net/route 2>/dev/null || true
}

TMP_CIDRS="$(mktemp)"
TMP_DENY_CIDRS="$(mktemp)"
trap 'rm -f "$TMP_CIDRS" "$TMP_DENY_CIDRS" "$TMP_FILE"' EXIT

if [[ -n "${PG_HBA_DENY_CIDRS:-}" ]]; then
  IFS=',' read -r -a deny_cidrs <<< "$PG_HBA_DENY_CIDRS"
  append_unique_deny_cidrs "${deny_cidrs[@]}"
fi

if command -v ip >/dev/null 2>&1; then
  while IFS= read -r cidr; do
    append_unique_cidrs "$cidr"
  done < <(ip -4 route show proto kernel scope link 2>/dev/null | awk '{print $1}')
else
  while IFS= read -r cidr; do
    append_unique_cidrs "$cidr"
  done < <(detect_proc_route_cidrs)
fi

append_unique_cidrs "${SUPABASE_NETWORK_SUBNET:-}" "${FUNCTIONS_DB_SUBNET:-}"

if [[ -n "${PG_HBA_ALLOWED_CIDRS:-}" ]]; then
  IFS=',' read -r -a extra_cidrs <<< "$PG_HBA_ALLOWED_CIDRS"
  append_unique_cidrs "${extra_cidrs[@]}"
fi

{
  echo "# Generated at container startup by configure-pg-hba.sh (SEC-11)"
  echo "local   all             supabase_admin                          trust"
  echo "local   all             all                                     peer map=supabase_map"
  echo "host    all             all             127.0.0.1/32            scram-sha-256"
  echo "host    all             all             ::1/128                 scram-sha-256"
  while IFS= read -r cidr; do
    [[ -n "$cidr" ]] || continue
    printf 'host    all             all             %-23s reject\n' "$cidr"
  done < "$TMP_DENY_CIDRS"
  while IFS= read -r cidr; do
    [[ -n "$cidr" ]] || continue
    printf 'host    all             all             %-23s scram-sha-256\n' "$cidr"
  done < "$TMP_CIDRS"
  echo "host    all             all             0.0.0.0/0               reject"
  echo "host    all             all             ::/0                    reject"
} > "$TMP_FILE"

chmod 0640 "$TMP_FILE"
if [[ "$(id -u)" == "0" ]] && id postgres >/dev/null 2>&1; then
  chown postgres:postgres "$TMP_FILE"
fi
mv "$TMP_FILE" "$HBA_PATH"
