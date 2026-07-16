#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_PROFILE="${1:-${DEPLOYMENT_PROFILE:-single-node}}"

start_studio() {
    echo "Iniciando Studio, Authelia e OpenResty..."
    cd "$ROOT_DIR/studio"
    docker compose up --build -d
    echo "Studio iniciado."
}

case "$DEPLOYMENT_PROFILE" in
    single-node)
        SERVER_TOPOLOGY=single-node
        ;;
    split-node-server)
        SERVER_TOPOLOGY=split-node
        ;;
    split-node-studio)
        start_studio
        exit 0
        ;;
    *)
        echo "Perfil invalido: $DEPLOYMENT_PROFILE" >&2
        echo "Use single-node, split-node-server ou split-node-studio." >&2
        exit 1
        ;;
esac

echo "Iniciando a base de dados e os servicos Supabase..."
cd "$ROOT_DIR/servidor"
API_OVERRIDE="docker-compose.${SERVER_TOPOLOGY}.yml"
API_COMPOSE=(docker compose -f docker-compose-api.yml -f "$API_OVERRIDE" --env-file .env)

docker compose -f docker-compose.yml --env-file .env up --build -d
"${API_COMPOSE[@]}" up --build -d

if [ -f /etc/systemd/system/supabase-host-agent.service ]; then
    echo "Iniciando host-agent..."
    systemctl start supabase-host-agent \
        || echo "Aviso: nao foi possivel iniciar supabase-host-agent (rode como root)." >&2
else
    echo "Aviso: host-agent nao instalado; lifecycle de projetos ficara indisponivel." >&2
    echo "       Instale com: sudo bash servidor/host-agent/install.sh" >&2
fi

echo "Aguardando o banco de dados ficar pronto..."
counter=0
until [ "$(docker inspect -f '{{.State.Health.Status}}' supabase-db)" = "healthy" ]; do
    if [ "$counter" -gt 24 ]; then
        echo "O banco de dados nao ficou saudavel a tempo." >&2
        exit 1
    fi
    printf "."
    sleep 5
    counter=$((counter + 1))
done

echo
echo "Aguardando Supavisor ficar pronto..."
counter=0
until docker exec supabase-pooler curl -sS -o /dev/null http://localhost:4000 2>/dev/null; do
    if [ "$counter" -gt 60 ]; then
        echo "O Supavisor nao respondeu a tempo." >&2
        exit 1
    fi
    printf "."
    sleep 2
    counter=$((counter + 1))
done

echo
echo "Iniciando Traefik com File Provider..."
docker compose -f traefik/docker-compose.yml --env-file .env up -d

echo "Iniciando projetos Supabase..."
shopt -s nullglob
for project_dir in projects/*/; do
    project_name="$(basename "$project_dir")"
    [ -f "$project_dir/docker-compose.yml" ] || continue

    echo "Iniciando projeto: $project_name"
    docker compose -p "$project_name" \
        -f "$project_dir/docker-compose.yml" \
        --env-file .env \
        --env-file "$project_dir/.env" \
        up --build -d
done

if [ "$DEPLOYMENT_PROFILE" = "single-node" ]; then
    start_studio
fi

echo "Perfil $DEPLOYMENT_PROFILE iniciado com sucesso."
