#!/usr/bin/env bash

start_all_projects() {
    local projects_root="${1:-}"
    local server_env="${2:-}"
    [[ -n "$projects_root" && -n "$server_env" ]] \
        || { echo "Uso: start_all_projects <projects_root> <server_env>" >&2; return 2; }
    local failed_projects=()
    local project_dir project_name
    shopt -s nullglob
    for project_dir in "$projects_root"/*/; do
        project_name="$(basename "$project_dir")"
        [ -f "$project_dir/docker-compose.yml" ] || continue

        echo "Iniciando projeto: $project_name"
        if docker compose -p "$project_name" \
            -f "$project_dir/docker-compose.yml" \
            --env-file "$server_env" \
            --env-file "$project_dir/.env" \
            up --build -d; then
            echo "Projeto iniciado: $project_name"
        else
            echo "AVISO: falha ao iniciar o projeto $project_name; seguindo para os demais." >&2
            failed_projects+=("$project_name")
        fi
    done
    if [ "${#failed_projects[@]}" -gt 0 ]; then
        echo "Projetos com falha na inicializacao: ${failed_projects[*]}." >&2
        return 1
    fi
    return 0
}
