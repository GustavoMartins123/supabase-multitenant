#!/usr/bin/env bash
#
# O rateio usa pesos fixos por dimensao e a sobra vai para o `rest`, de modo
# que a soma dos tres servicos seja exatamente o total do perfil.
#
#   memoria  nginx 1 : auth 3 : rest 4   (de 8)
#   cpus     nginx 1 : auth 2 : rest 3   (de 6)
#   pids     nginx 2 : auth 5 : rest 5   (de 12)
#
# nginx e um proxy fino; auth (GoTrue) e rest (PostgREST) sustentam a carga.
# Os pesos sao espelhados em servidor/api-internal/app/project_settings.py —
# um contrato de teste garante que as duas tabelas nao divirjam.

RESOURCE_SERVICES=(NGINX AUTH REST)
RESOURCE_MEM_WEIGHTS=(1 3 4)
RESOURCE_CPU_WEIGHTS=(1 2 3)
RESOURCE_PIDS_WEIGHTS=(2 5 5)
RESOURCE_MEM_FLOORS_MIB=(16 64 32)
RESOURCE_GHC_HEAP_PERCENT=80

resource_profiles_error() {
    echo "Erro: $*" >&2
    exit 1
}

resource_env_value() {
    sed -n "s/^$1=//p" "$2" | head -1 | tr -d '"'"'"''
}

resource_mem_to_mib() {
    local raw="${1,,}" number unit
    number="${raw%[mg]}"
    unit="${raw#"$number"}"
    [[ "$number" =~ ^[0-9]+$ && -n "$number" ]] \
        || resource_profiles_error "memoria invalida: $1 (use 256m ou 1g)"
    case "$unit" in
        m) printf '%s' "$number" ;;
        g) printf '%s' "$((number * 1024))" ;;
        *) resource_profiles_error "memoria invalida: $1 (use sufixo m ou g)" ;;
    esac
}

resource_cpus_to_centi() {
    local raw="$1" int frac
    [[ "$raw" =~ ^([0-9]+)(\.([0-9]{1,2}))?$ ]] \
        || resource_profiles_error "cpus invalido: $raw (use 0.50, 1.50, 3.00)"
    int="${BASH_REMATCH[1]}"
    frac="${BASH_REMATCH[3]:-0}"
    while [ "${#frac}" -lt 2 ]; do frac="${frac}0"; done
    printf '%s' "$((10#$int * 100 + 10#$frac))"
}

resource_split() {
    local total="$1"; shift
    local -a weights=("$@")
    local sum=0 weight index used=0 share
    for weight in "${weights[@]}"; do sum=$((sum + weight)); done
    local -a shares=()
    for index in "${!weights[@]}"; do
        if [ "$index" -eq $((${#weights[@]} - 1)) ]; then
            share=$((total - used))
        else
            share=$((total * weights[index] / sum))
            used=$((used + share))
        fi
        [ "$share" -ge 1 ] \
            || resource_profiles_error "perfil pequeno demais para ratear: total=$total"
        shares+=("$share")
    done
    printf '%s\n' "${shares[@]}"
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
    [[ "$pids" =~ ^[0-9]+$ ]] || resource_profiles_error "PROJECT_RES_${upper}_PIDS invalido: $pids"

    local -a mem_shares cpu_shares pids_shares
    mapfile -t mem_shares < <(resource_split "$(resource_mem_to_mib "$mem")" "${RESOURCE_MEM_WEIGHTS[@]}")
    local floor_index
    for floor_index in "${!RESOURCE_SERVICES[@]}"; do
        [ "${mem_shares[floor_index]}" -ge "${RESOURCE_MEM_FLOORS_MIB[floor_index]}" ] \
            || resource_profiles_error \
                "perfil $profile da apenas ${mem_shares[floor_index]}m ao ${RESOURCE_SERVICES[floor_index],,}; o minimo seguro e ${RESOURCE_MEM_FLOORS_MIB[floor_index]}m. Aumente PROJECT_RES_${upper}_MEMORY."
    done
    mapfile -t cpu_shares < <(resource_split "$(resource_cpus_to_centi "$cpus")" "${RESOURCE_CPU_WEIGHTS[@]}")
    mapfile -t pids_shares < <(resource_split "$pids" "${RESOURCE_PIDS_WEIGHTS[@]}")

    local temporary index service
    temporary="$(mktemp "${project_env}.limits.XXXXXX")"
    {
        grep -vE '^PROJECT_(RESOURCE_PROFILE|MEM_LIMIT|CPUS|PIDS_LIMIT|REST_GHC_MAX_HEAP|(NGINX|AUTH|REST)_(MEM_LIMIT|CPUS|PIDS_LIMIT))=' \
            "$project_env" || true
        printf 'PROJECT_RESOURCE_PROFILE=%s\n' "$profile"
        # Totais do projeto: referencia para a UI e para os limites derivados.
        printf 'PROJECT_MEM_LIMIT=%s\n' "$mem"
        printf 'PROJECT_CPUS=%s\n' "$cpus"
        printf 'PROJECT_PIDS_LIMIT=%s\n' "$pids"
        for index in "${!RESOURCE_SERVICES[@]}"; do
            service="${RESOURCE_SERVICES[index]}"
            printf 'PROJECT_%s_MEM_LIMIT=%sm\n' "$service" "${mem_shares[index]}"
            printf 'PROJECT_%s_CPUS=%d.%02d\n' "$service" \
                "$((cpu_shares[index] / 100))" "$((cpu_shares[index] % 100))"
            printf 'PROJECT_%s_PIDS_LIMIT=%s\n' "$service" "${pids_shares[index]}"
        done
        printf 'PROJECT_REST_GHC_MAX_HEAP=%sm\n' \
            "$(( mem_shares[2] * RESOURCE_GHC_HEAP_PERCENT / 100 ))"
    } > "$temporary"
    # Preserva dono/permissões do arquivo original (600).
    cat "$temporary" > "$project_env"
    rm -f "$temporary"
}
