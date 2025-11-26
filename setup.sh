#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

generate_postgres_password() {
  openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n'
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
        read -rp "IP ou Dominio do servidor: " server_ip

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

main() {
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

    SERVER_IP=$(get_server_ip)
    SERVER_IP=$(echo "$SERVER_IP" | xargs)
    # LOCAL_IP=$SERVER_IP
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

    cp servidor/.env.example servidor/.env

    sed -i "s|DB_ENC_KEY=pass|DB_ENC_KEY=$DB_ENC_KEY|g" servidor/.env
    sed -i "s|VAULT_ENC_KEY=pass|VAULT_ENC_KEY=$VAULT_ENC_KEY|g" servidor/.env
    sed -i "s|SECRET_KEY_BASE=pass|SECRET_KEY_BASE=$SECRET_KEY_BASE|g" servidor/.env
    sed -i "s|LOGFLARE_API_KEY=pass|LOGFLARE_API_KEY=$LOGFLARE_API_KEY|g" servidor/.env
    sed -i "s|FERNET_SECRET=pass|FERNET_SECRET=$SHARED_FERNET_SECRET|g" servidor/.env
    sed -i "s|NGINX_SHARED_TOKEN=pass|NGINX_SHARED_TOKEN=$SHARED_NGINX_TOKEN|g" servidor/.env
    sed -i "s|PROJECT_DELETE_PASSWORD=pass|PROJECT_DELETE_PASSWORD=$PROJECT_DELETE_PASSWORD|g" servidor/.env
    
    print_success "Arquivo servidor/.env configurado com sucesso!"

    print_status "Configurando servidor/secrets..."
    
    if [[ ! -f "servidor/secrets/.env.example" ]]; then
        print_error "Arquivo servidor/secrets/.env.example não encontrado!"
        exit 1
    fi
    
    JWT_SECRET=$(generate_jwt_secret)
    POSTGRES_PASSWORD=$(generate_postgres_password)

    cp servidor/secrets/.env.example servidor/secrets/.env
    
    sed -i "s|JWT_SECRET=pass|JWT_SECRET=$JWT_SECRET|g" servidor/secrets/.env
    sed -i "s|POSTGRES_PASSWORD=pass|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|g" servidor/secrets/.env
    
    print_success "Arquivo servidor/secrets/.env configurado com sucesso!"
    
    print_status "Configurando studio..."
    
    if [[ ! -f "studio/.env.example" ]]; then
        print_error "Arquivo studio/.env.example não encontrado!"
        exit 1
    fi
    
    COOKIE_SIGN_SECRET=$(generate_cookie_sign_secret)

    cp studio/.env.example studio/.env
    
    sed -i "s|FERNET_SECRET=pass|FERNET_SECRET=$SHARED_FERNET_SECRET|g" studio/.env
    sed -i "s|NGINX_SHARED_TOKEN=pass|NGINX_SHARED_TOKEN=$SHARED_NGINX_TOKEN|g" studio/.env
    sed -i "s|COOKIE_SIGN_SECRET=pass|COOKIE_SIGN_SECRET=$COOKIE_SIGN_SECRET|g" studio/.env
    if [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
    [[ "$SERVER_IP" =~ : ]]; then
        PROTO="http"
    else
        PROTO="https"
    fi 
    sed -i "s|^SERVER_DOMAIN=.*|SERVER_DOMAIN=${PROTO}://${SERVER_IP}|g" studio/.env
    sed -i "s|BACKEND_PROTO=pass|BACKEND_PROTO=$PROTO|g" studio/.env
    print_success "Arquivo studio/.env configurado com sucesso!"
    
    echo ""
    print_success "=== CONFIGURAÇÃO CONCLUÍDA ==="
    echo ""
    print_status "Arquivos configurados:"
    echo "  ✓ servidor/.env"
    echo "  ✓ servidor/secrets/.env"
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
    bash authelia.sh


    print_status "Configurando Nginx do Studio com o IP local detectado..."
    sed -i "s|server_name pass|server_name $LOCAL_IP|" studio/nginx/nginx.conf
    print_success "Nginx do Studio configurado para escutar em $LOCAL_IP."

    print_status "Configurando Authelia com o IP local..."

    local authelia_config="studio/authelia/configuration.yml"

    if [[ -f "$authelia_config" ]]; then
        print_status "Configurando Authelia com o IP local e segredos únicos..."
        
        sed -i "s|<SEU_IP>|$LOCAL_IP|g" "$authelia_config"

        local jwt_secret=$(generate_logflare_api_key)
        local session_secret=$(generate_logflare_api_key)
        local storage_key=$(generate_logflare_api_key)

        sed -i "s|JWT_SECRET|$jwt_secret|g" "$authelia_config"
        sed -i "s|SESSION_SECRET|$session_secret|g" "$authelia_config"
        sed -i "s|STORAGE_KEY|$storage_key|g" "$authelia_config"
        
        print_success "Arquivo de configuração do Authelia ($authelia_config) atualizado."
    else
        print_warning "Arquivo de configuração do Authelia ($authelia_config) não encontrado."
    fi
    print_status "Configurando a whitelist da api python "
    sed -i "s|<SEU_IP>/32|$LOCAL_IP/32|g" servidor/docker-compose-api.yml
    sed -i "s|<SEU_IP>|$LOCAL_IP|g" studio/docker-compose.yml
    print_success "Api python configurada para permitir esse ip $LOCAL_IP a consultar ela."
}
main

print_success "Script finalizado com sucesso!"
