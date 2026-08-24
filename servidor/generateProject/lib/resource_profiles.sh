#!/usr/bin/env bash
# Resolve o perfil de recursos do .env raiz e grava os limites concretos no
# .env do projeto (PROJECT_MEM_LIMIT, PROJECT_CPUS, PROJECT_PIDS_LIMIT).

# Uso: apply_project_resource_limits <root_env> <project_env> [profile_override]
# O terceiro argumento (opcional) sobrepoe o perfil do .env raiz — usado
# quando o projeto tem perfil proprio escolhido na criacao/edicao.

resource_profiles_error() {
    echo "Erro: $*" >&2
    exit 1
}

resource_env_value() {
    sed -n "s/^$1=//p" "$2" | head -1 | tr -d '"'"'"''
}

apply_project_resource_limits() {
    local root_env="$1" project_env="$2" profile_override="${3:-}"
    [ -f "$root_env" ] || resource_profiles_error ".env raiz ausente: $root_env"
    [ -f "$project_env" ] || resource_profiles_error ".env do projeto ausente: $project_env"

    local profile upper mem cpus pids key
    if [ -n "$profile_override" ]; then
        profile="$profile_override"
    else
        profile="$(resource_env_value PROJECT_RESOURCE_PROFILE "$root_env")"
        profile="${profile:-medium}"
    fi
    case "$profile" in
        small|medium|large) ;;
        *) resource_profiles_error "PROJECT_RESOURCE_PROFILE invalido: $profile (use small, medium ou large)" ;;
    esac
    upper="$(printf '%s' "$profile" | tr '[:lower:]' '[:upper:]')"

    mem="$(resource_env_value "PROJECT_RES_${upper}_MEMORY" "$root_env")"
    cpus="$(resource_env_value "PROJECT_RES_${upper}_CPUS" "$root_env")"
    pids="$(resource_env_value "PROJECT_RES_${upper}_PIDS" "$root_env")"
    for pair in "PROJECT_RES_${upper}_MEMORY:$mem" \
        "PROJECT_RES_${upper}_CPUS:$cpus" \
        "PROJECT_RES_${upper}_PIDS:$pids"; do
        key="${pair%%:*}"
        [ -n "${pair#*:}" ] || resource_profiles_error "$key ausente no .env raiz; atualize a partir do .env.example"
    done

    local name value temporary
    temporary="$(mktemp "${project_env}.limits.XXXXXX")"
    {
        grep -vE '^PROJECT_(MEM_LIMIT|CPUS|PIDS_LIMIT)=' "$project_env" || true
        printf 'PROJECT_MEM_LIMIT=%s\n' "$mem"
        printf 'PROJECT_CPUS=%s\n' "$cpus"
        printf 'PROJECT_PIDS_LIMIT=%s\n' "$pids"
    } > "$temporary"
    # Preserva dono/permissões do arquivo original (600).
    cat "$temporary" > "$project_env"
    rm -f "$temporary"
}
