#!/usr/bin/env sh
set -e

# ajusta permissões dentro do volume compartilhado: RW para nobody
if chown 65534:65534 /config/users_database.yml 2>/dev/null; then
    chmod 664 /config/users_database.yml
    echo "[entrypoint] users_database.yml agora pertence a 65534:65534 (mode 664)"
else
    echo "[entrypoint] WARN: não consegui alterar owner; volume pode estar RO"
fi

# garante X no diretório (acesso)
chmod 775 /config || true

exec openresty -g "daemon off;"
