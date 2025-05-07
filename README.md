# Documentação Supabase-Traefik-Nginx

## Visão geral

Este script **automatiza** a criação de múltiplos projetos Supabase em um único host, configurando
automaticamente os serviços **Realtime** e **Pooler** de cada instância.

---

## Sumário

- [Visão geral](#visão-geral)  
- [Propósito](#propósito)  
- [Pré-requisitos](#pré-requisitos)  

### Como Usar  
- [1. Clonar o repositório](#1-clonar-o-repositório)  
- [2. Subir o banco base](#2-subir-o-banco-base)  
- [3. Gerar o template _supabase_template](#3-gerar-o-template-_supabase_template)  
- [4. Executar o gerador de projetos](#4-executar-o-gerador-de-projetos)  
- [5. Levantando o projeto gerado](#5-levantando-o-projeto-gerado)  

### Configurações Adicionais  
- [Observações](#observações)  
- [6. Subindo o Traefik](#6-subindo-o-traefik)  
- [7. Subindo o Supabase Studio](#7-subindo-o-supabase-studio)  

### Extras  
- [8. Configuração opcional: JWT Secret por projeto](#8-configuração-opcional-jwt-secret-por-projeto)  
- [9. Solução de Problemas](#9-solução-de-problemas)  
- [Algumas observações importantes](#algumas-observações-importantes)  

## Propósito

Simplificar a inicialização de projetos Supabase, criando automaticamente:

- Um **database dedicado** para o projeto.  
- Configurações de **tenants** para Realtime e Pooler.  
- Arquivos de configuração para **NGINX**, variáveis de ambiente e **Docker Compose**.  

---

## Pré-requisitos

| Item | Descrição |
|------|-----------|
| Docker & Docker Compose | Instalados e funcionando. |
| Usuario    |   Com permissão para rodar comandos docker. |
| jq    |   Instalado na maquina. |

---

## Como Usar

### 1. Clonar o repositório

```bash
git clone git@github.com:GustavoMartins123/Supabase-Traefik-Nginx.git
cd Supabase-Traefik-Nginx
```
### 2. Subir o banco base

dentro da pasta docker/    
```bash
docker compose  --env-file secrets/.env   --env-file .env up -d
```
Altere os valores em secrets/.env e .env antes de subir.

### 3. Gerar o template _supabase_template

Assim que o Postgres estiver no ar, o script create_template.sh (pasta docker/) tentará criar o template automaticamente.

Verifique se ele existe:
```bash
docker exec -it supabase-db bash
psql -U supabase_admin
\l   # lista os bancos; procure _supabase_template
```
Caso de erro ao usar '\l' -> 'sh: 1: less: not found' rode:
```bash
exit
apt update
apt install -y less

psql -U supabase_admin
\l
```
Caso não apareça, rode manualmente dentro do contêiner:
```bash
cd docker-entrypoint-initdb.d/

chmod +x zzz-create_template.sh

./zzz-create_template.sh
```
### 4. Executar o gerador de projetos

Para gerar um novo projeto navegue até a pasta 'docker/generateProject'

```bash
cd docker/generateProject
```

Execute o script fornecendo um identificador para o projeto:

```bash
./generate_project.sh <PROJECT_ID>
```
O que é <PROJECT_ID>?

    Ele será o nome da pasta gerada e também o identificador usado para os serviços criados pelo script.

Atenção:

    Evite usar caracteres especiais no <PROJECT_ID>, exceto o underscore (_). O PostgreSQL não aceita nomes com outros símbolos.

Pré-requisitos

Antes de executar o script, verifique se o usuário da máquina possui as permissões necessárias para rodar o Docker:

Adicione o usuário ao grupo Docker com o comando:
```bash
sudo usermod -aG docker $USER
```
Reinicie o computador para aplicar as alterações.
Teste a instalação do Docker executando:
```bash
docker run hello-world
```

Se tudo estiver configurado corretamente, você verá uma mensagem de sucesso no terminal.

Exemplo de execução

Para criar um projeto, execute o seguinte comando na pasta docker/generateProject:
```bash
./generate_project.sh myproject
```

Verifique a saída – ela mostrará o banco criado e a porta NGINX alocada.
Saída Esperada

Arquivos de template gerados em ./projects/myproject
Banco _supabase_myproject criado com sucesso
Realtime tenant criado
Pooler tenant criado
✅ Projeto myproject configurado com sucesso (porta 5432)

Estrutura de Diretórios
Caminho	O que contém
docker/	Stack base e utilitários (create_template.sh, generateProject/, studio/, traefik/).
docker/generateProject/	Script generate_project.sh e helpers.
projects/<PROJECT_ID>/	Arquivos gerados para cada projeto (NGINX, .env, docker-compose.yml).

Estrutura interna de projects/<PROJECT_ID>:

    projects/
    └── <PROJECT_ID>/
        ├── docker-compose.yml
        ├── .env
        ├── nginx/
        │   └── nginx_<PROJECT_ID>.conf
        └── storage/
            └── stub/
                └── stub/

### 5. Levantando o projeto gerado
### dentro de docker/<PROJECT_ID> (criado após o script)

```bash
docker compose -p <PROJECT_ID> \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up -d
```

Exemplo:

```bash
docker compose -p myproject \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up -d
```

### Observações

    Garanta que o Postgres (supabase-db) esteja sempre rodando.

    Para roteamento externo, suba o Traefik localizado em docker/traefik.

### 6. Subindo o Traefik

    Acesse docker/traefik e edite:
        "traefik.http.routers.dashboard.rule=Host(`localhost`) || Host(`127.0.0.1`) || Host(`<DOMAIN>`)" - colocando o seu ip ou dominio
    agora estando na pasta correta rode 'docker compose up -d'

Como usar

    "http://<DOMAIN>/<PROJECT_ID>"
    
exemplo testando o realtime:
```bash
wscat -c "ws://<DOMAIN>/<PROJECT_ID>/realtime/v1/websocket?apikey=<ANON_KEY>&vsn=1.0.0"
```
Como ver a ANON_KEY:

    Navegue até:
        projects/
    └── <PROJECT_ID>/
        ├── .env
    No '.env' terá a 'ANON_KEY'

Se tudo der certo, irá aparecer isso:

    Connected (press CTRL+C to quit)


### 7. Subindo o Supabase Studio

    Acesse docker/studio/ e edite:

    SUPABASE_PUBLIC_URL=http://<SEU_IP>:4000

    Remova a exposição externa da porta NGINX se quiser:

    # docker-compose.yml
    # ports:
    #   - "4000:4000"

    Ajuste .env (na mesma pasta):

    STUDIO_DB=_supabase_<PROJECT_ID>   # ex.: _supabase_myproject

    Edite /nginx/nginx.conf na pasta docker/studio/nginx/:

    map "" $auth_upstream     { default "supabase-auth-<PROJECT_ID>:9999"; }
    map "" $rest_upstream     { default "supabase-rest-<PROJECT_ID>:3000"; }
    map "" $storage_upstream  { default "supabase-storage-<PROJECT_ID>:5000"; }

    Altere <PROJECT_ID> com o nome do seu projeto

Suba o Studio

    docker compose --env-file ../secrets/.env --env-file ../.env --env-file .env up -d

### Extras
### 8. Configuração opcional: JWT Secret por projeto

Por padrão, todos os projetos gerados compartilham o mesmo JWT_SECRET. Caso seja necessário configurar um segredo JWT exclusivo para cada projeto:

Edite o script generate_project.sh para definir um valor específico de JWT_SECRET, o Banco que o realtime e o pooler usam, pois por padrão eles irão injetar no 'postgres'.

Certifique-se de injetar esse valor nas seguintes áreas:
        Realtime do projeto <PROJECT_ID>
        Pooler (Supavisor) do mesmo projeto
        Arquivo .env gerado para o serviço

Descomente o realtime e o pooler do compose do projeto gerado.

troque as variaveis necessarias:

    JWT_SECRET por JWT_SECRET_PROJETO - de todos no compose
    POSTGRES_DB por POSTGRES_DATABASE
    POOLER_PROXY_PORT_TRANSACTION por POOLER_PROXY_PORT_TRANSACTION_PROJETO - de todos que no compose
    POOLER_PROXY_PORT_SESSION por POOLER_PROXY_PORT_SESSION_PROJETO - para o auth
    POSTGRES_POOLER por supabase-pooler-<PROJECT_ID>

Tendo colocado no compose do projeto o realtime e o pooler suba o projeto, entre no container do realtime:
```bash
docker exec -it realtime-dev.supabase-realtime-<PROJECT_ID> bash
```
Após isso você precisa injetar no realtime do seu projeto o tenant dele, monte:
```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <ANON_KEY>' \
  -d $'{
    "tenant" : {
      "name": "<PROJECT_ID>",
      "external_id": "<PROJECT_ID>",
      "jwt_secret": "<JWT_SECRET>",
      "extensions": [
        {
          "type": "postgres_cdc_rls",
          "settings": {
            "db_name": "_supabase_<PROJECT_ID>",
            "db_host": "<POSTGRES_IP OU O NOME DO SERVIÇO>",
            "db_user": "supabase_admin",
            "db_password": "<POSTGRES_PASSWORD>",
            "db_port": "<POSTGRES_PORT>",
            "region": "us-west-1",
            "poll_interval_ms": 100,
            "poll_max_record_bytes": 1048576,
            "ssl_enforced": false
          }
        }
      ]
    }
  }' \
  http://localhost:4000/api/tenants
```
Exemplo:
```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6ImRhdGFiYXNlIiwiaWF0IjoxNzQwMDI4ODAwLCJleHAiOjE5OTk1MzU2MDB9.-jv7_S01MWg3LbyVh6dN9dRLbINy_na3AL09CKpcHEc' \
  -d $'{
    "tenant" : {
      "name": "myproject",
      "external_id": "myproject",
      "jwt_secret": "ckAhjmmZVag0Wyptbk/Zpc2OHVQrqG+S4zRzJtK9GycmljDAtmSNQlfdqPaO2tS+x7JwaeIMWGKa0rSUt/C6rA==",
      "extensions": [
        {
          "type": "postgres_cdc_rls",
          "settings": {
            "db_name": "_supabase_myproject",
            "db_host": "172.20.200.10",
            "db_user": "supabase_admin",
            "db_password": "1flz+Mz7tzVwZSGZj5B4q8l72Fg2W7GE",
            "db_port": "6755",
            "region": "us-west-1",
            "poll_interval_ms": 100,
            "poll_max_record_bytes": 1048576,
            "ssl_enforced": false
          }
        }
      ]
    }
  }' \
  http://localhost:4000/api/tenants
```
Deve aparecer algo nesse formato se deu certo:

    {"data":{"id":"29b39b2d-2ac7-4674-8cf9-2695c259b2b6","name":"myproject","extensions":[{"type":"postgres_cdc_rls","inserted_at":"2025-05-07T13:22:00","updated_at":"2025-05-07T13:22:00","settings":{"db_host":"S01Cnd7uGS/72nKUzRqPOg==","db_name":"wVFmbWxqRLWvhtmSRtvcZg==","db_port":"85fLfqCQw/z1PzuXaLBPgQ==","db_user":"/E0DLeOskFoEkSt1oSaHOg==","poll_interval_ms":100,"poll_max_changes":100,"poll_max_record_bytes":1048576,"publication":"supabase_realtime","region":"us-west-1","slot_name":"supabase_realtime_replication_slot","ssl_enforced":false}}],"inserted_at":"2025-05-07T13:22:00","external_id":"myproject","max_joins_per_second":100,"max_events_per_second":100,"max_concurrent_users":200,"max_channels_per_client":100,"private_only":false}}


No arquivo nginx_<PROJECT_ID> também precisa ser trocado, na linha 11 e 150, respectivamente coloque o <PROJECT_ID> em cada um:

    map "" $realtime_upstream { default "realtime-dev.supabase-realtime-<PROJECT_ID>:4000"; }

    proxy_set_header Host "<PROJECT_ID>.localhost";

No compose do studio comente essa parte 

    AUTH_JWT_SECRET: ${JWT_SECRET}

Agora descomente essa:
    #AUTH_JWT_SECRET: ${JWT_SECRET_STUDIO}

Troque o jwt, anon_key e role_key no compose do Supabase Studio porque ele precisa saber as chaves corretas em cada projeto, então sempre troque essas variaveis no '.env', pelos novos valores:

    ANON_KEY=
    SERVICE_ROLE_KEY=
    JWT_SECRET_STUDIO=

Essa configuração garante que cada projeto tenha seu próprio segredo JWT, caso desejado.

Na pasta 'exampleUsingDifferentJWT' é um projeto que foi gerado seguindo esses passos como exemplo.

| Variável             | Descrição                                  | Obrigatória? |
|----------------------|--------------------------------------------|--------------|
| `JWT_SECRET`         | Chave comum a todos os projetos            | Sim          |
| `JWT_SECRET_PROJETO` | Chave exclusiva para este projeto          | Não          |
| `JWT_SECRET_STUDIO`  | Chave usada pelo Supabase Studio do projeto| Depende      |

### 9. Solução de Problemas
| Erro | Causa & Ação |
|------|--------------|
| **"JWT_SECRET ausente"** | Defina `JWT_SECRET` em `secrets/.env`. |
| **"Contêiner não encontrado"** | Verifique se `supabase-db`, `realtime-dev.supabase-realtime` e `supabase-pooler` estão ativos. |
| **"Porta em uso"** | O script tenta até 20 portas NGINX (4000–14000). Libere portas ou edite o range. |

### Algumas observações importantes

    Pooler:
        No docker compose o supabase auth ou outros pode se notar que é o nome do usuario do banco '.' o nome do tenant
            'postgres://supabase_auth_admin.<PROJECT_ID>...'
        É como o pooler consegue saber qual tenant usar, e dentro do tenant tem as configurações para a conexão daquele database específico

    Realtime:
        Na conf do nginx na rota do realtime pode se notar essa variavel:
            'proxy_set_header Host "<PROJECT_ID>.localhost";'
        O funcionamento é bem parecido com o pooler, ele usa o valor antes do ponto para saber qual tenant ele deve usar para conexão
        Sem isso o realtime irá tentar usar o 'realtime-dev' que é como ele é declarado no compose 'realtime-dev.supabase-realtime'
