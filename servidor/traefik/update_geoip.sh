#!/bin/bash

MMDB_PATH="seucaminho/traefik/geoip/GeoLite2-Country.mmdb"
BACKUP_DIR="seucaminho/traefik/logs_backup/geo"
BASE_URL="https://github.com/P3TERX/GeoLite.mmdb/releases/download"
FILE_NAME="GeoLite2-Country.mmdb"
DAYS_AHEAD=7
MAX_RETRIES=14

mkdir -p "$BACKUP_DIR"

TARGET_EPOCH=$(date -d "+${DAYS_AHEAD} days" +%s)
DOWNLOADED=false
DOWNLOADED_URL=""

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

for ((i = 0; i <= MAX_RETRIES; i++)); do
    TRY_EPOCH=$(( TARGET_EPOCH - i * 86400 ))
    TRY_DATE=$(date -d "@${TRY_EPOCH}" +%Y.%m.%d)
    URL="${BASE_URL}/${TRY_DATE}/${FILE_NAME}"

    log "Tentando: $URL"

    HTTP_CODE=$(curl -sL -o /tmp/geolite_tmp.mmdb -w "%{http_code}" "$URL")

    if [[ "$HTTP_CODE" == "200" ]]; then
        if file /tmp/geolite_tmp.mmdb | grep -q "data\|MaxMind\|mmdb"; then
            DOWNLOADED=true
            DOWNLOADED_URL="$URL"
            log "Download OK: $TRY_DATE (HTTP $HTTP_CODE)"
            break
        else
            log "Arquivo inválido em $TRY_DATE, continuando..."
            rm -f /tmp/geolite_tmp.mmdb
        fi
    else
        log "Não encontrado em $TRY_DATE (HTTP $HTTP_CODE)"
        rm -f /tmp/geolite_tmp.mmdb
    fi
done

if [[ "$DOWNLOADED" == true ]]; then
    if [[ -f "$MMDB_PATH" ]]; then
        BACKUP_NAME="GeoLite2-Country_$(date '+%Y%m%d_%H%M%S').mmdb"
        cp "$MMDB_PATH" "$BACKUP_DIR/$BACKUP_NAME"
        log "Backup salvo: $BACKUP_DIR/$BACKUP_NAME"

        find "$BACKUP_DIR" -name "*.mmdb" -mtime +60 -delete
        log "Backups antigos (+60d) removidos"
    fi

    mv /tmp/geolite_tmp.mmdb "$MMDB_PATH"
    log "Arquivo atualizado com sucesso! Fonte: $DOWNLOADED_URL"
else
    log "Nenhuma versão nova encontrada após $MAX_RETRIES tentativas. Mantendo arquivo atual."
    rm -f /tmp/geolite_tmp.mmdb
    exit 0
fi
