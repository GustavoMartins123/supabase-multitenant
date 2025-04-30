# Documentação

Este projeto **automatiza** a criação de novos projetos no ambiente Supabase, otimizando serviços como Realtime e Supavisor.

    Cada projeto usa o mesmo _JWT secret_. Se você quiser um secret diferente para cada projeto, altere o script para injetar esse valor no Realtime do banco `<PROJECT_ID>` correspondente, no Pooler e no arquivo `.env`. 
    No `docker-compose`, altere as variáveis de ambiente para consumir o `.env` gerado; assim, você terá um banco dedicado dentro do mesmo Postgres, com tokens assinados por chaves distintas. Além disso, o script:

- Configura um banco de dados dedicado.  
- Cria tenants para os serviços Realtime e Supavisor.  
- Gera arquivos de configuração necessários (NGINX, Docker Compose, variáveis de ambiente).  

---

## Propósito

Simplificar a inicialização de projetos Supabase, criando automaticamente:

- Um **database dedicado** para o projeto.  
- Configurações de **tenants** para Realtime e Supavisor.  
- Arquivos de configuração para **NGINX**, variáveis de ambiente e **Docker Compose**.  

---

## Pré-requisitos

| Item | Descrição |
|------|-----------|
| Docker & Docker Compose | Instalados e funcionando. |
| Contêineres em execução | `supabase-db` (PostgreSQL), `realtime-dev.supabase-realtime` (Realtime) e `supabase-pooler` (Supavisor). |
| Arquivos de ambiente | `secrets/.env` (JWT_SECRET, POSTGRES_PASSWORD) e `.env` (POSTGRES_HOST, POSTGRES_PORT). |
| PROJECT_ID | Identificador único a ser passado como argumento. |

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
docker compose --env-file ../secrets/.env --env-file ../.env up -d
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
Caso não apareça, rode manualmente dentro do contêiner:
```bash
cd docker-entrypoint-initdb.d/

chmod +x zzz-create_template.sh

./zzz-create_template.sh
```
###4. Executar o gerador de projetos

pasta docker/generateProject
./generate_project.sh <PROJECT_ID>

Exemplo:
```bash
./generate_project.sh myproject
```
Observação
    Não use caracteres especiais diferentes de um '_', pois o postgres não aceita.

Verifique a saída – ela mostrará o banco criado e a porta NGINX alocada.
Saída Esperada

Arquivos de template gerados em ./projects/myproject
Banco _supabase_myproject criado com sucesso
Realtime tenant criado
Supavisor tenant criado
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

Solução de Problemas
| Erro | Causa & Ação |
|------|--------------|
| **"JWT_SECRET ausente"** | Defina `JWT_SECRET` em `secrets/.env`. |
| **"Contêiner não encontrado"** | Verifique se `supabase-db`, `realtime-dev.supabase-realtime` e `supabase-pooler` estão ativos. |
| **"Porta em uso"** | O script tenta até 20 portas NGINX (4000–14000). Libere portas ou edite o range. |

Levantando o projeto gerado
### dentro de docker/<PROJECT_ID> (criado após o script)

docker compose -p <PROJECT_ID> \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up -d

Exemplo:

```bash
docker compose -p myproject \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up -d
```

Observações

    Garanta que o Postgres (supabase-db) esteja sempre rodando.

    Para roteamento externo, suba o Traefik localizado em docker/traefik.

Subindo o Traefik

    Acesse docker/traefik e edite:
        "traefik.http.routers.dashboard.rule=Host(`localhost`) || Host(`127.0.0.1`) || Host(`<SEU_DOMINIO>`)" - colocando o seu ip ou dominio
    agora estando na pasta correta rode 'docker compose up -d'

Subindo o Supabase Studio

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

Algumas observações importantes sobre o realtime e o pooler

    Pooler:
        No docker compose o supabase auth ou outros pode se notar que é o nome do usuario do banco '.' o nome do tenant
            'postgres://supabase_auth_admin.<PROJECT_ID>...'
        É como o pooler consegue saber qual tenant usar, e dentro do tenant tem as configurações para a conexão daquele database específico

    Realtime:
        Na conf do nginx na rota do realtime pode se notar essa variavel:
            'proxy_set_header Host "<PROJECT_ID>.localhost";'
        O funcionamento é bem parecido com o pooler, ele usa o valor antes do ponto para saber qual tenant ele deve usar para conexão
        Sem isso o realtime irá tentar usar o 'realtime-dev' que é como ele é declarado no compose 'realtime-dev.supabase-realtime'
