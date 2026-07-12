#!/bin/bash

set -e

echo "▶️  Iniciando a base de dados e serviços Supabase..."
cd servidor
docker compose -f docker-compose.yml --env-file .env up --build -d
docker compose -f docker-compose-api.yml --env-file .env up --build -d
echo "✅ Serviços Supabase iniciados. Aguardando o banco de dados ficar pronto..."


COUNTER=0
until [ "`docker inspect -f {{.State.Health.Status}} supabase-db`" == "healthy" ]; do
    if [ $COUNTER -gt 24 ]; then
        echo "❌ ERRO: O banco de dados não ficou saudável a tempo. Verifique os logs com 'docker-compose logs db'."
        exit 1
    fi
    printf "."
    sleep 5
    let COUNTER=COUNTER+1
done

echo -e "\n✅ Banco de dados está pronto e aceitando conexões."

echo "⏳ Aguardando Supavisor ficar pronto..."
COUNTER=0
until docker exec supabase-pooler curl -sS -o /dev/null http://localhost:4000 2>/dev/null; do
    if [ $COUNTER -gt 60 ]; then
        echo "❌ ERRO: O Supavisor não respondeu a tempo. Verifique os logs com 'docker logs supabase-pooler'."
        exit 1
    fi
    printf "."
    sleep 2
    let COUNTER=COUNTER+1
done

echo -e "\n✅ Supavisor está pronto."

echo "▶️  Iniciando o Traefik..."

docker compose -f traefik/docker-compose.yml --env-file .env up -d
echo "✅ Traefik iniciado."

echo "▶️  Iniciando projetos Supabase..."
for project_dir in projects/*/; do
    project_name=$(basename "$project_dir")
    
    if [ ! -d "$project_dir" ] || [ "$project_name" == ".gitkeep" ]; then
        continue
    fi
    
    if [ -f "$project_dir/docker-compose.yml" ]; then
        echo "  ▶️  Iniciando projeto: $project_name"
        docker compose -p "$project_name" \
            -f "$project_dir/docker-compose.yml" \
            --env-file .env \
            --env-file "$project_dir/.env" \
            up --build -d
        echo "  ✅ Projeto $project_name iniciado."
    else
        echo "  ⚠️  Projeto $project_name não tem docker-compose.yml, pulando..."
    fi
done
echo "✅ Todos os projetos iniciados."

cd .. 

echo "▶️  Iniciando o Studio..."
cd studio
docker compose up --build -d
echo "✅ Studio iniciado."
cd .. 