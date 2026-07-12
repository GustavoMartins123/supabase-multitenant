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

# O Studio e o OpenResty compartilham o mesmo bind mount de snippets, mas rodam
# com usuarios diferentes. A migracao de namespaces precisa renomear diretorios
# criados anteriormente pelo Studio; apenas montar o volume como rw nao concede
# essa permissao ao worker nobody.
SNIPPETS_DIR="${SNIPPETS_MANAGEMENT_FOLDER:-/app/snippets}"
if [ -d "$SNIPPETS_DIR" ]; then
    chown -R 65534:65534 "$SNIPPETS_DIR" 2>/dev/null || true

    # Diretorios precisam de write+execute para rename/delete e arquivos precisam
    # continuar gravaveis pelo Studio, independentemente do UID usado pela imagem.
    if find "$SNIPPETS_DIR" -type d -exec chmod 777 {} + \
        && find "$SNIPPETS_DIR" -type f -exec chmod 666 {} +; then
        echo "[entrypoint] snippets preparados para escrita compartilhada em $SNIPPETS_DIR"
    else
        echo "[entrypoint] WARN: não consegui preparar $SNIPPETS_DIR; a migração de snippets pode falhar"
    fi
else
    echo "[entrypoint] WARN: diretório de snippets ausente: $SNIPPETS_DIR"
fi

exec openresty -g "daemon off;"
