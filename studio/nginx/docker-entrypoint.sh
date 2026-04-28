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

# ajusta permissões dentro do volume compartilhado: RW para nobody
# SQLite tambem precisa escrever no diretorio para journal/WAL.
chown 65534:65534 /config 2>/dev/null || true

for file in /config/users_database.yml /config/ids.yml /config/db.sqlite3; do
    [ -e "$file" ] || continue
    if chown 65534:65534 "$file" 2>/dev/null; then
        chmod 664 "$file"
        echo "[entrypoint] $(basename "$file") agora pertence a 65534:65534 (mode 664)"
    else
        echo "[entrypoint] WARN: não consegui alterar owner de $(basename "$file"); volume pode estar RO"
    fi
done

# garante X no diretório (acesso)
chmod 775 /config || true

exec openresty -g "daemon off;"
