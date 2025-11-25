#!/bin/bash
set -e

echo "🔧 Corrigindo permissões dos volumes..."
cd servidor
bash fix-permissions.sh
echo "✅ Permissões corrigidas."

echo "▶️  Iniciando a base de dados e serviços Supabase..."
docker compose -f docker-compose.yml --env-file .env --env-file secrets/.env up --build -d
echo "✅ Serviços Supabase iniciados. Aguardando o banco de dados ficar pronto..."

echo "▶️  Iniciando a api do Studio..."
docker compose -f docker-compose-api.yml --env-file secrets/.env --env-file .env up --build -d
echo "✅ Api do Studio iniciado."

COUNTER=0
until [ "$(docker inspect -f {{.State.Health.Status}} supabase-db)" == "healthy" ]; do
    if [ $COUNTER -gt 24 ]; then
        echo "❌ ERRO: O banco de dados não ficou saudável a tempo. Verifique os logs com 'docker-compose logs db'."
        exit 1
    fi
    printf "."
    sleep 5
    let COUNTER=COUNTER+1
done

echo -e "\n✅ Banco de dados está pronto e aceitando conexões."

echo "▶️  Iniciando o Traefik..."
docker compose -f traefik/docker-compose.yml up -d
echo "✅ Traefik iniciado."

echo "▶️  Iniciando o Studio..."
cd ../studio
docker compose up --build -d
echo "✅ Studio iniciado."

cd ..