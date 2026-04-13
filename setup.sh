#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TRANSACTION_DIR=".setup_transaction_$$"
MODIFIED_FILES=()

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

init_transaction() {
    mkdir -p "$TRANSACTION_DIR"
    print_status "Sistema de transação inicializado em $TRANSACTION_DIR"
}

backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
        cp "$file" "$backup_path"
        MODIFIED_FILES+=("$file")
        print_status "Backup criado: $file -> $backup_path"
    fi
}

safe_sed() {
    local pattern="$1"
    local file="$2"
    local temp_file="$TRANSACTION_DIR/temp_$(basename "$file")"
    
    if [[ ! " ${MODIFIED_FILES[@]} " =~ " ${file} " ]]; then
        backup_file "$file"
    fi

    sed "$pattern" "$file" > "$temp_file"
    
    if [[ $? -eq 0 ]]; then
        mv "$temp_file" "$file"
        return 0
    else
        print_error "Falha ao aplicar modificação em $file"
        return 1
    fi
}

commit_transaction() {
    if [[ -d "$TRANSACTION_DIR" ]]; then
        rm -rf "$TRANSACTION_DIR"
        print_success "Transação confirmada. Backups removidos."
    fi
}

rollback_transaction() {
    print_error "Erro detectado! Revertendo alterações..."
    
    if [[ -d "$TRANSACTION_DIR" ]]; then
        for file in "${MODIFIED_FILES[@]}"; do
            local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
            if [[ -f "$backup_path" ]]; then
                cp "$backup_path" "$file"
                print_status "Restaurado: $file"
            fi
        done
        rm -rf "$TRANSACTION_DIR"
        print_warning "Todas as alterações foram revertidas."
    fi
    
    exit 1
}

trap rollback_transaction ERR

generate_db_enc_key() {
    openssl rand -base64 12 | cut -c1-16
}

generate_vault_enc_key() {
    openssl rand -base64 32 | tr -d '\n' | head -c 32
}

generate_secret_key_base() {
    openssl rand -base64 32 | tr -d '\n' | head -c 48
}

generate_logflare_api_key() {
    head -c 32 /dev/urandom | base64
}

generate_cookie_sign_secret() {
    openssl rand -base64 32 | tr -d '\n'
}

generate_jwt_secret() {
    openssl rand -base64 64 | tr -d '\n'
}

generate_push_worker_token() {
    openssl rand -hex 32
}

generate_postgres_password() {
  openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n'
}

generate_user_realtime() {
  echo "user_$(openssl rand -hex 4)"
}

generate_realtime_dashboard_pass(){
  openssl rand -base64 32 | tr -d '\n'
}

validate_input() {
    local input="$1"
    if [[ $input =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "ip"
    elif [[ $input =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$ ]]; then
        echo "domain"
    else
        echo "invalid"
    fi
}
validate_ip() {
    local ip="$1"
    local IFS='.'
    local -a octets=($ip)
    
    if [[ ${#octets[@]} -ne 4 ]]; then
        return 1
    fi

    for octet in "${octets[@]}"; do
        if ! [[ "$octet" =~ ^[0-9]+$ ]] || [ "$octet" -lt 0 ] || [ "$octet" -gt 255 ]; then
            return 1
        fi
    done
    
    return 0
}
get_server_ip() {
    local server_ip
    local validation_result
    
    while true; do
        read -rp "IP ou Dominio do servidor principal (Traefik/API/projetos): " server_ip

        server_ip=$(echo "$server_ip" | xargs)
        
        if [[ -z "$server_ip" ]]; then
            print_error "Entrada não pode estar vazia. Tente novamente." >&2
            continue
        fi

        if [[ "$server_ip" == "127.0.0.1" || "$server_ip" == "localhost" ]]; then
            print_error "Uso de 'localhost' ou '127.0.0.1' não é permitido. Digite um IP da rede ou domínio válido." >&2
            continue
        fi
        if [[ $server_ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            if validate_ip "$server_ip"; then
                print_success "✓ IP válido: $server_ip" >&2
                break
            else
                print_error "IP inválido." >&2
                continue
            fi
        elif [[ $server_ip =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$ ]]; then
            if [[ $server_ip =~ \.$$ ]]; then
                print_error "Domínio não pode terminar com ponto." >&2
                continue
            fi
            print_success "✓ Domínio válido: $server_ip" >&2
            break
        else
            print_error "Formato inválido. Digite um IP válido (ex: 192.168.1.100), domínio (ex: meusite.com)" >&2
            continue
        fi
    done
    
    echo "$server_ip"
}

confirm_network_topology() {
    local local_ip="$1"
    local server_ip="$2"
    local answer

    echo ""
    print_status "Resumo da topologia detectada:"
    echo "  - IP local desta maquina (Studio/Authelia/Nginx): $local_ip"
    echo "  - IP ou dominio digitado para o servidor principal: $server_ip"
    echo ""
    echo "Como o setup usa esses valores:"
    echo "  - O valor digitado vai para SERVER_URL e SERVER_DOMAIN"
    echo "  - Ele representa a maquina do servidor principal (Traefik/API/projetos)"
    echo "  - O IP local detectado fica para o Studio local, certificados e PUSH_API_URL"
    echo ""

    if [[ "$server_ip" == "$local_ip" ]]; then
        print_warning "Voce digitou o mesmo IP da maquina local."
        echo "  Isso prepara o ambiente para rodar servidor principal e Studio na mesma maquina."
        echo "  Se depois voce mover o Studio ou o servidor para outra maquina, normalmente basta ajustar os arquivos .env e recriar os containers envolvidos."
    else
        print_status "Voce esta configurando uma topologia com Studio local e servidor principal em outro host."
        echo "  Isso e o esperado quando a interface administrativa roda em uma maquina e os projetos/API em outra."
    fi

    echo ""
    while true; do
        read -rp "Confirmar essa configuracao de rede? [s/N]: " answer
        answer=$(echo "$answer" | xargs | tr '[:upper:]' '[:lower:]')

        case "$answer" in
            s|sim)
                return 0
                ;;
            n|nao|"")
                print_error "Configuracao cancelada pelo usuario."
                exit 1
                ;;
            *)
                print_warning "Resposta invalida. Digite 's' para confirmar ou 'n' para cancelar."
                ;;
        esac
    done
}

main() {
    init_transaction
    
    print_status "Iniciando configuração do ambiente..."

    if [[ ! -d "servidor" ]]; then
        print_error "Pasta 'servidor' não encontrada!"
        exit 1
    fi
    
    if [[ ! -d "studio" ]]; then
        print_error "Pasta 'studio' não encontrada!"
        exit 1
    fi
    print_status "Detectando IP local da máquina..."
    LOCAL_IP=$(ip route get 8.8.8.8 | awk '{print $7; exit}')

    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}') 
    fi

    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP=$(hostname -I | awk '{print $1}')
    fi
    
    if [ -z "$LOCAL_IP" ]; then
        print_error "Não foi possível detectar o IP local da máquina automaticamente. Verifique a conexão de rede."
        exit 1
    fi

    print_success "IP local detectado: $LOCAL_IP"
    print_status "Gerando chaves compartilhadas..."

    SHARED_FERNET_SECRET=$(generate_logflare_api_key)
    SHARED_NGINX_TOKEN=$(generate_logflare_api_key)
    PUSH_WORKER_TOKEN=$(generate_push_worker_token)

    SERVER_IP=$(get_server_ip)
    SERVER_IP=$(echo "$SERVER_IP" | xargs)
    confirm_network_topology "$LOCAL_IP" "$SERVER_IP"
    print_status "Configurando servidor principal..."
    
    if [[ ! -f "servidor/.env.example" ]]; then
        print_error "Arquivo servidor/.env.example não encontrado!"
        exit 1
    fi

    DB_ENC_KEY=$(generate_db_enc_key)
    VAULT_ENC_KEY=$(generate_vault_enc_key)
    SECRET_KEY_BASE=$(generate_secret_key_base)
    LOGFLARE_API_KEY=$(generate_logflare_api_key)
    PROJECT_DELETE_PASSWORD=$(generate_jwt_secret)
    DASHBOARD_USER=$(generate_user_realtime)
    DASHBOARD_PASSWORD=$(generate_realtime_dashboard_pass)
    JWT_SECRET=$(generate_jwt_secret)
    POSTGRES_PASSWORD=$(generate_postgres_password)

    cp servidor/.env.example servidor/.env

    safe_sed "s|POSTGRES_PASSWORD=pass|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|g" servidor/.env
    safe_sed "s|DB_ENC_KEY=pass|DB_ENC_KEY=$DB_ENC_KEY|g" servidor/.env
    safe_sed "s|VAULT_ENC_KEY=pass|VAULT_ENC_KEY=$VAULT_ENC_KEY|g" servidor/.env
    safe_sed "s|SECRET_KEY_BASE=pass|SECRET_KEY_BASE=$SECRET_KEY_BASE|g" servidor/.env
    safe_sed "s|LOGFLARE_API_KEY=pass|LOGFLARE_API_KEY=$LOGFLARE_API_KEY|g" servidor/.env
    safe_sed "s|JWT_SECRET=pass|JWT_SECRET=$JWT_SECRET|g" servidor/.env
    safe_sed "s|FERNET_SECRET=pass|FERNET_SECRET=$SHARED_FERNET_SECRET|g" servidor/.env
    safe_sed "s|NGINX_SHARED_TOKEN=pass|NGINX_SHARED_TOKEN=$SHARED_NGINX_TOKEN|g" servidor/.env
    safe_sed "s|PUSH_WORKER_TOKEN=pass|PUSH_WORKER_TOKEN=$PUSH_WORKER_TOKEN|g" servidor/.env
    safe_sed "s|PROJECT_DELETE_PASSWORD=pass|PROJECT_DELETE_PASSWORD=$PROJECT_DELETE_PASSWORD|g" servidor/.env
    if [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
    [[ "$SERVER_IP" =~ : ]]; then
        PROTO="http"
    else
        PROTO="https"
    fi
    safe_sed "s|SERVER_URL=pass|SERVER_URL=${SERVER_IP}|g" servidor/.env
    safe_sed "s|SERVER_PROTO=pass|SERVER_PROTO=${PROTO}|g" servidor/.env
    safe_sed "s|^PUSH_API_URL=.*|PUSH_API_URL=https://${LOCAL_IP}:4000/api/internal/push|g" servidor/.env
    safe_sed "s|PUSH_VERIFY_TLS=true|PUSH_VERIFY_TLS=true|g" servidor/.env
    safe_sed "s|PUSH_CA_FILE=/docker/push-certs/ca.pem|PUSH_CA_FILE=/docker/push-certs/ca.pem|g" servidor/.env
    safe_sed "s|DASHBOARD_USER=pass|DASHBOARD_USER=${DASHBOARD_USER}|g" servidor/.env
    safe_sed "s|DASHBOARD_PASSWORD=pass|DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}|g" servidor/.env
    print_success "Arquivo servidor/.env configurado com sucesso!"

    print_status "Configurando studio..."
    
    if [[ ! -f "studio/.env.example" ]]; then
        print_error "Arquivo studio/.env.example não encontrado!"
        exit 1
    fi
    
    COOKIE_SIGN_SECRET=$(generate_cookie_sign_secret)
    POSTGRES_NGINX_PASSWORD=$(generate_postgres_password)

    cp studio/.env.example studio/.env
    safe_sed "s|FERNET_SECRET=pass|FERNET_SECRET=$SHARED_FERNET_SECRET|g" studio/.env
    safe_sed "s|NGINX_SHARED_TOKEN=pass|NGINX_SHARED_TOKEN=$SHARED_NGINX_TOKEN|g" studio/.env
    safe_sed "s|PUSH_WORKER_TOKEN=pass|PUSH_WORKER_TOKEN=$PUSH_WORKER_TOKEN|g" studio/.env
    safe_sed "s|COOKIE_SIGN_SECRET=pass|COOKIE_SIGN_SECRET=$COOKIE_SIGN_SECRET|g" studio/.env
    safe_sed "s|POSTGRES_NGINX_PASSWORD=pass|POSTGRES_NGINX_PASSWORD=$POSTGRES_NGINX_PASSWORD|g" studio/.env
    safe_sed "s|^SERVER_DOMAIN=.*|SERVER_DOMAIN=${PROTO}://${SERVER_IP}|g" studio/.env
    safe_sed "s|BACKEND_PROTO=pass|BACKEND_PROTO=$PROTO|g" studio/.env
    print_success "Arquivo studio/.env configurado com sucesso!"
    
    echo ""
    print_success "=== CONFIGURAÇÃO CONCLUÍDA ==="
    echo ""
    print_status "Arquivos configurados:"
    echo "  ✓ servidor/.env"
    echo "  ✓ studio/.env"
    echo ""
    print_status "Chaves compartilhadas configuradas:"
    echo "  - FERNET_SECRET (servidor e studio)"
    echo "  - NGINX_SHARED_TOKEN (servidor e studio)"
    echo ""
    if [[ "$PROTO" == "http" ]]; then
        IP_DOMAIN="IP"
    else
        IP_DOMAIN="Dominio"
    fi
    print_status "$IP_DOMAIN do servidor configurado: $SERVER_IP"
    echo ""

    print_status "Gerando certificados SSL autoassinados para o Studio/Authelia..."
    bash authelia.sh "$LOCAL_IP"

    print_status "Copiando certificado do Studio para o servidor Python..."
    mkdir -p servidor/certs
    backup_file "servidor/certs/ca.pem"
    cp studio/authelia/ssl/ca.pem servidor/certs/ca.pem
    print_success "Certificado copiado para servidor/certs/ca.pem"


    print_status "Configurando Nginx do Studio com o IP local detectado..."
    backup_file "studio/nginx/nginx.conf"
    safe_sed "s|server_name pass|server_name $LOCAL_IP|" studio/nginx/nginx.conf
    print_success "Nginx do Studio configurado para escutar em $LOCAL_IP."

    print_status "Configurando Authelia com o IP local..."

    local authelia_config="studio/authelia/configuration.yml"

    if [[ -f "$authelia_config" ]]; then
        print_status "Configurando Authelia com o IP local e segredos únicos..."
        
        backup_file "$authelia_config"
        safe_sed "s|<SEU_IP>|$LOCAL_IP|g" "$authelia_config"

        local jwt_secret=$(generate_logflare_api_key)
        local session_secret=$(generate_logflare_api_key)
        local storage_key=$(generate_logflare_api_key)

        safe_sed "s|JWT_SECRET|$jwt_secret|g" "$authelia_config"
        safe_sed "s|SESSION_SECRET|$session_secret|g" "$authelia_config"
        safe_sed "s|STORAGE_KEY|$storage_key|g" "$authelia_config"
        
        print_success "Arquivo de configuração do Authelia ($authelia_config) atualizado."
    else
        print_warning "Arquivo de configuração do Authelia ($authelia_config) não encontrado."
    fi
    print_status "Configurando a whitelist da api python "
    backup_file "servidor/docker-compose-api.yml"
    safe_sed "s|<SEU_IP>/32|$LOCAL_IP/32|g" servidor/docker-compose-api.yml
    print_status "Configurando update_geoip.sh com o caminho real..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    backup_file "servidor/traefik/update_geoip.sh"
    safe_sed "s|seucaminho|$SCRIPT_DIR|g" servidor/traefik/update_geoip.sh
    safe_sed "s|HOST_PROJECT_ROOT=\"pass\"|HOST_PROJECT_ROOT=\"$SCRIPT_DIR\"|g" servidor/.env

    backup_file "studio/docker-compose.yml"
    safe_sed "s|<SEU_IP>|$LOCAL_IP|g" studio/docker-compose.yml
    print_success "Api python configurada para permitir esse ip $LOCAL_IP a consultar ela."
    print_success "Script update_geoip.sh configurado com o caminho: $SCRIPT_DIR"
    
    commit_transaction
}
main

print_success "Script finalizado com sucesso!"
