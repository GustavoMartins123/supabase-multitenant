## Setup https

Por padrão, a plataforma é configurada para rodar em um ambiente de desenvolvimento local usando HTTP. Os passos a seguir habilitam o Traefik para operar em HTTPS, gerando certificados SSL automaticamente com Let's Encrypt.

### ⚠️ Pré-requisitos

Antes de prosseguir, certifique-se de que:

- **Domínio válido**: Você possui um domínio registrado apontando para o IP do seu servidor
- **DNS configurado**: O domínio está propagado e acessível pela internet
- **Portas abertas**: As portas 80 e 443 estão liberadas no firewall/cloud provider
> **Importante**: O Let's Encrypt só funciona com domínios válidos e publicamente acessíveis. Para desenvolvimento local, continue usando HTTP ou configure certificados auto-assinados.

---

### Passo 1: Habilitar TLS no `traefik.yml`

Para que o Traefik possa gerar e armazenar os certificados SSL do Let's Encrypt, precisamos primeiro ajustar as permissões do arquivo de armazenamento e depois editar sua configuração principal.

**1.1. Ajustar Permissões do `acme.json` (Passo Crítico)**

Execute o seguinte comando dentro da pasta `servidor/traefik/` para garantir que o Traefik tenha permissão para gerenciar os certificados de forma segura.

```bash
# Define as permissões restritivas (apenas o proprietário pode ler/escrever)
chmod 600 acme.json
```

Agora, abra o arquivo `servidor/traefik/traefik.yml` e faça as seguintes alterações:

**1.2. Ativar Redirecionamento para HTTPS**

Esta configuração instrui o Traefik a redirecionar todo o tráfego da porta 80 (HTTP) para a porta 443 (HTTPS).

* **Encontre** a seção `entryPoints` e **substitua-a** pelo bloco abaixo para ativar o redirecionamento e a porta `websecure`:

    ```yaml
    entryPoints:
      web:
        address: ":80"
        http:
          redirections:
            entryPoint:
              to: websecure
              scheme: https
      websecure:
        address: ":443"
    ```

**1.3. Configurar o Provedor de Certificados (Let's Encrypt)**

Isso informa ao Traefik como obter os certificados SSL.

* **Adicione** o seguinte bloco ao final do arquivo. **Lembre-se de trocar `seuemail@email.com` pelo seu email.**

    ```yaml
    certificatesResolvers:
      letsencrypt:
        acme:
          email: seuemail@email.com
          storage: /acme.json
          keyType: EC256
          httpChallenge:
            entryPoint: web
    ```

**1.4. Definir Padrões de Segurança TLS (Opcional, mas recomendado)**

Este bloco garante que apenas cifras de criptografia modernas e seguras sejam utilizadas.

* **Adicione** o seguinte bloco ao final do arquivo:

    ```yaml
    tls:
      options:
        default:
          minVersion: "VersionTLS12"
          cipherSuites:
            - "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384"
            - "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
            - "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305"
            - "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305"
            - "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256"
            - "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
          curvePreferences:
            - "secp521r1"
            - "secp384r1"
    ```

> 💡 **Nota de compatibilidade**: Restringir a versão mínima para `VersionTLS12` e limitar as cifras garante excelente segurança e pontuação máxima em auditorias (como SSL Labs), mas pode impedir a conexão de clientes muito antigos ou dispositivos legados (como sistemas embarcados obsoletos). Se a sua regra de negócio exige suporte a esses dispositivos, você pode remover ou flexibilizar essa configuração.

---

### Passo 2: Ajustar Headers de Segurança no `middlewares.yml`

Para produção, é crucial enviar o header `Strict-Transport-Security` (HSTS), que força o navegador a usar HTTPS.

* Abra o arquivo `servidor/traefik/middlewares.yml`.
* **Encontre** o middleware `security-headers` e **substitua-o completamente** pela versão abaixo:

    ```yaml
    # Substitua o middleware 'security-headers' existente por este:
    security-headers:
      headers:
        customRequestHeaders:
          X-Forwarded-Proto: "https"
        customResponseHeaders:
          X-Frame-Options: "DENY"
          X-Content-Type-Options: "nosniff"
          X-XSS-Protection: "1; mode=block"
          Strict-Transport-Security: "max-age=31536000; includeSubDomains; preload" 
          Content-Security-Policy: "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'"
          Referrer-Policy: "strict-origin-when-cross-origin"
    ```

> ⚠️ **Atenção: Ajuste conforme suas regras de negócio!**
> Os cabeçalhos (headers) de segurança padrão acima são rígidos e seguros, mas podem ser restritivos ("engessados") dependendo do seu projeto:
>
> * **`Content-Security-Policy` (CSP)**:
>   * **O que faz:** Impede que o navegador carregue scripts, imagens, fontes ou faça requisições de/para domínios que não sejam o próprio (`'self'`).
>   * **Quando ajustar:** Se o seu aplicativo usa APIs externas (ex: Stripe, Google Maps), fontes do Google Fonts, ou se você usa o Supabase Storage para exibir imagens hospedadas em outros buckets/domínios, o CSP bloqueará o carregamento. Você precisará adicionar os domínios permitidos nas diretivas apropriadas (ex: `img-src 'self' data: https://*.supabase.co; connect-src 'self' https://api.seuservico.com`). Se estiver na fase inicial de desenvolvimento ou testes, você pode desativar temporariamente este cabeçalho ou usar `Content-Security-Policy-Report-Only` para auditar os bloqueios sem impedir o funcionamento da aplicação.
> * **`Strict-Transport-Security` (HSTS)**:
>   * **O que faz:** Obriga o navegador a sempre usar HTTPS para o domínio atual e todos os seus subdomínios (`includeSubDomains; preload`) durante 1 ano (`max-age=31536000`).
>   * **Cuidado:** Uma vez ativo e enviado ao cabeçalho com `preload`, se você tiver subdomínios legados ou outros serviços que ainda precisem rodar sem HTTPS, eles se tornarão totalmente inacessíveis. Recomenda-se começar com um `max-age` menor e sem `preload` ou `includeSubDomains` durante a fase de testes e homologação (ex: `"max-age=63072000"`).
> * **`X-Frame-Options`**:
>   * **O que faz:** Evita ataques de clickjacking impedindo que seu site seja renderizado dentro de um `<iframe>`.
>   * **Quando ajustar:** Se você planeja integrar o painel ou partes da sua aplicação dentro de outras plataformas suas via iframe, altere de `"DENY"` para `"SAMEORIGIN"`, ou use a diretiva `frame-ancestors` no CSP.

---

### Passo 3: Atualizar os Roteadores em middlewares.yml

* Abra o arquivo servidor/traefik/middlewares.yml.

* Ajuste os entrypoints: Para cada roteador (malicious-paths, block-bad-useragents e http-catchall), adicione `- websecure` a lista de `entryPoints` e adicione a chave `tls: {}`.

* Exemplo para o roteador malicious-paths:

ANTES:
```yml
    malicious-paths:
      rule: "..."
      entryPoints:
        - web
      priority: 2000
      middlewares:
        - malicious-paths-chain
      service: forbidden-service
```
DEPOIS:
```yml
    malicious-paths:
      rule: "..."
      entryPoints:
        - web
        - websecure
      tls: {}
      priority: 2000
      middlewares:
        - malicious-paths-chain
      service: forbidden-service
```
* Essa etapa vale da mesma forma para os roteadores 'block-bad-useragents' e 'http-catchall'.

**3.1. Roteador da API de Projetos (projects-api)**

* Abra o arquivo servidor/traefik/render_dynamic_config.py.
* Encontre o bloco que monta o roteador "projects-api".

ANTES:
```python
        "      entryPoints:",
        "        - web",
        "      priority: 1000",
```
DEPOIS:
```python
        "      entryPoints:",
        "        - web",
        "        - websecure",
        "      tls: {}",
        "      priority: 1000",
```

## Passo 4: Configurar os Roteadores dos Projetos para HTTPS

* Esta é a etapa final para expor suas aplicações Supabase de forma segura.

* No mesmo arquivo servidor/traefik/render_dynamic_config.py, encontre o bloco que monta o roteador "project-{project_id}". Como esse roteador é gerado dinamicamente para todos os projetos a partir do conteúdo de projects/, essa edição já vale tanto para os projetos existentes quanto para os que forem criados depois.

ANTES:
```python
                "      entryPoints:",
                "        - web",
                "      priority: 500",
```
DEPOIS:
```python
                "      entryPoints:",
                "        - web",
                "        - websecure",
                "      tls: {}",
                "      priority: 500",
```

## Passo 5: Aplicar as Configurações Finais

Após salvar todas as alterações nos arquivos *.yml, reinicie os contêineres para que as novas regras sejam aplicadas.

Execute os seguintes comandos a partir da pasta raiz do seu projeto.

**5.1. Atualize o Ambiente do Servidor de Gerenciamento (Studio)**

O Nginx do Studio precisa saber que o backend agora opera em HTTPS.

* Abra o arquivo studio/.env.

* Altere as seguintes variáveis para apontar para seu domínio e usar o protocolo https:

ANTES:
```bash
SERVER_DOMAIN=http://<seu_ip_local>
BACKEND_PROTO=http
```
DEPOIS:
```
SERVER_DOMAIN=https://seu.dominio.real
BACKEND_PROTO=https
```

**5.2. Reinicie Todos os Serviços**

Os comandos abaixo forçam a recriação dos contêineres, garantindo que eles usem os novos arquivos .yml e .env que você modificou.

Reinicie o Gateway de Borda (Traefik), o watcher da configuração dinâmica e de permissão para escrita ao arquivo 'acme.json':

```bash
# Aplica as novas configurações de HTTPS e resolvedores de certificado.
docker compose -f servidor/traefik/docker-compose.yml up -d --force-recreate
```

Reinicie a Interface de Gerenciamento (Studio):

```bash
# Aplica as novas variáveis de ambiente para o backend.
docker compose -f studio/docker-compose.yml up -d --force-recreate
```
