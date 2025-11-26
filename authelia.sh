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

main() {
    local SSL_DIR="studio/authelia/ssl"
    
    local ABSOLUTE_SSL_DIR
    ABSOLUTE_SSL_DIR="$(pwd)/$SSL_DIR"
    
    print_status "Diretório de destino dos certificados: $ABSOLUTE_SSL_DIR"

    print_status "Executando o container do Authelia para criar os arquivos..."
    if docker run --rm -u "$(id -u):$(id -g)" -v "$ABSOLUTE_SSL_DIR:/data/authelia/keys" authelia/authelia:4.39 authelia crypto certificate rsa generate --common-name "authelia" --directory /data/authelia/keys; then
        print_success "Certificados gerados com sucesso pelo Authelia."
    else
        print_warning "Primeira tentativa falhou. Limpando e tentando novamente..."
 
        if [[ -d "$ABSOLUTE_SSL_DIR" ]]; then
            rm -rf "$ABSOLUTE_SSL_DIR"
            print_status "Diretório deletado: $ABSOLUTE_SSL_DIR"
        fi
        
        mkdir -p "$ABSOLUTE_SSL_DIR"
        print_status "Diretório recriado e tentando novamente..."

        if docker run --rm -v "$ABSOLUTE_SSL_DIR:/data/authelia/keys" authelia/authelia:4.39 authelia crypto certificate rsa generate --common-name "authelia" --directory /data/authelia/keys; then
            print_success "Certificados gerados com sucesso pelo Authelia (fallback)."
            chmod 755 "$ABSOLUTE_SSL_DIR"
        else
            print_error "Falha ao executar o container do Authelia mesmo após fallback. Verifique se o Docker está em execução."
            exit 1
        fi
    fi

    print_status "Renomeando arquivos para 'public.crt' e 'private.pem'..."
    
    if [[ -f "$SSL_DIR/private.pem" && -f "$SSL_DIR/public.crt" ]]; then
        mv "$SSL_DIR/public.crt" "$SSL_DIR/ca.pem"
        mv "$SSL_DIR/private.pem" "$SSL_DIR/ca.key"
        print_success "Arquivos renomeados com sucesso."
    else
        print_error "Os arquivos de certificado (private.pem, public.crt) não foram encontrados após a geração."
        exit 1
    fi
}
main