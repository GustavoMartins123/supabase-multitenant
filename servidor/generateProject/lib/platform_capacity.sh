#!/usr/bin/env bash

platform_capacity_error() {
    echo "Erro: $*" >&2
    return 1
}

PLATFORM_BASELINE_REFERENCE_CPUS=20

PLATFORM_LIMIT_HEADROOM_PERCENT=100

PLATFORM_LIMIT_FLOOR_MIB=128
PLATFORM_LIMIT_FLOOR_PIDS=128

PLATFORM_SERVICE_CONTAINER=(
    "analytics:supabase-analytics"
    "supavisor:supabase-pooler"
    "realtime:realtime-dev.supabase-realtime"
    "studio:supabase-studio"
    "storage:supabase-storage-global"
    "postgres-meta:postgres-meta-global"
    "studio-nginx:nginx"
    "vector:supabase-vector-global"
    "projects-api:projects-api"
    "authelia:authelia"
    "edge-functions:supabase-edge-functions"
    "key-authorizer:key-authorizer"
    "storage-data-plane:shared-storage-data-plane"
    "imgproxy:supabase-imgproxy-global"
)

PLATFORM_SERVICE_COMPOSE=(
    "analytics:servidor:analytics"
    "supavisor:servidor:supavisor"
    "realtime:servidor:realtime"
    "storage:servidor:storage"
    "vector:servidor:vector"
    "edge-functions:servidor:functions"
    "imgproxy:servidor:imgproxy"
    "storage-data-plane:servidor:storage-data-plane"
    "projects-api:api:projects-api"
    "key-authorizer:api:key-authorizer"
    "postgres-meta:api:postgres-meta-global"
    "studio:studio:studio"
    "studio-nginx:studio:nginx"
    "authelia:studio:authelia"
)

PLATFORM_CPU_SCALED_SERVICES=(realtime supavisor studio-nginx)

PLATFORM_SHARED_BASELINE_MIB=(
    "analytics:592"
    "supavisor:227"
    "realtime:334"
    "studio:256"
    "storage:214"
    "postgres-meta:162"
    "studio-nginx:128"
    "vector:34"
    "projects-api:78"
    "authelia:43"
    "edge-functions:155"
    "key-authorizer:63"
    "storage-data-plane:21"
    "imgproxy:96"
)

PLATFORM_SHARED_PER_PROJECT_MIB=(
    "realtime:24"
    "supavisor:12"
    "storage:8"
)

PLATFORM_SHARED_CPU_WEIGHT=(
    "supavisor:6"
    "realtime:5"
    "storage:4"
    "analytics:3"
    "studio:3"
    "studio-nginx:2"
    "projects-api:2"
    "postgres-meta:1"
    "imgproxy:2"
    "authelia:1"
    "key-authorizer:1"
    "vector:1"
    "edge-functions:2"
    "storage-data-plane:1"
)

PLATFORM_SHARED_CPU_FLOOR_CENTI=(
    "analytics:45"
    "supavisor:80"
    "realtime:30"
    "studio:35"
    "storage:40"
    "postgres-meta:35"
    "studio-nginx:35"
    "vector:15"
    "projects-api:35"
    "authelia:20"
    "edge-functions:35"
    "key-authorizer:35"
    "storage-data-plane:10"
    "imgproxy:30"
)

PLATFORM_POSTGRES_CPU_FLOOR_CENTI=(
    "small:215"
    "medium:475"
    "large:940"
)

PLATFORM_SHARED_PIDS_BASELINE=(
    "analytics:92"
    "supavisor:72"
    "realtime:65"
    "edge-functions:48"
    "storage-data-plane:28"
    "vector:29"
    "authelia:25"
    "studio:24"
    "postgres-meta:24"
    "studio-nginx:40"
    "storage:19"
    "imgproxy:14"
    "projects-api:12"
    "key-authorizer:12"
)

platform_container_cgroup() {
    local container="$1" id base
    command -v docker >/dev/null 2>&1 || return 1
    id="$(docker inspect -f '{{.Id}}' "$container" 2>/dev/null)" || return 1
    [ -n "$id" ] || return 1
    for base in \
        "/sys/fs/cgroup/system.slice/docker-$id.scope" \
        "/sys/fs/cgroup/docker/$id" \
        "/sys/fs/cgroup/memory/docker/$id"; do
        [ -r "$base/memory.stat" ] && { printf '%s' "$base"; return 0; }
    done
    return 1
}

platform_container_peak_mib() {
    local container="$1" base peak limit
    base="$(platform_container_cgroup "$container")" || return 1
    if [ -r "$base/memory.peak" ]; then
        peak="$(awk '{printf "%d", int($1/1048576)}' "$base/memory.peak")"
    else
        peak="$(awk '/^anon /{printf "%d", int($2/1048576); found=1} END{exit !found}' \
            "$base/memory.stat")" || return 1
    fi
    [ -n "$peak" ] && [ "$peak" -gt 0 ] || return 1

    limit="$(docker inspect -f '{{.HostConfig.Memory}}' "$container" 2>/dev/null)"
    if [ -n "$limit" ] && [ "$limit" -gt 0 ]; then
        limit=$(( limit / 1048576 ))
        [ "$peak" -ge $(( limit * 95 / 100 )) ] && return 1
    fi
    printf '%s' "$peak"
}

platform_container_peak_pids() {
    local container="$1" base peak limit
    base="$(platform_container_cgroup "$container")" || return 1
    if [ -r "$base/pids.peak" ]; then
        peak="$(cat "$base/pids.peak")"
    else
        [ -r "$base/pids.current" ] || return 1
        peak="$(cat "$base/pids.current")"
    fi
    [ -n "$peak" ] && [ "$peak" -gt 0 ] || return 1

    limit="$(docker inspect -f '{{.HostConfig.PidsLimit}}' "$container" 2>/dev/null)"
    if [ -n "$limit" ] && [ "$limit" -gt 0 ] 2>/dev/null; then
        [ "$peak" -ge $(( limit * 95 / 100 )) ] && return 1
    fi
    printf '%s' "$peak"
}

platform_service_container() {
    local service="$1" entry
    for entry in "${PLATFORM_SERVICE_CONTAINER[@]}"; do
        [ "${entry%%:*}" = "$service" ] && { printf '%s' "${entry#*:}"; return 0; }
    done
    return 1
}

platform_service_baseline_mib() {
    local service="$1" host_cpus="${2:-0}" entry reference=0 measured container
    for entry in "${PLATFORM_SHARED_BASELINE_MIB[@]}"; do
        [ "${entry%%:*}" = "$service" ] && reference="${entry#*:}"
    done
    [ "$reference" -gt 0 ] \
        || { platform_capacity_error "servico sem baseline de referencia: $service"; return 1; }

    local floor="$reference"
    if [ "$host_cpus" -gt 0 ]; then
        for entry in "${PLATFORM_CPU_SCALED_SERVICES[@]}"; do
            if [ "$entry" = "$service" ]; then
                floor=$(( reference * host_cpus / PLATFORM_BASELINE_REFERENCE_CPUS ))
                [ "$floor" -lt $(( reference / 4 )) ] && floor=$(( reference / 4 ))
                break
            fi
        done
    fi

    if container="$(platform_service_container "$service")"; then
        if measured="$(platform_container_peak_mib "$container")" \
            && [ "$measured" -gt "$floor" ]; then
            printf '%s' "$measured"
            return 0
        fi
    fi
    printf '%s' "$floor"
}

platform_service_baseline_source() {
    local service="$1" host_cpus="${2:-0}" container measured floor
    floor="$(platform_service_baseline_mib "$service" "$host_cpus")" || return 1
    if container="$(platform_service_container "$service")"; then
        if measured="$(platform_container_peak_mib "$container")" \
            && [ "$measured" -ge "$floor" ] && [ "$measured" -gt 0 ]; then
            printf 'medido'
            return 0
        fi
    fi
    printf 'referencia'
}

platform_detect_disk_mib() {
    local declared="${1:-auto}" path="${2:-.}"
    if [ "$declared" != "auto" ] && [ -n "$declared" ]; then
        local lower="${declared,,}" number unit
        number="${lower%[mgt]}"
        unit="${lower#"$number"}"
        [[ "$number" =~ ^[0-9]+$ ]] \
            || { platform_capacity_error "PLATFORM_HOST_DISK invalido: $declared"; return 1; }
        case "$unit" in
            m) printf '%s' "$number" ;;
            g) printf '%s' "$((number * 1024))" ;;
            t) printf '%s' "$((number * 1024 * 1024))" ;;
            *) platform_capacity_error "PLATFORM_HOST_DISK precisa de sufixo m, g ou t"; return 1 ;;
        esac
        return 0
    fi
    df -Pm "$path" 2>/dev/null | awk 'NR==2 {printf "%d", $4}'
}


PLATFORM_PG_CONTROL_ROLES=(
    "platform_app:20:4"
    "key_authorizer:10:2"
    "platform_reader:5:1"
    "platform_meta_admin:5:1"
    "host_agent_rw:10:0"
    "meta_guest:5:0"
)
PLATFORM_PG_SYSTEM_CONNECTIONS=20
PLATFORM_PG_POOL_PER_PROJECT=40

platform_service_cpu_centi() {
    local service="$1" shared_cpu_centi="$2" entry weight=0 total=0 floor=0
    for entry in "${PLATFORM_SHARED_CPU_WEIGHT[@]}"; do
        total=$(( total + ${entry#*:} ))
        [ "${entry%%:*}" = "$service" ] && weight="${entry#*:}"
    done
    [ "$weight" -gt 0 ] \
        || { platform_capacity_error "servico sem peso de CPU: $service"; return 1; }
    for entry in "${PLATFORM_SHARED_CPU_FLOOR_CENTI[@]}"; do
        [ "${entry%%:*}" = "$service" ] && floor="${entry#*:}"
    done
    [ "$floor" -gt 0 ] \
        || { platform_capacity_error "servico sem piso de CPU: $service"; return 1; }
    local share=$(( shared_cpu_centi * weight / total ))
    [ "$share" -lt "$floor" ] && share="$floor"
    printf '%s' "$share"
}

platform_postgres_cpu_floor_centi() {
    local profile="$1" entry
    for entry in "${PLATFORM_POSTGRES_CPU_FLOOR_CENTI[@]}"; do
        [ "${entry%%:*}" = "$profile" ] && { printf '%s' "${entry#*:}"; return 0; }
    done
    platform_capacity_error "perfil sem piso de CPU do Postgres: $profile"
}

platform_service_pids() {
    local service="$1" reserve_percent="$2" entry baseline=0 container measured
    for entry in "${PLATFORM_SHARED_PIDS_BASELINE[@]}"; do
        [ "${entry%%:*}" = "$service" ] && baseline="${entry#*:}"
    done
    [ "$baseline" -gt 0 ] \
        || { platform_capacity_error "servico sem baseline de PIDs: $service"; return 1; }

    if container="$(platform_service_container "$service")"; then
        if measured="$(platform_container_peak_pids "$container" 2>/dev/null)" \
            && [ -n "$measured" ] && [ "$measured" -gt "$baseline" ]; then
            baseline="$measured"
        fi
    fi

    local raw=$(( baseline * 4 ))
    [ "$raw" -lt "$PLATFORM_LIMIT_FLOOR_PIDS" ] && raw="$PLATFORM_LIMIT_FLOOR_PIDS"
    printf '%s' "$(( (raw + 15) / 16 * 16 ))"
}

platform_role_connection_limit() {
    local role="$1" projects="$2" entry minimum per_project
    for entry in "${PLATFORM_PG_CONTROL_ROLES[@]}"; do
        [ "${entry%%:*}" = "$role" ] || continue
        minimum="$(printf '%s' "$entry" | cut -d: -f2)"
        per_project="$(printf '%s' "$entry" | cut -d: -f3)"
        printf '%s' "$(( minimum + per_project * projects ))"
        return 0
    done
    platform_capacity_error "role sem orcamento de conexoes: $role"
    return 1
}

platform_control_connections() {
    local projects="$1" entry total=0 minimum per_project
    for entry in "${PLATFORM_PG_CONTROL_ROLES[@]}"; do
        minimum="$(printf '%s' "$entry" | cut -d: -f2)"
        per_project="$(printf '%s' "$entry" | cut -d: -f3)"
        total=$(( total + minimum + per_project * projects ))
    done
    printf '%s' "$total"
}

platform_env_value() {
    sed -n "s/^$1=//p" "$2" 2>/dev/null | head -1 | tr -d '"'"'"''
}

platform_detect_memory_mib() {
    local declared="${1:-auto}"
    if [ "$declared" != "auto" ] && [ -n "$declared" ]; then
        local lower="${declared,,}" number unit
        number="${lower%[mg]}"
        unit="${lower#"$number"}"
        [[ "$number" =~ ^[0-9]+$ ]] \
            || { platform_capacity_error "PLATFORM_HOST_MEMORY invalido: $declared"; return 1; }
        case "$unit" in
            m) printf '%s' "$number" ;;
            g) printf '%s' "$((number * 1024))" ;;
            *) platform_capacity_error "PLATFORM_HOST_MEMORY precisa de sufixo m ou g"; return 1 ;;
        esac
        return 0
    fi
    [ -r /proc/meminfo ] \
        || { platform_capacity_error "/proc/meminfo ilegivel; declare PLATFORM_HOST_MEMORY"; return 1; }
    awk '/^MemTotal:/ {printf "%d", $2/1024; exit}' /proc/meminfo
}

platform_detect_cpus() {
    local declared="${1:-auto}"
    if [ "$declared" != "auto" ] && [ -n "$declared" ]; then
        printf '%s' "$declared"
        return 0
    fi
    nproc 2>/dev/null || printf '1'
}

platform_shared_baseline_total() {
    local reserve_percent="$1" host_cpus="${2:-0}" entry total=0 value
    for entry in "${PLATFORM_SHARED_BASELINE_MIB[@]}"; do
        value="$(platform_service_baseline_mib "${entry%%:*}" "$host_cpus")" || return 1
        total=$(( total + value ))
    done
    printf '%s' "$(( total * (100 + reserve_percent) / 100 ))"
}

platform_shared_per_project_total() {
    local reserve_percent="$1" entry total=0
    for entry in "${PLATFORM_SHARED_PER_PROJECT_MIB[@]}"; do
        total=$((total + ${entry#*:}))
    done
    printf '%s' "$(( total * (100 + reserve_percent) / 100 ))"
}

platform_service_limit_mib() {
    local service="$1" projects="$2" reserve_percent="$3" host_cpus="${4:-0}"
    local entry base=0 increment=0
    base="$(platform_service_baseline_mib "$service" "$host_cpus")" || return 1
    for entry in "${PLATFORM_SHARED_PER_PROJECT_MIB[@]}"; do
        [ "${entry%%:*}" = "$service" ] && increment="${entry#*:}"
    done
    [ "$base" -gt 0 ] \
        || { platform_capacity_error "servico sem baseline: $service"; return 1; }
    local raw=$(( (base + increment * projects) \
        * (100 + PLATFORM_LIMIT_HEADROOM_PERCENT) / 100 ))
    [ "$raw" -lt "$PLATFORM_LIMIT_FLOOR_MIB" ] && raw="$PLATFORM_LIMIT_FLOOR_MIB"
    printf '%s' "$(( (raw + 15) / 16 * 16 ))"
}

platform_format_mib() {
    local mib="$1"
    if [ "$mib" -ge 1024 ]; then
        printf '%d,%01d GiB' "$((mib / 1024))" "$(( (mib % 1024) * 10 / 1024 ))"
    else
        printf '%d MiB' "$mib"
    fi
}

platform_compute_capacity() {
    local root_env="$1"
    [ -f "$root_env" ] || { platform_capacity_error ".env raiz ausente: $root_env"; return 1; }

    local reserve host_declared cpus_declared postgres_share work_mem_nodes profile
    reserve="$(platform_env_value PLATFORM_RESERVE_PERCENT "$root_env")"
    reserve="${reserve:-20}"
    host_declared="$(platform_env_value PLATFORM_HOST_MEMORY "$root_env")"
    host_declared="${host_declared:-auto}"
    cpus_declared="$(platform_env_value PLATFORM_HOST_CPUS "$root_env")"
    cpus_declared="${cpus_declared:-auto}"
    postgres_share="$(platform_env_value PLATFORM_POSTGRES_SHARE_PERCENT "$root_env")"
    postgres_share="${postgres_share:-50}"
    work_mem_nodes="$(platform_env_value PLATFORM_WORK_MEM_NODES "$root_env")"
    work_mem_nodes="${work_mem_nodes:-2}"
    local active_percent
    active_percent="$(platform_env_value PLATFORM_ACTIVE_CONNECTION_PERCENT "$root_env")"
    active_percent="${active_percent:-25}"
    [[ "$active_percent" =~ ^[0-9]+$ ]] && [ "$active_percent" -ge 5 ] && [ "$active_percent" -le 100 ] \
        || { platform_capacity_error "PLATFORM_ACTIVE_CONNECTION_PERCENT fora de 5..100: $active_percent"; return 1; }
    PLATFORM_CAP_ACTIVE_PERCENT="$active_percent"
    local disk_declared disk_path
    disk_declared="$(platform_env_value PLATFORM_HOST_DISK "$root_env")"
    disk_declared="${disk_declared:-auto}"
    disk_path="$(dirname "$root_env")"
    profile="$(platform_env_value PLATFORM_CAPACITY_PROFILE "$root_env")"
    profile="${profile:-$(platform_env_value PROJECT_RESOURCE_PROFILE "$root_env")}"
    profile="${profile:-medium}"

    [[ "$reserve" =~ ^[0-9]+$ ]] && [ "$reserve" -ge 10 ] && [ "$reserve" -le 60 ] \
        || { platform_capacity_error "PLATFORM_RESERVE_PERCENT fora de 10..60: $reserve"; return 1; }

    PLATFORM_CAP_RESERVE_PERCENT="$reserve"
    PLATFORM_CAP_HOST_MIB="$(platform_detect_memory_mib "$host_declared")" || return 1
    PLATFORM_CAP_HOST_CPUS="$(platform_detect_cpus "$cpus_declared")"
    PLATFORM_CAP_RESERVED_MIB=$(( PLATFORM_CAP_HOST_MIB * reserve / 100 ))
    PLATFORM_CAP_ALLOCATABLE_MIB=$(( PLATFORM_CAP_HOST_MIB - PLATFORM_CAP_RESERVED_MIB ))

    local upper profile_mem
    upper="$(printf '%s' "$profile" | tr '[:lower:]' '[:upper:]')"
    profile_mem="$(platform_env_value "PROJECT_RES_${upper}_MEMORY" "$root_env")"
    [ -n "$profile_mem" ] \
        || { platform_capacity_error "PROJECT_RES_${upper}_MEMORY ausente no .env raiz"; return 1; }
    local profile_mib
    case "${profile_mem,,}" in
        *g) profile_mib=$(( ${profile_mem%[gG]} * 1024 )) ;;
        *m) profile_mib=${profile_mem%[mM]} ;;
        *) platform_capacity_error "PROJECT_RES_${upper}_MEMORY invalido: $profile_mem"; return 1 ;;
    esac
    PLATFORM_CAP_PROFILE="$profile"
    PLATFORM_CAP_PROJECT_MIB="$profile_mib"

    local shared_base shared_increment
    shared_base="$(platform_shared_baseline_total "$reserve" "$PLATFORM_CAP_HOST_CPUS")"
    shared_increment="$(platform_shared_per_project_total "$reserve")"
    PLATFORM_CAP_SHARED_BASE_MIB="$shared_base"
    PLATFORM_CAP_SHARED_PER_PROJECT_MIB="$shared_increment"

    local work_mem_floor_mib=4 autovacuum=4
    PLATFORM_CAP_WORK_MEM_NODES="$work_mem_nodes"
    PLATFORM_CAP_AUTOVACUUM_WORKERS="$autovacuum"

    local hash_multiplier=2
    PLATFORM_CAP_HASH_MEM_MULTIPLIER="$hash_multiplier"

    local projects=0 iteration budget_for_rest postgres_budget shared_total
    local capacity_by_memory previous=-1 shared_buffers_mib maintenance_mib
    local max_connections work_mem_mib available_for_sorts active_connections
    for iteration in 1 2 3 4 5 6 7 8; do
        shared_total=$(( shared_base + shared_increment * projects ))
        budget_for_rest=$(( PLATFORM_CAP_ALLOCATABLE_MIB - shared_total ))
        [ "$budget_for_rest" -gt 0 ] || {
            platform_capacity_error "camada compartilhada nao cabe no host com folga de ${reserve}%"
            return 1
        }
        postgres_budget=$(( budget_for_rest * postgres_share / 100 ))
        capacity_by_memory=$(( (budget_for_rest - postgres_budget) / profile_mib ))
        [ "$capacity_by_memory" -lt 0 ] && capacity_by_memory=0
        projects="$capacity_by_memory"
        [ "$projects" -eq "$previous" ] && break
        previous="$projects"
    done

    PLATFORM_CAP_POSTGRES_MIB="$postgres_budget"
    PLATFORM_CAP_SHARED_TOTAL_MIB="$shared_total"
    PLATFORM_CAP_BY_MEMORY="$capacity_by_memory"

    shared_buffers_mib=$(( postgres_budget * 25 / 100 ))
    maintenance_mib=$(( postgres_budget / 16 ))
    [ "$maintenance_mib" -gt 1024 ] && maintenance_mib=1024
    [ "$maintenance_mib" -lt 64 ] && maintenance_mib=64

    available_for_sorts=$(( postgres_budget - shared_buffers_mib - maintenance_mib * autovacuum ))
    [ "$available_for_sorts" -gt 0 ] || {
        platform_capacity_error "orcamento do Postgres nao cobre shared_buffers + manutencao"
        return 1
    }

    local parallel_per_gather=2
    [ "$projects" -gt 8 ] && parallel_per_gather=1
    PLATFORM_CAP_PARALLEL_PER_GATHER="$parallel_per_gather"

    local allocations_per_connection=$(( work_mem_nodes \
        * (1 + parallel_per_gather) * hash_multiplier ))
    PLATFORM_CAP_ALLOCATIONS_PER_CONNECTION="$allocations_per_connection"

    while [ "$projects" -gt 0 ]; do
        max_connections=$(( $(platform_control_connections "$projects") \
            + PLATFORM_PG_SYSTEM_CONNECTIONS \
            + projects * PLATFORM_PG_POOL_PER_PROJECT ))
        active_connections=$(( max_connections * active_percent / 100 ))
        [ "$active_connections" -lt 1 ] && active_connections=1
        work_mem_mib=$(( available_for_sorts \
            / (active_connections * allocations_per_connection) ))
        [ "$work_mem_mib" -ge "$work_mem_floor_mib" ] && break
        projects=$(( projects - 1 ))
    done
    if [ "$projects" -eq 0 ]; then
        platform_capacity_error \
            "host de $(platform_format_mib "$PLATFORM_CAP_HOST_MIB") nao comporta nenhum projeto do perfil $profile com folga de ${reserve}%. Use um perfil menor, reduza PLATFORM_RESERVE_PERCENT ou aumente a maquina."
        return 1
    fi

    PLATFORM_CAP_SHARED_BUFFERS_MIB="$shared_buffers_mib"
    PLATFORM_CAP_MAINTENANCE_MIB="$maintenance_mib"
    PLATFORM_CAP_WORK_MEM_MIB="$work_mem_mib"
    PLATFORM_CAP_MAX_CONNECTIONS="$max_connections"
    PLATFORM_CAP_ACTIVE_CONNECTIONS="$active_connections"
    PLATFORM_CAP_BY_CONNECTIONS="$projects"

    PLATFORM_CAP_REPLICATION_SLOTS=$(( projects + projects * reserve / 100 + 4 ))
    PLATFORM_CAP_WAL_SENDERS=$(( PLATFORM_CAP_REPLICATION_SLOTS + 8 ))
    PLATFORM_CAP_LOGICAL_WORKERS=$(( PLATFORM_CAP_REPLICATION_SLOTS / 2 ))
    [ "$PLATFORM_CAP_LOGICAL_WORKERS" -lt 4 ] && PLATFORM_CAP_LOGICAL_WORKERS=4
    PLATFORM_CAP_BY_SLOTS="$projects"

    PLATFORM_CAP_PROJECTS="$projects"
    if [ "$PLATFORM_CAP_BY_CONNECTIONS" -lt "$PLATFORM_CAP_BY_MEMORY" ]; then
        PLATFORM_CAP_BINDING="work_mem"
    else
        PLATFORM_CAP_BINDING="memoria"
    fi

    local allocatable_centi shared_cpu_centi postgres_cpu_centi project_cpu_centi
    allocatable_centi=$(( PLATFORM_CAP_HOST_CPUS * 100 * (100 - reserve) / 100 ))
    PLATFORM_CAP_ALLOCATABLE_CPUS=$(( allocatable_centi / 100 ))
    shared_cpu_centi=$(( allocatable_centi * 20 / 100 ))
    postgres_cpu_centi=$(( allocatable_centi * postgres_share / 100 ))
    PLATFORM_CAP_POSTGRES_CPU_FLOOR_CENTI="$(platform_postgres_cpu_floor_centi "$profile")" \
        || return 1
    [ "$postgres_cpu_centi" -lt "$PLATFORM_CAP_POSTGRES_CPU_FLOOR_CENTI" ] \
        && postgres_cpu_centi="$PLATFORM_CAP_POSTGRES_CPU_FLOOR_CENTI"
    PLATFORM_CAP_SHARED_CPU_CENTI="$shared_cpu_centi"
    PLATFORM_CAP_POSTGRES_CPU_CENTI="$postgres_cpu_centi"

    local profile_cpus profile_cpu_centi
    profile_cpus="$(platform_env_value "PROJECT_RES_${upper}_CPUS" "$root_env")"
    profile_cpu_centi=$(( ${profile_cpus%%.*} * 100 + 10#$(printf '%s' "${profile_cpus#*.}" | cut -c1-2) ))
    PLATFORM_CAP_PROJECT_CPU_CENTI="$profile_cpu_centi"
    project_cpu_centi=$(( allocatable_centi - shared_cpu_centi - postgres_cpu_centi ))
    [ "$project_cpu_centi" -lt 0 ] && project_cpu_centi=0
    PLATFORM_CAP_CPU_OVERSUBSCRIBE=$(( PLATFORM_CAP_PROJECTS * profile_cpu_centi * 100 \
        / (project_cpu_centi > 0 ? project_cpu_centi : 1) ))
    local cpu_max_oversubscribe
    cpu_max_oversubscribe="$(platform_env_value PLATFORM_CPU_OVERSUBSCRIBE_MAX "$root_env")"
    cpu_max_oversubscribe="${cpu_max_oversubscribe:-300}"
    [[ "$cpu_max_oversubscribe" =~ ^[0-9]+$ ]] && [ "$cpu_max_oversubscribe" -ge 100 ] \
        || { platform_capacity_error "PLATFORM_CPU_OVERSUBSCRIBE_MAX precisa ser >= 100"; return 1; }
    PLATFORM_CAP_CPU_OVERSUBSCRIBE_MAX="$cpu_max_oversubscribe"

    PLATFORM_CAP_BY_CPU=$(( project_cpu_centi * cpu_max_oversubscribe / 100 / profile_cpu_centi ))
    if [ "$PLATFORM_CAP_BY_CPU" -lt "$PLATFORM_CAP_PROJECTS" ]; then
        PLATFORM_CAP_PROJECTS="$PLATFORM_CAP_BY_CPU"
        PLATFORM_CAP_BINDING="cpu"
        PLATFORM_CAP_CPU_OVERSUBSCRIBE="$cpu_max_oversubscribe"
    fi
    [ "$PLATFORM_CAP_PROJECTS" -gt 0 ] || {
        platform_capacity_error \
            "host sem CPU suficiente para um projeto $profile e os servicos compartilhados"
        return 1
    }

    PLATFORM_CAP_DISK_MIB="$(platform_detect_disk_mib "$disk_declared" "$disk_path")"
    [ -n "$PLATFORM_CAP_DISK_MIB" ] && [ "$PLATFORM_CAP_DISK_MIB" -gt 0 ] \
        || { platform_capacity_error "nao foi possivel medir o disco; declare PLATFORM_HOST_DISK"; return 1; }
    PLATFORM_CAP_DISK_RESERVED_MIB=$(( PLATFORM_CAP_DISK_MIB * reserve / 100 ))
    PLATFORM_CAP_DISK_ALLOCATABLE_MIB=$(( PLATFORM_CAP_DISK_MIB - PLATFORM_CAP_DISK_RESERVED_MIB ))

    PLATFORM_CAP_MAX_WAL_MIB=$(( PLATFORM_CAP_DISK_ALLOCATABLE_MIB / 32 ))
    [ "$PLATFORM_CAP_MAX_WAL_MIB" -gt 16384 ] && PLATFORM_CAP_MAX_WAL_MIB=16384
    [ "$PLATFORM_CAP_MAX_WAL_MIB" -lt 1024 ] && PLATFORM_CAP_MAX_WAL_MIB=1024
    PLATFORM_CAP_MIN_WAL_MIB=$(( PLATFORM_CAP_MAX_WAL_MIB / 4 ))
    PLATFORM_CAP_SLOT_WAL_KEEP_MIB=$(( PLATFORM_CAP_MAX_WAL_MIB / 2 ))

    local disk_for_temp
    disk_for_temp=$(( (PLATFORM_CAP_DISK_ALLOCATABLE_MIB - PLATFORM_CAP_MAX_WAL_MIB) / 4 ))
    PLATFORM_CAP_TEMP_FILE_LIMIT_MIB=$(( disk_for_temp / active_connections ))
    [ "$PLATFORM_CAP_TEMP_FILE_LIMIT_MIB" -lt 64 ] && PLATFORM_CAP_TEMP_FILE_LIMIT_MIB=64
    [ "$PLATFORM_CAP_TEMP_FILE_LIMIT_MIB" -gt 8192 ] && PLATFORM_CAP_TEMP_FILE_LIMIT_MIB=8192

    local disk_for_projects
    disk_for_projects=$(( PLATFORM_CAP_DISK_ALLOCATABLE_MIB - PLATFORM_CAP_MAX_WAL_MIB - disk_for_temp ))
    PLATFORM_CAP_PROJECT_DISK_MIB=$(( disk_for_projects / (PLATFORM_CAP_PROJECTS > 0 ? PLATFORM_CAP_PROJECTS : 1) ))

    PLATFORM_CAP_AUTOVACUUM_WORKERS=$(( (PLATFORM_CAP_PROJECTS + 2) / 3 ))
    [ "$PLATFORM_CAP_AUTOVACUUM_WORKERS" -lt 4 ] && PLATFORM_CAP_AUTOVACUUM_WORKERS=4
    [ "$PLATFORM_CAP_AUTOVACUUM_WORKERS" -gt 8 ] && PLATFORM_CAP_AUTOVACUUM_WORKERS=8

    PLATFORM_CAP_MAX_PARALLEL_WORKERS=$(( PLATFORM_CAP_ALLOCATABLE_CPUS / 4 ))
    [ "$PLATFORM_CAP_MAX_PARALLEL_WORKERS" -lt 2 ] && PLATFORM_CAP_MAX_PARALLEL_WORKERS=2
    PLATFORM_CAP_MAX_PARALLEL_MAINTENANCE=$(( PLATFORM_CAP_MAX_PARALLEL_WORKERS / 2 ))
    [ "$PLATFORM_CAP_MAX_PARALLEL_MAINTENANCE" -lt 1 ] && PLATFORM_CAP_MAX_PARALLEL_MAINTENANCE=1
    PLATFORM_CAP_MAX_WORKER_PROCESSES=$(( PLATFORM_CAP_MAX_PARALLEL_WORKERS \
        + PLATFORM_CAP_LOGICAL_WORKERS + 4 ))
    return 0
}

platform_render_postgres_conf() {
    local root_env="$1" output="$2"
    platform_compute_capacity "$root_env" || return 1

    local effective_cache_mib=$(( PLATFORM_CAP_SHARED_BUFFERS_MIB * 2 ))
    local temporary
    temporary="$(mktemp "${output}.XXXXXX")" || return 1
    {
        printf '# Gerado por lib/platform_capacity.sh — NAO EDITE A MAO.\n'
        printf '# Regenere com: bash lib/platform_capacity.sh --render-postgres <root_env> <saida>\n'
        printf '# Host medido: %s MiB, %s nucleos. Folga de %s%%. Teto: %s projetos (%s).\n\n' \
            "$PLATFORM_CAP_HOST_MIB" "$PLATFORM_CAP_HOST_CPUS" \
            "$PLATFORM_CAP_RESERVE_PERCENT" "$PLATFORM_CAP_PROJECTS" \
            "$PLATFORM_CAP_BINDING"

        printf '# --- exigem RESTART: provisionados no teto ---\n'
        printf 'max_connections = %s\n' "$PLATFORM_CAP_MAX_CONNECTIONS"
        printf 'shared_buffers = %sMB\n' "$PLATFORM_CAP_SHARED_BUFFERS_MIB"
        printf 'max_worker_processes = %s\n' "$PLATFORM_CAP_MAX_WORKER_PROCESSES"
        printf 'max_replication_slots = %s\n' "$PLATFORM_CAP_REPLICATION_SLOTS"
        printf 'max_wal_senders = %s\n' "$PLATFORM_CAP_WAL_SENDERS"
        printf 'autovacuum_max_workers = %s\n\n' "$PLATFORM_CAP_AUTOVACUUM_WORKERS"

        printf '# --- aceitam reload: ajustaveis a quente conforme projetos entram ---\n'
        printf 'work_mem = %sMB\n' "$PLATFORM_CAP_WORK_MEM_MIB"
        printf 'maintenance_work_mem = %sMB\n' "$PLATFORM_CAP_MAINTENANCE_MIB"
        printf 'temp_file_limit = %sMB\n' "$PLATFORM_CAP_TEMP_FILE_LIMIT_MIB"
        printf 'max_wal_size = %sMB\n' "$PLATFORM_CAP_MAX_WAL_MIB"
        printf 'min_wal_size = %sMB\n' "$PLATFORM_CAP_MIN_WAL_MIB"
        printf 'max_slot_wal_keep_size = %sMB\n' "$PLATFORM_CAP_SLOT_WAL_KEEP_MIB"
        printf 'effective_cache_size = %sMB\n' "$effective_cache_mib"
        printf 'max_parallel_workers = %s\n' "$PLATFORM_CAP_MAX_PARALLEL_WORKERS"
        printf 'max_parallel_workers_per_gather = %s\n' "$PLATFORM_CAP_PARALLEL_PER_GATHER"
        printf 'max_parallel_maintenance_workers = %s\n' "$PLATFORM_CAP_MAX_PARALLEL_MAINTENANCE"
    } > "$temporary" || { rm -f "$temporary"; return 1; }
    chmod 644 "$temporary"
    mv "$temporary" "$output"
}

platform_render_compose_override() {
    local root_env="$1" target="$2" output="$3"
    platform_compute_capacity "$root_env" || return 1

    local entry service file compose_name memory cpus pids temporary any=0
    temporary="$(mktemp "${output}.XXXXXX")" || return 1
    {
        printf '# Gerado por lib/platform_capacity.sh — NAO EDITE A MAO.\n'
        printf '# Limites derivados deste host: %s MiB, %s nucleos, folga %s%%.\n' \
            "$PLATFORM_CAP_HOST_MIB" "$PLATFORM_CAP_HOST_CPUS" "$PLATFORM_CAP_RESERVE_PERCENT"
        printf '# Regenere com: bash lib/platform_capacity.sh --render-compose <root_env> %s <saida>\n' "$target"
        printf 'services:\n'

        if [ "$target" = servidor ]; then
            printf '  db:\n'
            printf '    mem_limit: %sm\n' "$PLATFORM_CAP_POSTGRES_MIB"
            printf '    memswap_limit: %sm\n' "$PLATFORM_CAP_POSTGRES_MIB"
            printf '    cpus: "%d.%02d"\n' \
                "$(( PLATFORM_CAP_POSTGRES_CPU_CENTI / 100 ))" \
                "$(( PLATFORM_CAP_POSTGRES_CPU_CENTI % 100 ))"
            printf '    pids_limit: %s\n' \
                "$(( (PLATFORM_CAP_MAX_CONNECTIONS \
                    + PLATFORM_CAP_MAX_WORKER_PROCESSES \
                    + PLATFORM_CAP_AUTOVACUUM_WORKERS + 32) \
                    * (100 + PLATFORM_CAP_RESERVE_PERCENT) / 100 ))"
            any=1
        fi

        for entry in "${PLATFORM_SERVICE_COMPOSE[@]}"; do
            service="${entry%%:*}"
            file="$(printf '%s' "$entry" | cut -d: -f2)"
            compose_name="$(printf '%s' "$entry" | cut -d: -f3)"
            [ "$file" = "$target" ] || continue
            memory="$(platform_service_limit_mib "$service" "$PLATFORM_CAP_PROJECTS" \
                "$PLATFORM_CAP_RESERVE_PERCENT" "$PLATFORM_CAP_HOST_CPUS")" || return 1
            cpus="$(platform_service_cpu_centi "$service" "$PLATFORM_CAP_SHARED_CPU_CENTI")" || return 1
            pids="$(platform_service_pids "$service" "$PLATFORM_CAP_RESERVE_PERCENT")" || return 1
            printf '  %s:\n' "$compose_name"
            printf '    mem_limit: %sm\n' "$memory"
            printf '    memswap_limit: %sm\n' "$memory"
            printf '    cpus: "%d.%02d"\n' "$(( cpus / 100 ))" "$(( cpus % 100 ))"
            printf '    pids_limit: %s\n' "$pids"
            any=1
        done
    } > "$temporary" || { rm -f "$temporary"; return 1; }

    if [ "$any" -eq 0 ]; then
        rm -f "$temporary"
        platform_capacity_error "alvo de compose desconhecido: $target (use servidor, api ou studio)"
        return 1
    fi
    chmod 644 "$temporary"
    mv "$temporary" "$output"
}

platform_render_env() {
    local root_env="$1" output="$2"
    platform_compute_capacity "$root_env" || return 1
    local temporary
    temporary="$(mktemp "${output}.XXXXXX")" || return 1
    {
        printf '# Gerado por lib/platform_capacity.sh — NAO EDITE A MAO.\n'
        printf '# Capacidade derivada deste host. Regenere com --render-env.\n'
        printf 'PLATFORM_PROJECT_CAPACITY=%s\n' "$PLATFORM_CAP_PROJECTS"
        printf 'PLATFORM_CAPACITY_BINDING=%s\n' "$PLATFORM_CAP_BINDING"
        printf 'PLATFORM_HOST_MEMORY_MIB=%s\n' "$PLATFORM_CAP_HOST_MIB"
        printf 'PLATFORM_HOST_CPU_COUNT=%s\n' "$PLATFORM_CAP_HOST_CPUS"
        printf 'PLATFORM_RESERVE_PERCENT=%s\n' "$PLATFORM_CAP_RESERVE_PERCENT"
        printf 'PLATFORM_PROJECT_PROFILE=%s\n' "$PLATFORM_CAP_PROFILE"
    } > "$temporary" || { rm -f "$temporary"; return 1; }
    chmod 644 "$temporary"
    mv "$temporary" "$output"
}

platform_apply_shared_limits() {
    local root_env="$1"
    platform_compute_capacity "$root_env" || return 1
    command -v docker >/dev/null 2>&1 \
        || { platform_capacity_error "docker ausente; nao da para aplicar limites"; return 1; }

    local entry service container memory cpus pids applied=0 skipped=0
    for entry in "${PLATFORM_SHARED_BASELINE_MIB[@]}"; do
        service="${entry%%:*}"
        container="$(platform_service_container "$service")" || continue
        docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -qx true \
            || { skipped=$(( skipped + 1 )); continue; }

        memory="$(platform_service_limit_mib "$service" "$PLATFORM_CAP_PROJECTS" \
            "$PLATFORM_CAP_RESERVE_PERCENT" "$PLATFORM_CAP_HOST_CPUS")" || return 1
        cpus="$(platform_service_cpu_centi "$service" "$PLATFORM_CAP_SHARED_CPU_CENTI")" || return 1
        pids="$(platform_service_pids "$service" "$PLATFORM_CAP_RESERVE_PERCENT")" || return 1

        if docker update \
            --memory "${memory}m" --memory-swap "${memory}m" \
            --cpus "$(printf '%d.%02d' "$(( cpus / 100 ))" "$(( cpus % 100 ))")" \
            --pids-limit "$pids" \
            "$container" >/dev/null 2>&1; then
            applied=$(( applied + 1 ))
        else
            echo "Aviso: nao foi possivel aplicar limites em $container" >&2
            skipped=$(( skipped + 1 ))
        fi
    done
    echo "Limites da camada compartilhada aplicados: $applied ajustados, $skipped ignorados (teto: $PLATFORM_CAP_PROJECTS projetos)"
}

platform_capacity_report() {
    local root_env="$1"
    platform_compute_capacity "$root_env" || return 1

    printf '\n  CAPACIDADE DA PLATAFORMA\n'
    printf '  %s\n\n' "$(printf '=%.0s' {1..66})"

    printf '  Host\n'
    printf '    memoria total                %18s\n' "$(platform_format_mib "$PLATFORM_CAP_HOST_MIB")"
    printf '    folga reservada (%2d%%)        %18s\n' \
        "$PLATFORM_CAP_RESERVE_PERCENT" "$(platform_format_mib "$PLATFORM_CAP_RESERVED_MIB")"
    printf '    alocavel                     %18s\n' "$(platform_format_mib "$PLATFORM_CAP_ALLOCATABLE_MIB")"
    printf '    CPUs (alocaveis / total)     %18s\n\n' \
        "$PLATFORM_CAP_ALLOCATABLE_CPUS / $PLATFORM_CAP_HOST_CPUS"

    printf '  Reparticao do alocavel\n'
    printf '    camada compartilhada         %18s\n' "$(platform_format_mib "$PLATFORM_CAP_SHARED_TOTAL_MIB")"
    printf '    Postgres                     %18s\n' "$(platform_format_mib "$PLATFORM_CAP_POSTGRES_MIB")"
    printf '    projetos (%2d x perfil %-6s) %18s\n\n' \
        "$PLATFORM_CAP_PROJECTS" "$PLATFORM_CAP_PROFILE" \
        "$(platform_format_mib "$(( PLATFORM_CAP_PROJECTS * PLATFORM_CAP_PROJECT_MIB ))")"

    printf '  Postgres derivado\n'
    printf '    shared_buffers (25%%)         %18s\n' "$(platform_format_mib "$PLATFORM_CAP_SHARED_BUFFERS_MIB")"
    printf '    maintenance_work_mem         %18s\n' "$(platform_format_mib "$PLATFORM_CAP_MAINTENANCE_MIB")"
    printf '    work_mem (derivado)          %18s\n' "${PLATFORM_CAP_WORK_MEM_MIB} MiB"
    printf '    nos de work_mem por query    %18s\n' "$PLATFORM_CAP_WORK_MEM_NODES"
    printf '    x paralelismo (1 + %d)        %18s\n' \
        "$PLATFORM_CAP_PARALLEL_PER_GATHER" "$(( 1 + PLATFORM_CAP_PARALLEL_PER_GATHER ))x"
    printf '    x hash_mem_multiplier        %18s\n' "${PLATFORM_CAP_HASH_MEM_MULTIPLIER}x"
    printf '    = alocacoes por conexao      %18s\n' "$PLATFORM_CAP_ALLOCATIONS_PER_CONNECTION"
    printf '    max_connections              %18s\n' "$PLATFORM_CAP_MAX_CONNECTIONS"
    printf '    conexoes concorrentes (%2d%%)  %18s\n' \
        "$PLATFORM_CAP_ACTIVE_PERCENT" "$PLATFORM_CAP_ACTIVE_CONNECTIONS"
    printf '    max_replication_slots        %18s\n' "$PLATFORM_CAP_REPLICATION_SLOTS"
    printf '    max_wal_senders              %18s\n\n' "$PLATFORM_CAP_WAL_SENDERS"

    printf '  Teto de projetos, por restricao\n'
    printf '    por memoria de projeto       %18s\n' "$PLATFORM_CAP_BY_MEMORY"
    printf '    por piso de work_mem         %18s\n' "$PLATFORM_CAP_BY_CONNECTIONS"
    printf '    por CPU (sobrecompromisso)   %18s\n' "$PLATFORM_CAP_BY_CPU"
    printf '    ---------------------------------------------------\n'
    printf '    TETO (%s)  %*s\n\n' "$PLATFORM_CAP_BINDING" \
        "$(( 30 - ${#PLATFORM_CAP_BINDING} ))" "$PLATFORM_CAP_PROJECTS"

    printf '  Disco\n'
    printf '    total no ponto de montagem   %18s\n' "$(platform_format_mib "$PLATFORM_CAP_DISK_MIB")"
    printf '    folga reservada (%2d%%)        %18s\n' \
        "$PLATFORM_CAP_RESERVE_PERCENT" "$(platform_format_mib "$PLATFORM_CAP_DISK_RESERVED_MIB")"
    printf '    max_wal_size                 %18s\n' "$(platform_format_mib "$PLATFORM_CAP_MAX_WAL_MIB")"
    printf '    min_wal_size                 %18s\n' "$(platform_format_mib "$PLATFORM_CAP_MIN_WAL_MIB")"
    printf '    max_slot_wal_keep_size       %18s\n' "$(platform_format_mib "$PLATFORM_CAP_SLOT_WAL_KEEP_MIB")"
    printf '    temp_file_limit por conexao  %18s\n' "$(platform_format_mib "$PLATFORM_CAP_TEMP_FILE_LIMIT_MIB")"
    printf '    cota por projeto             %18s\n\n' "$(platform_format_mib "$PLATFORM_CAP_PROJECT_DISK_MIB")"

    printf '  Workers do Postgres\n'
    printf '    autovacuum_max_workers       %18s\n' "$PLATFORM_CAP_AUTOVACUUM_WORKERS"
    printf '    max_parallel_workers         %18s\n' "$PLATFORM_CAP_MAX_PARALLEL_WORKERS"
    printf '    max_parallel_workers_per_gather %15s\n' "$PLATFORM_CAP_PARALLEL_PER_GATHER"
    printf '    max_parallel_maintenance_workers %14s\n' "$PLATFORM_CAP_MAX_PARALLEL_MAINTENANCE"
    printf '    max_logical_replication_workers %15s\n' "$PLATFORM_CAP_LOGICAL_WORKERS"
    printf '    max_worker_processes         %18s\n\n' "$PLATFORM_CAP_MAX_WORKER_PROCESSES"

    printf '  CPU (centi-CPU; 100 = 1 nucleo)\n'
    printf '    alocavel                     %18s\n' "$(( PLATFORM_CAP_ALLOCATABLE_CPUS * 100 ))"
    printf '    camada compartilhada (20%%)   %18s\n' "$PLATFORM_CAP_SHARED_CPU_CENTI"
    printf '    Postgres                     %18s\n' "$PLATFORM_CAP_POSTGRES_CPU_CENTI"
    printf '    teto de projetos por CPU     %18s\n' "$PLATFORM_CAP_BY_CPU"
    printf '    sobrecompromisso (max %3d%%)  %17s%%\n\n' \
        "$PLATFORM_CAP_CPU_OVERSUBSCRIBE_MAX" "$PLATFORM_CAP_CPU_OVERSUBSCRIBE"

    printf '  Limites da camada compartilhada\n'
    printf '    %-20s %8s %8s %8s  %s\n' SERVICO MEMORIA CPU PIDS ORIGEM
    local entry service
    for entry in "${PLATFORM_SHARED_BASELINE_MIB[@]}"; do
        service="${entry%%:*}"
        printf '    %-20s %7sm %8s %8s  %s\n' "$service" \
            "$(platform_service_limit_mib "$service" "$PLATFORM_CAP_PROJECTS" "$PLATFORM_CAP_RESERVE_PERCENT" "$PLATFORM_CAP_HOST_CPUS")" \
            "$(platform_service_cpu_centi "$service" "$PLATFORM_CAP_SHARED_CPU_CENTI")" \
            "$(platform_service_pids "$service" "$PLATFORM_CAP_RESERVE_PERCENT")" \
            "$(platform_service_baseline_source "$service" "$PLATFORM_CAP_HOST_CPUS")"
    done

    printf '\n  ORIGEM: "medido" le memory.peak/pids.peak do cgroup neste host.\n'
    printf '  "referencia" e o fallback de primeira instalacao, escalado pelos\n'
    printf '  nucleos nos servicos que alocam por scheduler (realtime, supavisor,\n'
    printf '  studio-nginx). Medicao ceifada pelo proprio limite e descartada.\n'
    printf '\n  Nao medido (estimativa): o incremento por projeto de realtime,\n'
    printf '  supavisor e storage. Exige N projetos com trafego real.\n\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        --report)
            platform_capacity_report "${2:?uso: platform_capacity.sh --report <root_env>}"
            ;;
        --render-env)
            platform_render_env \
                "${2:?uso: platform_capacity.sh --render-env <root_env> <saida>}" \
                "${3:?uso: platform_capacity.sh --render-env <root_env> <saida>}"
            ;;
        --apply-shared)
            platform_apply_shared_limits \
                "${2:?uso: platform_capacity.sh --apply-shared <root_env>}"
            ;;
        --render-compose)
            platform_render_compose_override \
                "${2:?uso: --render-compose <root_env> <servidor|api|studio> <saida>}" \
                "${3:?uso: --render-compose <root_env> <servidor|api|studio> <saida>}" \
                "${4:?uso: --render-compose <root_env> <servidor|api|studio> <saida>}"
            ;;
        --render-postgres)
            platform_render_postgres_conf \
                "${2:?uso: platform_capacity.sh --render-postgres <root_env> <saida>}" \
                "${3:?uso: platform_capacity.sh --render-postgres <root_env> <saida>}"
            ;;
        *)
            echo "uso: platform_capacity.sh --report <root_env>" >&2
            echo "     platform_capacity.sh --render-postgres <root_env> <saida>" >&2
            exit 1
            ;;
    esac
fi
