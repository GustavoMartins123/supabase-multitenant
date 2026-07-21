#!/usr/bin/env sh
set -e

# garante que o arquivo de opaque identifiers exista antes dos workers do nginx
if [ ! -f /config/ids.yml ]; then
    {
        echo '# yaml-language-server: $schema=https://www.authelia.com/schemas/v4.40/json-schema/export.identifiers.json'
        echo
        echo 'identifiers: []'
    } > /config/ids.yml
fi

AUTHELIA_CLI_SECRETS_DIR="/var/run/authelia-cli-secrets"
install -d -m 700 -o 65534 -g 65534 "$AUTHELIA_CLI_SECRETS_DIR"
for secret_name in JWT_SECRET STORAGE_ENCRYPTION_KEY; do
    source_path="/run/secrets/$secret_name"
    target_path="$AUTHELIA_CLI_SECRETS_DIR/$secret_name"
    if [ ! -s "$source_path" ]; then
        echo "[entrypoint] ERRO: secret do Authelia ausente: $secret_name" >&2
        exit 1
    fi
    install -m 400 -o 65534 -g 65534 "$source_path" "$target_path"
done

if [ ! -s /config/configuration.runtime.yml ]; then
    echo "[entrypoint] ERRO: configuration.runtime.yml ausente" >&2
    exit 1
fi
chmod 644 /config/configuration.runtime.yml

chown 65534:65534 /config 2>/dev/null || true
chmod 777 /config || true

for file in /config/users_database.yml /config/ids.yml /config/db.sqlite3; do
    [ -e "$file" ] || continue
    if chown 65534:65534 "$file" 2>/dev/null; then
        chmod 666 "$file"
        echo "[entrypoint] $(basename "$file") preparado para escrita pelos workers (mode 666)"
    else
        echo "[entrypoint] WARN: não consegui alterar owner de $(basename "$file"); volume pode estar RO"
        chmod 666 "$file" 2>/dev/null || true
    fi
done

for file in /config/db.sqlite3-shm /config/db.sqlite3-wal /config/db.sqlite3-journal; do
    [ -e "$file" ] || continue
    chown 65534:65534 "$file" 2>/dev/null || true
    chmod 666 "$file" 2>/dev/null || true
done

chmod 755 /config/ssl 2>/dev/null || true

SNIPPETS_DIR="${SNIPPETS_MANAGEMENT_FOLDER:-/app/snippets}"
if [ -d "$SNIPPETS_DIR" ]; then
    chown -R 65534:65534 "$SNIPPETS_DIR" 2>/dev/null || true

    if find "$SNIPPETS_DIR" -type d -exec chmod 777 {} + \
        && find "$SNIPPETS_DIR" -type f -exec chmod 666 {} +; then
        echo "[entrypoint] snippets preparados para escrita compartilhada em $SNIPPETS_DIR"
    else
        echo "[entrypoint] WARN: não consegui preparar $SNIPPETS_DIR; a migração de snippets pode falhar"
    fi
else
    echo "[entrypoint] WARN: diretório de snippets ausente: $SNIPPETS_DIR"
fi

PROFILE_PICTURES_DIR="/config/profile-pictures"
mkdir -p "$PROFILE_PICTURES_DIR"
chown -R 65534:65534 "$PROFILE_PICTURES_DIR" 2>/dev/null || true
find "$PROFILE_PICTURES_DIR" -type d -exec chmod 700 {} +
find "$PROFILE_PICTURES_DIR" -type f -exec chmod 600 {} +

exec openresty -g "daemon off;"
