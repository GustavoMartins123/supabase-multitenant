#!/bin/bash

MMDB_PATH="seucaminho/traefik/geoip/GeoLite2-Country.mmdb"
BACKUP_DIR="seucaminho/traefik/logs_backup/geo"
BASE_URL="https://github.com/P3TERX/GeoLite.mmdb/releases/download"
FILE_NAME="GeoLite2-Country.mmdb"
GITHUB_API="https://api.github.com/repos/P3TERX/GeoLite.mmdb/releases/latest"

mkdir -p "$BACKUP_DIR"

DOWNLOADED=false
DOWNLOADED_URL=""

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Consultando API do GitHub para obter a última release..."
LATEST_RELEASE=$(curl -sL "$GITHUB_API")

if [[ -n "$LATEST_RELEASE" ]] && echo "$LATEST_RELEASE" | grep -q "tag_name"; then
    RELEASE_DATE=$(echo "$LATEST_RELEASE" | grep -oP '"tag_name":\s*"\K[^"]+')
    log "Última release encontrada: $RELEASE_DATE"
    
    URL="${BASE_URL}/${RELEASE_DATE}/${FILE_NAME}"
    log "Tentando download: $URL"
    
    HTTP_CODE=$(curl -sL -o /tmp/geolite_tmp.mmdb -w "%{http_code}" "$URL")
    
    if [[ "$HTTP_CODE" == "200" ]]; then
        if file /tmp/geolite_tmp.mmdb | grep -q "data\|MaxMind\|mmdb"; then
            DOWNLOADED=true
            DOWNLOADED_URL="$URL"
            log "Download OK: $RELEASE_DATE (HTTP $HTTP_CODE)"
        else
            log "Arquivo inválido, tentando método alternativo..."
            rm -f /tmp/geolite_tmp.mmdb
        fi
    else
        log "Falha no download (HTTP $HTTP_CODE), tentando método alternativo..."
        rm -f /tmp/geolite_tmp.mmdb
    fi
else
    log "Não foi possível consultar a API do GitHub, tentando método alternativo..."
fi

if [[ "$DOWNLOADED" == false ]]; then
    log "Usando método alternativo: tentativas sequenciais..."
    DAYS_AHEAD=7
    MAX_RETRIES=14
    TARGET_EPOCH=$(date -d "+${DAYS_AHEAD} days" +%s)
    
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
fi

if [[ "$DOWNLOADED" == true ]]; then
    MMDB_DIR=$(dirname "$MMDB_PATH")
    if [[ ! -d "$MMDB_DIR" ]]; then
        mkdir -p "$MMDB_DIR"
        log "Diretório criado: $MMDB_DIR"
    fi

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
