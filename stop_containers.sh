#!/bin/bash

set -e

echo "⏹️  Parando o Studio..."
cd studio
docker compose down
echo "✅ Studio parado."
cd ..

echo "⏹️  Parando projetos Supabase..."
cd servidor
for project_dir in projects/*/; do
    project_name=$(basename "$project_dir")
    
    if [ ! -d "$project_dir" ] || [ "$project_name" == ".gitkeep" ]; then
        continue
    fi
    
    if [ -f "$project_dir/docker-compose.yml" ]; then
        echo "  ⏹️  Parando projeto: $project_name"
        docker compose -p "$project_name" \
            -f "$project_dir/docker-compose.yml" \
            --env-file .env \
            --env-file "$project_dir/.env" \
            down
        echo "  ✅ Projeto $project_name parado."
    else
        echo "  ⚠️  Projeto $project_name não tem docker-compose.yml, pulando..."
    fi
done
echo "✅ Todos os projetos parados."

echo "⏹️  Parando o Traefik..."
docker compose -f traefik/docker-compose.yml down
echo "✅ Traefik parado."

echo "⏹️  Parando a base de dados e serviços Supabase..."
docker compose -f docker-compose-api.yml --env-file .env down
docker compose -f docker-compose.yml --env-file .env down
echo "✅ Serviços Supabase parados."

cd ..

echo "✅ Todos os serviços foram parados com sucesso!"
