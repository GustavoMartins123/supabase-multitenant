#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_PROFILE="${1:-${DEPLOYMENT_PROFILE:-single-node}}"

run_systemctl() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

stop_studio() {
    cd "$ROOT_DIR/studio"
    docker compose down
}

case "$DEPLOYMENT_PROFILE" in
    single-node)
        SERVER_TOPOLOGY=single-node
        stop_studio
        ;;
    split-node-server)
        SERVER_TOPOLOGY=split-node
        ;;
    split-node-studio)
        stop_studio
        exit 0
        ;;
    *)
        echo "Perfil invalido: $DEPLOYMENT_PROFILE" >&2
        echo "Use single-node, split-node-server ou split-node-studio." >&2
        exit 1
        ;;
esac

if [ -f /etc/systemd/system/supabase-host-agent.service ]; then
    echo "Parando host-agent..."
    run_systemctl stop supabase-host-agent \
        || echo "Aviso: nao foi possivel parar supabase-host-agent." >&2
fi

cd "$ROOT_DIR/servidor"
API_OVERRIDE="docker-compose.${SERVER_TOPOLOGY}.yml"
API_COMPOSE=(docker compose -f docker-compose-api.yml -f "$API_OVERRIDE" --env-file .env)

echo "Parando projetos Supabase..."
shopt -s nullglob
for project_dir in projects/*/; do
    project_name="$(basename "$project_dir")"
    [ -f "$project_dir/docker-compose.yml" ] || continue

    docker compose -p "$project_name" \
        -f "$project_dir/docker-compose.yml" \
        --env-file .env \
        --env-file "$project_dir/.env" \
        down
done

echo "Parando Traefik..."
docker compose -f traefik/docker-compose.yml --env-file .env down

echo "Parando Projects API e servicos compartilhados..."
"${API_COMPOSE[@]}" down
docker compose -f docker-compose.yml --env-file .env down

echo "Perfil $DEPLOYMENT_PROFILE parado com sucesso."
