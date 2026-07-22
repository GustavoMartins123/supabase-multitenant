#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_PROFILE="${1:-${DEPLOYMENT_PROFILE:-single-node}}"
HOST_AGENT_UNIT="/etc/systemd/system/supabase-host-agent.service"
HOST_AGENT_DIR="$ROOT_DIR/servidor/host-agent"
HOST_AGENT_PYTHON="$HOST_AGENT_DIR/.venv/bin/python"

die() {
    echo "Erro: $*" >&2
    exit 1
}

run_systemctl() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

require_host_agent_installation() {
    if [ ! -f "$HOST_AGENT_UNIT" ] || [ ! -x "$HOST_AGENT_PYTHON" ]; then
        die "host-agent ausente ou incompleto. Instale com: sudo bash '$HOST_AGENT_DIR/install.sh'"
    fi
    if ! grep -Fq "$HOST_AGENT_PYTHON" "$HOST_AGENT_UNIT" || \
       ! grep -Fq "$ROOT_DIR/servidor" "$HOST_AGENT_UNIT"; then
        die "host-agent aponta para outra copia do repositorio. Reinstale com: sudo bash '$HOST_AGENT_DIR/install.sh'"
    fi
    if grep -Fxq 'User=root' "$HOST_AGENT_UNIT" || \
       grep -Fq '__HOST_AGENT_USER__' "$HOST_AGENT_UNIT"; then
        die "host-agent ainda usa o contrato antigo de root. Reinstale com: sudo bash '$HOST_AGENT_DIR/install.sh'"
    fi
}

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

require_host_agent_installation

echo "Iniciando a base de dados e os servicos Supabase..."
cd "$ROOT_DIR/servidor"
API_OVERRIDE="docker-compose.${SERVER_TOPOLOGY}.yml"
API_COMPOSE=(docker compose -f docker-compose-api.yml -f "$API_OVERRIDE" --env-file .env)

docker compose -f docker-compose.yml --env-file .env up --build -d
"${API_COMPOSE[@]}" up --build -d

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
echo "Aguardando Projects API ficar pronta..."
counter=0
until [ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' projects-api 2>/dev/null)" = "healthy" ]; do
    if [ "$counter" -gt 36 ]; then
        die "Projects API nao ficou saudavel a tempo."
    fi
    printf "."
    sleep 5
    counter=$((counter + 1))
done

echo
echo "Validando acesso do host-agent ao control plane..."
if ! (
    cd "$HOST_AGENT_DIR"
    "$HOST_AGENT_PYTHON" -m hostagent \
        --root "$ROOT_DIR/servidor" \
        --check-schema
); then
    die "host-agent nao consegue acessar o banco/schema com o servidor/.env atual. Reinstale com: sudo bash '$HOST_AGENT_DIR/install.sh'"
fi

echo "Reiniciando host-agent para carregar credenciais e chaves atuais..."
run_systemctl restart supabase-host-agent \
    || die "nao foi possivel reiniciar supabase-host-agent."
systemctl is-active --quiet supabase-host-agent \
    || die "supabase-host-agent nao ficou ativo apos o restart. Consulte: journalctl -u supabase-host-agent -n 100"

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
