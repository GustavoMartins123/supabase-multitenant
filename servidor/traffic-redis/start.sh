#!/bin/sh
set -eu
: "${ACCESS_RATE_REDIS_PASSWORD:?Missing traffic Redis password}"
case "$ACCESS_RATE_REDIS_PASSWORD" in *[!a-f0-9]*|'') exit 1;; esac
[ "${#ACCESS_RATE_REDIS_PASSWORD}" -eq 64 ] || exit 1
umask 077
printf 'bind 0.0.0.0\nprotected-mode yes\nrequirepass %s\ndir /data\nappendonly yes\nappendfsync always\nmaxmemory 256mb\nmaxmemory-policy noeviction\n' "$ACCESS_RATE_REDIS_PASSWORD" > /tmp/traffic.conf
chown redis:redis /tmp/traffic.conf
exec /usr/local/bin/docker-entrypoint.sh redis-server /tmp/traffic.conf
