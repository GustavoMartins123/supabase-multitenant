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

---

### Passo 3: Atualizar os Labels do Docker Compose

* Abra o arquivo servidor/traefik/docker-compose.yml.

* Ajuste os entrypoints: Para cada roteador (malicious-paths e block-bad-useragents), comente a linha que aponta apenas para web e descomente a que aponta para web,websecure.

* Habilite o TLS: Descomente a linha tls=true para cada um desses roteadores.

* Ative o HTTPS Catch-all: Descomente o bloco inteiro do roteador https-catchall no final da lista de labels.

* Exemplo para o roteador malicious-paths:

ANTES:
```yml
# - "traefik.http.routers.malicious-paths.entrypoints=web,websecure"
- "traefik.http.routers.malicious-paths.entrypoints=web"
# ...
# - "traefik.http.routers.malicious-paths.tls=true"
```
DEPOIS:
```yml
- "traefik.http.routers.malicious-paths.entrypoints=web,websecure"
# - "traefik.http.routers.malicious-paths.entrypoints=web"
# ...
- "traefik.http.routers.malicious-paths.tls=true"
```
* Essa etapa vale da mesma forma para o bloco logo abaixo, o 'block-bad-useragents'

**3.1. Adicionar o Roteador HTTPS Catch-all**

Este roteador funciona como uma "rede de segurança" para conexões HTTPS, capturando qualquer tentativa de acesso a domínios não configurados e aplicando as mesmas políticas de segurança.

* **Cole** no final do bloco `labels`:

```yml
 - "traefik.http.routers.https-catchall.rule=HostRegexp(`{host:.+}`)"
 - "traefik.http.routers.https-catchall.entrypoints=websecure"
 - "traefik.http.routers.https-catchall.priority=100"
 - "traefik.http.routers.https-catchall.middlewares=security-chain-enhanced@file"
 - "traefik.http.routers.https-catchall.tls=true"
 - "traefik.http.routers.https-catchall.service=noop@internal"
```
Importante: Este roteador complementa o http-catchall existente, garantindo que tanto conexões HTTP quanto HTTPS não autorizadas sejam tratadas com as mesmas políticas de segurança.

**3.2. Roteador da API de Projetos (projects-api)**

Para garantir que a api que gerencia os projetos responda a partir do dominio faça o seguinte:
 
* Edite o arquivo que fica em "servidor/docker-compose.yml"
* Role até achar o "projects-api"
* Edite as labels

```yml
labels:
  - traefik.enable=true
  - traefik.http.middlewares.lanonly.ipallowlist.sourcerange=<SEU_IP>/32, 172.20.0.0/16
  - traefik.http.routers.projects.rule=PathPrefix(`/api/projects`)
  - traefik.http.routers.projects.middlewares=lanonly, api-security-chain@file
  - traefik.http.services.projects.loadbalancer.server.port=18000  
```

DEPOIS:
```yml
labels:
  - traefik.http.middlewares.lanonly.ipallowlist.sourcerange=<SEU_IP>/32, 172.20.0.0/16
  - traefik.http.routers.projects.rule=Host(`seu_dominio`) && PathPrefix(`/api/projects`)
  - traefik.http.routers.projects.priority=100
  - traefik.http.routers.projects.entrypoints=websecure
  - traefik.http.routers.projects.tls=true
  - traefik.http.routers.projects.tls.certresolver=letsencrypt
  - traefik.http.routers.projects.middlewares=lanonly, api-security-chain@file
  - traefik.http.services.projects.loadbalancer.server.port=18000
```

Nota: troque 'seu_dominio' pelo dominio real que será usado.

## Passo 4: Configurar os Roteadores dos Projetos para HTTPS

* Esta é a etapa final para expor suas aplicações Supabase de forma segura.

**4.1. Para Novos Projetos (Editando o Template)**

* Para garantir que todos os projetos criados a partir de agora já nasçam configurados para HTTPS, você deve editar o arquivo de template que o script generate_project.sh utiliza.

    Abra o arquivo: servidor/generateProject/dockercomposetemplate.

    Edite os labels do serviço nginx para que fiquem como no exemplo "DEPOIS" abaixo.

```yml
labels:
  - "traefik.enable=true"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.rule=Host(`seu_dominio`) && PathPrefix(`/{{project_id}}`)"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.entrypoints=websecure"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.tls=true"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.tls.certresolver=letsencrypt"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.rule=PathPrefix(`/{{project_id}}`)"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.entrypoints=web"
  # ...
```

DEPOIS:
```yml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.rule=Host(`seu_dominio`) && PathPrefix(`/{{project_id}}`)"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.entrypoints=websecure"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.tls=true"
  - "traefik.http.routers.supabase-nginx-{{project_id}}.tls.certresolver=letsencrypt"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.rule=PathPrefix(`/{{project_id}}`)"
  # - "traefik.http.routers.supabase-nginx-{{project_id}}.entrypoints=web"
  # ...
```
Nota: troque 'seu_dominio' pelo dominio real que será usado.

**4.2. Para Projetos Existentes (Editando Manualmente)**

Se você já possui projetos que foram criados com a configuração HTTP, é necessário atualizá-los manualmente para que usem HTTPS.

* Navegue até a pasta do projeto que deseja migrar (ex: projects/meu_projeto_antigo/).

* Abra o arquivo docker-compose.yml.

* Aplique as exatamente as mesmas alterações descritas na seção [4.1](#41-para-novos-projetos-editando-o-template) acima: comente as linhas de configuração HTTP e descomente as linhas de HTTPS, inserindo seu domínio na regra Host(...).

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

Os comandos abaixo forçam a recriação dos contêineres, garantindo que eles usem os novos labels e arquivos .env que você modificou.

* Reinicie os Serviços Base do Servidor:

```bash
# Inicia o PostgreSQL, a API de gerenciamento, etc.
docker compose -f servidor/docker-compose.yml --env-file servidor/secrets/.env --env-file servidor/.env up -d --force-recreate
```
Reinicie o Gateway de Borda (Traefik) e de permissão para escrita ao arquivo 'acme.json':

```bash
# Aplica as novas configurações de HTTPS e resolvedores de certificado.
docker compose -f servidor/traefik/docker-compose.yml up -d --force-recreate
```

Reinicie a Interface de Gerenciamento (Studio):

```bash
# Aplica as novas variáveis de ambiente para o backend.
docker compose -f studio/docker-compose.yml up -d --force-recreate
```

Reinicie o Projeto Existente que foi Modificado:
```bash
# Aplica os novos labels de HTTPS ao projeto. Substitua nos dois <seu_projeto> pelo nome real.
docker compose -f projects/<seu_projeto>/docker-compose.yml -p <seu_projeto> --env-file servidor/secrets/.env --env-file servidor/.env --env-file projects/<seu_projeto>/.env up -d --force-recreate
```