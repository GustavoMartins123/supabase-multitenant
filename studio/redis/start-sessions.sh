#!/bin/sh
set -eu
password=$(cat /run/secrets/REDIS_SESSION_PASSWORD)
case "$password" in ''|*[!A-Za-z0-9_-]*) echo 'Invalid Redis session password' >&2; exit 1;; esac
[ "${#password}" -ge 64 ] || { echo 'Redis session password too short' >&2; exit 1; }
umask 077
printf 'bind 0.0.0.0\nprotected-mode yes\nrequirepass %s\ndir /data\nappendonly yes\nappendfsync everysec\nmaxmemory 256mb\nmaxmemory-policy noeviction\n' "$password" > /tmp/sessions.conf
chown redis:redis /tmp/sessions.conf
exec /usr/local/bin/docker-entrypoint.sh redis-server /tmp/sessions.conf
