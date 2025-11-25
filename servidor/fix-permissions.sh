#!/bin/bash
set -e

POSTGRES_UID=105
POSTGRES_GID=106

echo "  → Verificando e criando diretórios se necessário..."

if [ ! -d "volumes/db/data" ]; then
    echo "    • Criando volumes/db/data..."
    mkdir -p volumes/db/data
fi

if [ ! -d "volumes/db/wal_archives" ]; then
    echo "    • Criando volumes/db/wal_archives..."
    mkdir -p volumes/db/wal_archives
fi

echo "  → Ajustando permissões de volumes/db/data..."
sudo chown -R ${POSTGRES_UID}:${POSTGRES_GID} volumes/db/data
sudo chmod -R 700 volumes/db/data

echo "  → Ajustando permissões de volumes/db/wal_archives..."
sudo chown -R ${POSTGRES_UID}:${POSTGRES_GID} volumes/db/wal_archives
sudo chmod -R 755 volumes/db/wal_archives

echo "  ✓ Permissões configuradas com sucesso!"