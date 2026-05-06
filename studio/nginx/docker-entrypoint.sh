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

# Ajusta permissoes dentro do volume compartilhado.
#
# Em alguns hosts/bind mounts o chown retorna sucesso, mas o owner continua
# root:root. Os workers do OpenResty rodam como nobody, entao eles precisam de
# permissao de escrita efetiva para gerar identifiers do Authelia e gravar
# ids.yml. SQLite tambem precisa escrever no diretorio para journal/WAL.
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

exec openresty -g "daemon off;"
