#!/bin/sh
set -eu
umask 077

if [ ! -f /config/.desktop-initialized ]; then
    [ ! -s /seed/db.sqlite3 ] && [ ! -e /seed/.studio-bootstrap-consumed ] \
        || { echo 'Existing administrative data requires explicit migration into usersdb' >&2; exit 1; }
    for name in users_database.yml ids.yml db.sqlite3 notifications.txt .studio-directory-sequence; do
        [ -f "/seed/$name" ] || { echo "Missing setup seed: $name" >&2; exit 1; }
        cp "/seed/$name" "/config/$name"
        chown 65534:65534 "/config/$name"
        chmod 600 "/config/$name"
    done
    cp -R /seed-snippets/. /snippets/
    chown -R 65534:65534 /snippets
    touch /config/.desktop-initialized
fi

mkdir -p /config/ssl
for name in configuration.runtime.yml .studio-origin; do
    [ -s "/seed/$name" ] || { echo "Missing runtime configuration: $name" >&2; exit 1; }
    install -m 644 "/seed/$name" "/config/$name"
done
for name in ca.pem server.pem; do
    install -m 644 "/seed/ssl/$name" "/config/ssl/$name"
done
install -m 600 /seed/ssl/server.key /config/ssl/server.key
