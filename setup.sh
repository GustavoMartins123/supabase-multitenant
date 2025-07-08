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

generate_fernet_secret() {
    openssl rand -base64 64 | tr -d '\n'
}

generate_jwt_secret() {
    openssl rand -base64 64 | tr -d '\n'
}

generate_postgres_password() {
  openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n'
}

generate_cookie_sign_secret() {
    openssl rand -base64 32 | tr -d '\n'
}

get_server_ip() {
  read -rp "IP ou Dominio do servidor: " server_ip
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

    print_status "Gerando chaves compartilhadas..."
    SHARED_FERNET_SECRET=$(generate_fernet_secret)
    SHARED_NGINX_TOKEN=$(generate_fernet_secret)

    SERVER_IP=$(get_server_ip)
    SERVER_IP=$(echo "$SERVER_IP" | xargs)

    print_status "Configurando servidor principal..."
    
    if [[ ! -f "servidor/.env.example" ]]; then
        print_error "Arquivo servidor/.env.example não encontrado!"
        exit 1
    fi

    DB_ENC_KEY=$(generate_db_enc_key)
    VAULT_ENC_KEY=$(generate_vault_enc_key)
    SECRET_KEY_BASE=$(generate_secret_key_base)
    LOGFLARE_API_KEY=$(generate_logflare_api_key)
    PROJECT_DELETE_PASSWORD=$(generate_fernet_secret)

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
    if [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$SERVER_IP" =~ : ]]; then
        PROTO="http"         # IPv4 ou IPv6 → HTTP    
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
}

if [[ $EUID -eq 0 ]]; then
    print_warning "Executando como root. Certifique-se de que isso é necessário."
fi

main

print_success "Script finalizado com sucesso!"