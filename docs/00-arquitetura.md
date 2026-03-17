# Arquitetura do Sistema

Este documento explica como o sistema funciona internamente, desde a autenticação até o roteamento de requisições para projetos específicos.

---

## Visão Geral

O sistema permite gerenciar múltiplos projetos Supabase isolados em um único servidor, usando:

- **Studio único** para gerenciar todos os projetos
- **PostgreSQL compartilhado** com databases isolados por projeto
- **Roteamento dinâmico** via Traefik + Nginx/Lua
- **Autenticação centralizada** via Authelia

---

## Conceitos Base

### Replication Slots

PostgreSQL não permite usar o mesmo replication slot em databases diferentes simultaneamente. Por isso, cada projeto precisa de seu próprio slot para o Realtime funcionar.

**Padrão de nomenclatura:**
```
supabase_realtime_messages_replication_slot_projeto_a
supabase_realtime_messages_replication_slot_projeto_b
```

O tenant_id é extraído do header `Host` injetado pelo Nginx do projeto e usado para construir o nome do slot específico.

### JWT Tokens

Todos os projetos usam o mesmo `JWT_SECRET` (compartilhado), mas cada projeto tem tokens únicos.

**Geração:**
- Algoritmo: HS256 (HMAC SHA256)
- Validade: 8 anos
- Roles: `anon` e `service_role`
- Diferenciação: campo `iss` (issuer) único por projeto

**Exemplo:**
```json
{
  "role": "anon",
  "iss": "supabase-projeto_x",
  "iat": 1234567890,
  "exp": 1486789012
}
```

### Pools de Conexão (Supavisor)

O Supavisor identifica o projeto pelo **sufixo do username** na connection string.

**Padrão:** `usuario.TENANT_ID:senha@pooler:porta/database`

**Exemplos:**
```bash
postgres://supabase_auth_admin.projeto_x:senha@pooler:6543/postgres
postgres://authenticator.projeto_x:senha@pooler:6543/postgres
postgres://supabase_storage_admin.projeto_x:senha@pooler:5432/postgres
```

**Modos de pooling:**
- **Transaction mode (porta 5432):** Storage - pool por transação
- **Session mode (porta 6543):** GoTrue e PostgREST - pool por sessão

**Configuração padrão por projeto:**
```json
{
  "db_database": "_supabase_projeto_x",
  "default_pool_size": 40,
  "default_max_clients": 800
}
```

---

## Componentes Principais

### Studio

**Porta:** 9091 (Authelia) e 4000 (Nginx)

**Componentes:**
- **Authelia:** Autenticação de usuários
- **Nginx/OpenResty + Lua:** Gateway inteligente que injeta credenciais
- **Flutter Web:** Interface de seleção de projetos
- **Supabase Studio:** Interface final de gerenciamento

**Responsabilidades:**
- Autenticar usuários
- Permitir seleção de projeto
- Injetar `Authorization` header com service_role do projeto
- Fazer proxy para o Traefik

### Servidor

**Componentes:**

**Serviços Compartilhados:**
- **PostgreSQL (supabase-db):** Banco principal com databases isolados por projeto
- **Supavisor (Pooler):** Pool de conexões global
- **Realtime:** WebSocket global para todos os projetos
- **Edge Functions:** Functions compartilhadas
- **API Python (FastAPI):** Gerencia ciclo de vida dos projetos

**Por Projeto:**
- **Nginx:** Gateway do projeto
- **GoTrue:** Autenticação de usuários finais
- **PostgREST:** API REST do banco
- **Storage:** Armazenamento de arquivos
- **Meta (postgres-meta):** API de metadados do banco (usado exclusivamente pelo Studio)
- **ImgProxy:** Processamento de imagens

**Gateway:**
- **Traefik:** Roteamento dinâmico baseado em labels Docker

---

## Fluxo de Autenticação

### 1. Login Inicial

```
Usuário → https://ip:9091
  ↓
Authelia valida credenciais (users_database.yml)
  ↓
Redireciona para https://ip:4000 (Nginx Studio)
  ↓
Nginx serve Flutter Web
```

### 2. Seleção de Projeto

```
Usuário clica em "Projeto X"
  ↓
Flutter chama: GET /set-project?ref=projeto_x
  ↓
Nginx/Lua cria cookie assinado: supabase_project=projeto_x.timestamp.signature
  ↓
Cookie válido por 24 horas (86400s)
  ↓
Redireciona para Supabase Studio
```

### 3. Headers Injetados pelo Authelia

Após autenticação, Authelia retorna o email e grupos do usuário. O Nginx/Lua então processa e injeta headers:

**Processo:**

1. Authelia retorna headers:
   ```
   Remote-Email: usuario@example.com
   Remote-Groups: active,admin
   ```

2. Nginx/Lua hasheia o email (SHA256):
   ```lua
   local sha256 = require "resty.sha256"
   local hasher = sha256:new()
   hasher:update(email)
   local digest = hasher:final()
   local email_hash = str.to_hex(digest)
   ```

3. Nginx injeta headers hasheados:
   ```
   Remote-Email: a1b2c3d4e5f6...  (SHA256 do email)
   Remote-Groups: active,admin
   ```

**Por que hashear o email?**
- Privacidade: email não trafega em texto plano
- Consistência: API Python também usa hash para validar

Esses headers são usados pela API Python para validar permissões.

---

## Fluxo de Requisição Completo

### Exemplo: GET /rest/v1/tabela

```
1. Usuário faz requisição no Studio
   GET /rest/v1/tabela

2. Nginx Studio (Lua) intercepta
   - Authelia já validou e retornou email/grupos
   - Lua hasheia email com SHA256
   - Injeta Remote-Email (hash) e Remote-Groups
   - Lê cookie supabase_project → "projeto_x"
   - Valida assinatura HMAC do cookie
   - Busca service_role do projeto_x (cache ou API)

3. Nginx Studio injeta Authorization
   Authorization: Bearer eyJhbGc...service_role_do_projeto_x
   
4. Nginx Studio faz proxy para Traefik
   GET https://servidor/projeto_x/rest/v1/tabela

5. Traefik roteia baseado em labels Docker
   - Lê label: traefik.http.routers.projeto-x.rule=PathPrefix(`/projeto_x`)
   - Roteia para container nginx-projeto-x

6. Nginx do Projeto valida apikey
   - Verifica se Authorization header é válido
   - Remove prefixo /projeto_x do path

7. Nginx do Projeto faz proxy para PostgREST
   GET http://rest:3000/tabela
   
8. PostgREST consulta database projeto_x
   - Conecta via Supavisor (pooler)
   - Executa query com permissões do JWT

9. Resposta retorna pelo caminho inverso
   PostgREST → Nginx Projeto → Traefik → Nginx Studio → Usuário
```

---

## Sistema de Cache de Service Keys

### Problema

Buscar a service_role do banco a cada requisição seria lento.

### Solução

**Cache em memória compartilhada (Lua shared dict):**

```lua
-- Configuração
lua_shared_dict service_keys 10m;  -- 10MB de cache
TTL: 600 segundos (10 minutos)
```

**Fluxo:**

```
1. Nginx/Lua precisa da service_role de "projeto_x"

2. Verifica cache (service_keys:projeto_x)
   - Se existe e não expirou → usa do cache
   - Se não existe ou expirou → busca da API

3. Cache miss: chama API interna
   GET http://api:18000/api/projects/internal/enc-key/projeto_x
   Header: X-Shared-Token: NGINX_SHARED_TOKEN

4. API Python retorna key criptografada (Fernet)
   {"encrypted_key": "gAAAAA..."}

5. Lua descriptografa com Fernet
   service_role = fernet.decrypt(encrypted_key)

6. Armazena em cache por 10 minutos
   cache:set("projeto_x", service_role, 600)

7. Usa a key descriptografada
```

**Por que criptografar?**
- Keys não ficam em texto plano no banco
- Mesmo com acesso ao banco, precisa do FERNET_SECRET

---

## Banco de Dados Compartilhado

### Estrutura

**Database `postgres` (sistema):**
```sql
-- Tabelas do sistema
projects (id, name, owner_email, anon_key, service_role, ...)
project_members (project_id, user_email, role, ...)
```

**Databases por projeto:**
```
projeto_a  -- Database isolado do Projeto A
projeto_b  -- Database isolado do Projeto B
projeto_c  -- Database isolado do Projeto C
```

### Isolamento

Cada projeto tem:
- Database próprio no PostgreSQL
- Schemas próprios (auth, storage, realtime, etc.)
- Replication slot próprio para Realtime
- Roles próprios (authenticator, anon, service_role)

### Conexões

**Via Supavisor (Pooler):**
- GoTrue, PostgREST, Storage → conectam via pooler
- Pool compartilhado, mas cada serviço especifica o database

**Conexão Direta:**
- Meta → conecta direto no PostgreSQL

---

## Setup Inicial

### Primeira Inicialização do PostgreSQL

Na primeira vez que o PostgreSQL sobe, um script de inicialização cria a estrutura base do sistema.

**Script:** `servidor/volumes/db/create_template.sh`

**Montado em:** `/docker-entrypoint-initdb.d/zzz-create_template.sh`

⚠️ O prefixo `zzz-` garante que este script execute por último, após todos os outros scripts de inicialização do Supabase (roles.sql, jwt.sql, webhooks.sql, etc.).

### O Que o Script Faz

```
1. Cria schema _analytics
   CREATE SCHEMA IF NOT EXISTS _analytics;
   
   Usado para armazenar métricas e logs do sistema.

2. Cria database _supabase_template (vazio)
   CREATE DATABASE _supabase_template;

3. Faz dump do database postgres
   pg_dump -U postgres -d postgres \
     --exclude-schema=cron \
     | grep -v "CREATE EXTENSION.*pg_cron" \
     | grep -v "COMMENT ON EXTENSION pg_cron"
   
   Captura toda a estrutura criada pelos scripts de inicialização:
   - roles.sql (anon, service_role, authenticator, etc.)
   - jwt.sql (validação JWT)
   - webhooks.sql, logs.sql, realtime.sql
   - storage.sql (schemas e functions)
   - Todas as extensions (pg_net, pgjwt, etc.)

4. Restaura dump em _supabase_template
   psql -U postgres -d _supabase_template
   
   Agora _supabase_template tem toda a estrutura base do Supabase.

5. Cria tabelas do sistema no database postgres
   
   A) Tabela projects:
      CREATE TABLE projects (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        anon_key TEXT,
        service_role TEXT
      );
   
   B) Tabela project_members:
      CREATE TABLE project_members (
        project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL,
        role TEXT DEFAULT 'member',
        PRIMARY KEY (project_id, user_id)
      );
   
   C) Tabela jobs:
      CREATE TABLE jobs (
        job_id UUID PRIMARY KEY,
        project TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        status TEXT NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now()
      );

6. Transforma _supabase_template em template
   ALTER DATABASE _supabase_template WITH is_template = true;
   UPDATE pg_database SET datallowconn = false 
   WHERE datname = '_supabase_template';
   
   - is_template = true: Permite usar como template no CREATE DATABASE
   - datallowconn = false: Impede conexões diretas (proteção)
```

### Por Que Usar Template?

**Sem template:**
```sql
CREATE DATABASE projeto_novo;
-- Precisa rodar todos os scripts manualmente
-- Demora ~30 segundos por projeto
```

**Com template:**
```sql
CREATE DATABASE projeto_novo TEMPLATE _supabase_template;
-- Clona estrutura completa em ~2 segundos
```

**Vantagens:**
- Criação de projeto 15x mais rápida
- Garante que todos os projetos têm estrutura idêntica
- Não precisa reexecutar migrations
- Reduz chance de erros

### O Que Está no Template

**Schemas:**
- `auth` (GoTrue - autenticação)
- `storage` (Storage - arquivos)
- `realtime` (Realtime - subscriptions)
- `extensions` (Extensions instaladas)
- `public` (Schema padrão do usuário)

**Roles:**
- `anon` (acesso público)
- `authenticated` (usuários autenticados)
- `service_role` (acesso total)
- `authenticator` (role de conexão)
- `supabase_auth_admin` (GoTrue)
- `supabase_storage_admin` (Storage)
- `pgbouncer` (Supavisor)

**Extensions:**
- `pg_net` (HTTP requests)
- `pgjwt` (JWT validation)
- `uuid-ossp` (UUID generation)
- `pgcrypto` (Encryption)
- E outras extensions do Supabase

**Functions e Triggers:**
- Validação JWT
- Webhooks
- Storage policies
- Realtime triggers

### Quando o Template é Usado

**Criação de projeto:**
```bash
CREATE DATABASE _supabase_projeto_novo TEMPLATE _supabase_template;
```

---

## Criação de Projeto

### Fluxo Completo

**Importante:** Todo o processo é executado pelo script `generate_project.sh`, chamado pela API Python.

```
1. Usuário clica em "Criar Projeto" no Flutter
   POST /api/projects
   Body: { name: "meu_projeto" }
   Headers: Remote-Email (SHA256 hash), Remote-Groups

2. API Python valida permissões
   - Recebe email hasheado no header
   - Hasheia emails do banco para comparar
   - Verifica se usuário pode criar projetos
   - Valida nome (único, sem caracteres especiais)

3. API Python chama generate_project.sh
   bash generate_project.sh meu_projeto

4. Script valida nome do projeto
   - Apenas minúsculas, números e _ (3-40 caracteres)
   - Não pode conter ponto (.)
   - Não pode ser palavra reservada SQL
   - Não pode já existir

5. Script gera portas aleatórias
   - NGINX_PORT (range 4000-14000, até 20 tentativas)
   - META_PORT (range 4000-14000, até 20 tentativas)
   - Verifica se porta está livre com lsof

6. Script gera JWT tokens
   Ver seção "Conceitos Base" para detalhes sobre geração de tokens.

7. Script cria estrutura de pastas
   servidor/projects/meu_projeto/
   ├── docker-compose.yml (do dockercomposetemplate)
   ├── .env (do .envtemplate)
   ├── Dockerfile
   ├── nginx/
   │   └── nginx_meu_projeto.conf (do nginxtemplate)
   ├── pooler/
   │   └── pooler.exs (do poolertemplate)
   └── storage/
       └── stub/stub/

8. Script cria database no PostgreSQL
   CREATE DATABASE _supabase_meu_projeto TEMPLATE _supabase_template;
   
   Clona estrutura completa do template (ver seção "Setup Inicial").
   Inclui todos os schemas, roles, extensions, functions e triggers.

9. Script registra tenant no Realtime
   Ver seção "Conceitos Base" para detalhes sobre replication slots.
   
   POST http://realtime:4000/api/tenants
   Body: {
     name: "meu_projeto",
     jwt_secret: "...",
     db_name: "_supabase_meu_projeto",
     slot_name: "supabase_realtime_replication_slot_meu_projeto"
   }

10. Script registra tenant no Supavisor
    Ver seção "Conceitos Base" para detalhes sobre pools de conexão.
    
    PUT http://pooler:4000/api/tenants/meu_projeto

11. Script executa docker compose
    cd servidor/projects/meu_projeto
    docker compose -p meu_projeto \
      --env-file ../../secrets/.env \
      --env-file ../../.env \
      --env-file .env \
      up --build -d

12. Traefik descobre automaticamente
    - Lê labels Docker do container nginx-meu_projeto
    - Registra rota: /meu_projeto → nginx-meu_projeto:NGINX_PORT

13. API Python salva no banco sistema (postgres)
    INSERT INTO projects (
      name, owner_email, 
      anon_key, service_role,  -- criptografados com Fernet
      nginx_port, meta_port,
      ...
    )

14. Projeto está pronto
    - Aparece na lista do Flutter
    - Usuário pode acessar via Studio
```

---

## Traefik - Roteamento Dinâmico

### Como Funciona

Traefik monitora o Docker socket e lê labels dos containers automaticamente.

**Labels do projeto:**
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.supabase-nginx-meu_projeto.rule=PathPrefix(`/meu_projeto`)"
  - "traefik.http.services.supabase-nginx-meu_projeto.loadbalancer.server.port=PORTA"
  - "traefik.http.routers.supabase-nginx-meu_projeto.middlewares=strip-meu_projeto"
  - "traefik.http.middlewares.strip-meu_projeto.stripprefix.prefixes=/meu_projeto"
```

**Fluxo:**

```
Requisição: GET /meu_projeto/rest/v1/tabela
  ↓
Traefik lê rule: PathPrefix(`/meu_projeto`)
  ↓
Aplica middleware: strip-meu_projeto (remove /meu_projeto)
  ↓
Envia para nginx-meu_projeto:PORTA
  ↓
Nginx do projeto recebe: GET /rest/v1/tabela
```

---

## Serviços Compartilhados

### Realtime (Global)

**Um único container atende todos os projetos.**

**Modificação importante para multi-tenant:**

O Realtime original do Supabase não suporta múltiplos projetos nativamente. A solução implementada modifica a função `replication_slot_name/1`:

**Original:**
```elixir
def replication_slot_name(schema, table) do
  "supabase_#{schema}_#{table}_replication_slot_#{slot_suffix()}"
end
```

**Modificado:**
```elixir
def replication_slot_name(%__MODULE__{table: table, schema: schema, tenant_id: tenant_id}) do
  "supabase_#{schema}_#{table}_replication_slot_#{tenant_id}"
end
```

**Como funciona:**

1. Nginx do projeto injeta: `Host: meu_projeto.localhost`
2. Realtime extrai `tenant_id` do header Host
3. Usa tenant_id para construir nome do replication slot (ver seção "Conceitos Base")

**Fluxo completo:**

```
WebSocket: wss://servidor/projeto_x/realtime/v1
  ↓
Traefik roteia para nginx-projeto-x
  ↓
Nginx injeta: Host: projeto_x.localhost
  ↓
Proxy para Realtime global
  ↓
Realtime extrai tenant_id = "projeto_x"
  ↓
Conecta no database _supabase_projeto_x
  ↓
Usa slot específico do projeto (ver "Conceitos Base")
  ↓
Stream de mudanças específico do projeto
```

**Arquivo modificado:**
- `servidor/volumes/realtime/replication_connection.ex`
- Injetado no container Realtime durante build

### Supavisor (Pooler)

**Um único container gerencia conexões de todos os projetos.**

Ver seção "Conceitos Base" para detalhes sobre como o roteamento multi-tenant funciona (sufixo do username, modos de pooling, configuração padrão).

**Vantagens:**

- Pool compartilhado entre projetos
- Isolamento por tenant_id no username
- Limites configuráveis por projeto
- Suporta múltiplos modos de pooling

### Edge Functions

**Compartilhadas entre projetos.**

Localização: `servidor/volumes/functions/`

Cada projeto pode ter sua pasta:
```
functions/
├── main/          # Functions globais
├── projeto_a/     # Functions do projeto A
└── projeto_b/     # Functions do projeto B
```
---

## Por Projeto

### Postgres-Meta

**Um container por projeto.**

**O que é:**
- API que expõe metadados do PostgreSQL
- Usado exclusivamente pelo Supabase Studio

**Responsabilidades:**
- Listar tabelas, colunas, schemas
- Consultar policies (RLS), functions, triggers
- Fornecer informações para a interface do Studio
- Cache de metadados para evitar queries pesadas

**Como funciona:**
```
Studio precisa listar tabelas
  ↓
GET /api/platform/pg-meta/default/tables
  ↓
Nginx Studio injeta service_role
  ↓
Proxy para: https://servidor/projeto_x/meta/tables
  ↓
Postgres-Meta consulta information_schema
  ↓
Retorna JSON com lista de tabelas
```

**Conexão:**
- Conecta direto no PostgreSQL (não usa Supavisor)
- Precisa de acesso total ao information_schema
- Cada projeto tem seu próprio container Meta

---

## Isolamento e Segurança

### Validação de Permissões

**Nível 1: Authelia**
- Valida credenciais do usuário
- Retorna email e grupos do usuário

**Nível 1.5: Nginx/Lua**
- Hasheia o email com SHA256
- Injeta headers: Remote-Email (hasheado), Remote-Groups

**Nível 2: API Python**
- Recebe email hasheado
- Hasheia emails do banco para comparar
- Valida se usuário é dono ou membro do projeto
- Consulta tabela `project_members` no database `postgres`
- Verifica role (admin ou member)

**Nível 3: Nginx do Projeto**
- Valida se Authorization header é válido
- Verifica se é anon_key ou service_role do projeto

**Nível 4: PostgREST/GoTrue**
- Valida JWT signature com JWT_SECRET do projeto
- Aplica Row Level Security (RLS) do PostgreSQL

### O que Impede Acesso Não Autorizado

**Usuário A não pode acessar projeto do Usuário B porque:**

1. API Python valida membros antes de retornar service_role
2. Cookie `supabase_project` é assinado
3. Service_role é específica de cada projeto
4. Nginx do projeto valida a apikey

---

## Arquitetura de 2 Máquinas

### Configuração

**Máquina 1 (Rede Local - sem IP externo):**
- Studio (Authelia + Nginx/Lua + Flutter)
- Porta 9091 (Authelia) acessível apenas na LAN

**Máquina 2 (Servidor - com IP externo):**
- PostgreSQL, Supavisor, Realtime, Functions
- API Python
- Traefik (portas 80/443 expostas)
- Projetos (containers dinâmicos)

### Comunicação

```
Usuário (LAN) → Authelia (Máquina 1)
  ↓
Nginx Studio (Máquina 1) → Traefik (Máquina 2 - IP externo)
  ↓
Traefik → Projetos (Máquina 2)
```

**Nginx Studio acessa API Python:**
- Via HTTP: `http://IP_EXTERNO:18000/api/...`
- Protegido por IP allowlist
- Header: `X-Shared-Token: NGINX_SHARED_TOKEN`

**Alternativa:**
- Usar autenticação do Traefik (Forward Auth)
- Remover IP allowlist

---

## Rede Docker

**Nome:** `rede-supabase`

**Configuração:**
```
Driver: bridge
Subnet: 172.20.0.0/16
IP Range: 172.20.0.0/18
Gateway: 172.20.0.1
```

**Todos os containers estão na mesma rede:**
- Comunicação por nome (ex: `supabase-db`, `traefik`, `nginx-projeto-x`)

---

## Observabilidade e Logs

### Vector - Agregação de Logs

O sistema usa **Vector** para coletar e armazenar logs de containers Docker no PostgreSQL.

**Container:** `supabase-vector-global`

**Configuração:** `servidor/volumes/logs/vector.yml`

### Estrutura de Logs

**Database:** `logs_db` (separado do database `postgres`)

**Tabela:** `public.logs` (particionada por mês)

**Schema:**
```sql
CREATE TABLE public.logs (
  timestamp TIMESTAMPTZ NOT NULL,
  container_id TEXT,
  container_name TEXT,
  image TEXT,
  stream TEXT,              -- stdout ou stderr
  message TEXT,             -- Conteúdo do log
  host TEXT,
  container_created_at TIMESTAMPTZ,
  label JSONB,
  source_type TEXT
) PARTITION BY RANGE (timestamp);
```

**Índices:**
- `idx_logs_timestamp` (timestamp DESC)
- `idx_logs_container_name` (container_name)
- `idx_logs_stream` (stream)

### Particionamento Automático

**Partições por mês:**
```
logs_2025_01  -- Janeiro 2025
logs_2025_02  -- Fevereiro 2025
logs_2025_03  -- Março 2025
logs_default  -- Fallback
```

**Manutenção automática via pg_cron:**
- Executa diariamente às 04:00
- Cria partição para próximos 2 meses
- Remove partições com mais de 3 meses

```sql
-- Job agendado
SELECT cron.schedule(
  'maintain_logs_partitions_job',
  '0 4 * * *',
  $$SELECT maintain_log_partitions()$$
);
```

### Serviços Monitorados

Vector coleta logs apenas dos **serviços globais:**

```yaml
# vector.yml - filtro
filter_global_services:
  type: "filter"
  condition: >-
    includes([
      "supabase-db",
      "supabase-pooler",
      "realtime-dev.supabase-realtime",
      "supabase-edge-functions",
      "docker-projects-api-1",
      "traefik-traefik-1"
    ], .container_name)
```

**Logs de projetos individuais não são coletados** (nginx-projeto-x, gotrue-projeto-x, etc.)

### Como Consultar Logs

**Conectar no database logs_db:**
```bash
docker exec -it supabase-db psql -U supabase_admin -d logs_db
```

**Logs recentes de todos os serviços:**
```sql
SELECT timestamp, container_name, stream, message
FROM public.logs
ORDER BY timestamp DESC
LIMIT 100;
```

**Logs de um serviço específico:**
```sql
SELECT timestamp, stream, message
FROM public.logs
WHERE container_name = 'supabase-db'
ORDER BY timestamp DESC
LIMIT 50;
```

**Logs de erro (stderr):**
```sql
SELECT timestamp, container_name, message
FROM public.logs
WHERE stream = 'stderr'
ORDER BY timestamp DESC
LIMIT 50;
```

**Logs de um período específico:**
```sql
SELECT timestamp, container_name, message
FROM public.logs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
  AND container_name = 'realtime-dev.supabase-realtime'
ORDER BY timestamp DESC;
```

**Buscar por palavra-chave:**
```sql
SELECT timestamp, container_name, message
FROM public.logs
WHERE message ILIKE '%error%'
  OR message ILIKE '%exception%'
ORDER BY timestamp DESC
LIMIT 100;
```

**Estatísticas por container:**
```sql
SELECT 
  container_name,
  COUNT(*) as total_logs,
  COUNT(*) FILTER (WHERE stream = 'stderr') as errors,
  MIN(timestamp) as first_log,
  MAX(timestamp) as last_log
FROM public.logs
WHERE timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY container_name
ORDER BY total_logs DESC;
```

### Configuração do Vector

**Variáveis de ambiente:**
```yaml
environment:
  LOGFLARE_API_KEY: ${LOGFLARE_API_KEY}  # Não usado atualmente
  PG_URI: postgres://vector_writer:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/logs_db
```

**User dedicado:**
- Username: `vector_writer`
- Password: Mesma do `POSTGRES_PASSWORD`
- Permissões: ALL ON DATABASE logs_db

**Batch de inserção:**
```yaml
batch:
  max_events: 100      # Insere até 100 logs por vez
  timeout_secs: 1      # Ou a cada 1 segundo
```

### Retenção de Logs

**Padrão:** 3 meses

**Modificar retenção:**

Editar função `maintain_log_partitions()` em `servidor/volumes/db/vector_logs.sql`:

```sql
-- Alterar de 3 para 6 meses
old_month_end date := date_trunc('month', now() - interval '6 months');
```

Recriar o database logs_db ou executar a função manualmente.

### Limitações

**Logs não coletados:**
- Containers de projetos individuais
- Containers excluídos do filtro
- Logs antes da inicialização do Vector

**Performance:**
- Partições antigas devem ser dropadas regularmente
- Índices podem crescer significativamente
- Considerar archive/backup de partições antigas

### Troubleshooting

**Vector não está coletando logs:**
```bash
# Verificar status do Vector
docker logs supabase-vector-global

# Verificar health
docker exec supabase-vector-global wget -qO- http://localhost:8686/health
```

**Tabela logs vazia:**
```sql
-- Verificar se user vector_writer existe
\du vector_writer

-- Verificar permissões
\dp public.logs
```

**Partições não sendo criadas:**
```sql
-- Verificar job do pg_cron
SELECT * FROM cron.job WHERE jobname = 'maintain_logs_partitions_job';

-- Executar manualmente
SELECT maintain_log_partitions();
```

---

## Duplicação de Projeto
**With-Data:**
- Copia estrutura completa
- Copia todos os dados das tabelas
- Copia arquivos do storage (com xattr preservados)
- Uso: Backup, staging, testes

### Processo Completo

**Executado pelo script `duplicate_project.sh`:**

```bash
bash duplicate_project.sh projeto_original projeto_novo [with-data|schema-only]
```

**Fluxo:**

```
1. Validações iniciais
   - Verifica se projeto original existe
   - Valida nome do novo projeto (minúsculas, sem ponto, não reservado)
   - Verifica se novo projeto já existe

2. Gera portas aleatórias
   - NGINX_PORT (4000-14000, até 20 tentativas)
   - META_PORT (4000-14000, até 20 tentativas)

3. Gera novos JWT tokens
   Ver seção "Conceitos Base" para detalhes sobre geração de tokens.
   Cada projeto tem tokens únicos (iss diferente).

4. Cria estrutura de pastas
   servidor/projects/projeto_novo/
   ├── docker-compose.yml
   ├── .env
   ├── Dockerfile
   ├── nginx/
   │   └── nginx_projeto_novo.conf
   └── pooler/
       └── pooler.exs

5. Duplica database

   A) Cria database vazio:
      CREATE DATABASE _supabase_projeto_novo;
   
   B) Garante que roles existem:
      - pgbouncer
      - authenticator
      - supabase_auth_admin
      - supabase_storage_admin
   
   C) Faz dump do banco original:
   
      Schema-only:
      - pg_dump --schema=auth --schema=storage --schema-only
      - pg_dump --exclude-schema=auth --exclude-schema=storage --schema-only
      - Copia dados de migrations (auth.schema_migrations, storage.migrations)
      
      With-data:
      - pg_dump completo (schema + dados)
   
   D) Restaura dump no novo database:
      psql -d _supabase_projeto_novo < dump.sql
   
   E) Marca migrations como executadas:
      UPDATE auth.schema_migrations SET dirty = false;
      UPDATE storage.migrations SET dirty = false;

6. Copia storage (apenas with-data)
   
   Usa tar com preservação de xattr:
   
   cd projeto_original/storage
   tar --xattrs --xattrs-include='*' --acls -cpf - . | \
     (cd projeto_novo/storage && tar --xattrs --xattrs-include='*' --acls -xpf -)
   
   Flags importantes:
   - --xattrs: Preserva extended attributes (metadados do Storage)
   - --acls: Preserva permissões ACL
   - -p: Preserva permissões, ownership, timestamps

7. Registra tenant no Realtime
   Ver seção "Conceitos Base" para detalhes sobre replication slots.
   
   POST http://realtime:4000/api/tenants
   Body: {
     name: "projeto_novo",
     jwt_secret: "...",
     db_name: "_supabase_projeto_novo",
     slot_name: "supabase_realtime_replication_slot_projeto_novo"
   }

8. Registra tenant no Supavisor
   Ver seção "Conceitos Base" para detalhes sobre pools de conexão.
   
   PUT http://pooler:4000/api/tenants/projeto_novo

9. Sobe containers do novo projeto
   cd servidor/projects/projeto_novo
   docker compose -p projeto_novo \
     --env-file ../../secrets/.env \
     --env-file ../../.env \
     --env-file .env \
     up --build -d

10. Traefik descobre automaticamente
    - Lê labels Docker
    - Registra rota: /projeto_novo → nginx-projeto_novo:NGINX_PORT

11. API Python salva no banco sistema
    INSERT INTO projects (
      name, owner_email,
      anon_key, service_role,  -- criptografados com Fernet
      nginx_port, meta_port,
      ...
    )
```



### Por Que Copiar Migrations?

**Crítico para Auth e Storage não quebrarem:**

```sql
-- Copia histórico de migrations
pg_dump --data-only \
  -t 'auth.schema_migrations' \
  -t 'storage.migrations'
```

Se não copiar:
- GoTrue tenta rodar migrations novamente
- Storage tenta rodar migrations novamente
- Pode causar erros ou inconsistências

---

## Deleção de Projeto

### Segurança

A deleção de projeto requer autenticação em múltiplos níveis:

**Senha de Deleção:**
- Gerada automaticamente no `setup.sh`
- Armazenada em: `servidor/.env` como `PROJECT_DELETE_PASSWORD`
- Única para toda a instalação
- Deve ser enviada no header `X-Delete-Password`

**Permissões:**
- Apenas usuários do grupo `admin` podem deletar projetos
- Validado pelo Nginx/Lua (`check_admin.lua`)
- API Python valida novamente

### Fluxo Completo

**Executado pela API Python, que chama `delete_project.sh`:**

```
1. Usuário clica em "Deletar Projeto" no Flutter
   DELETE /api/projects/meu_projeto
   Headers:
     Remote-Email: (SHA256 hash)
     Remote-Groups: admin
     X-Delete-Password: senha_gerada_no_setup

2. Nginx Studio valida permissões
   - Verifica se método é DELETE
   - Verifica se X-Delete-Password está presente
   - Executa check_admin.lua (valida grupo admin)
   - Executa admin_projects_delete_check.lua

3. API Python valida credenciais
   - Verifica se usuário está no grupo admin
   - Valida senha com hmac.compare_digest()
   - Verifica se PROJECT_DELETE_PASSWORD está configurado

4. API Python pausa serviços críticos
   docker pause realtime-dev.supabase-realtime
   docker pause supabase-pooler
   
   Motivo: Evitar conexões ativas durante deleção

5. API Python remove containers do projeto
   - Lista containers com get_project_containers()
   - Remove cada container: docker rm -f <container>

6. API Python limpa registros do Realtime
   DELETE FROM _realtime.extensions WHERE tenant_external_id = 'meu_projeto'
   DELETE FROM _realtime.tenants WHERE external_id = 'meu_projeto'

7. API Python aguarda 10 segundos
   Garante que conexões sejam finalizadas

8. API Python termina conexões ativas
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE datname = '_supabase_meu_projeto'
     AND pid <> pg_backend_pid()

9. API Python aguarda 2 segundos
   Garante que conexões foram terminadas

10. API Python dropa replication slots
    Chama drop_supabase_replication_slots()
    Remove slots: supabase_realtime_*_replication_slot_meu_projeto

11. API Python dropa database
    DROP DATABASE IF EXISTS "_supabase_meu_projeto"

12. API Python limpa tabelas do sistema (database postgres)
    DELETE FROM project_members WHERE project_id = <id>
    DELETE FROM jobs WHERE project = 'meu_projeto'
    DELETE FROM projects WHERE id = <id>

13. API Python limpa registros do Supavisor
    DELETE FROM _supavisor.users WHERE tenant_external_id = 'meu_projeto'
    DELETE FROM _supavisor.tenants WHERE external_id = 'meu_projeto'

14. API Python despausa serviços críticos
    docker unpause realtime-dev.supabase-realtime
    docker unpause supabase-pooler

15. API Python chama delete_project.sh
    bash delete_project.sh meu_projeto
    
    Script remove diretório físico:
    rm -rf servidor/projects/meu_projeto/

16. API Python valida deleção
    - Verifica se database ainda existe
    - Retorna erros se houver falhas parciais

17. Resposta final
    {
      "project": "meu_projeto",
      "status": "success" | "partial_success",
      "message": "...",
      "errors": [...]  // Se houver
    }
```

### O Que é Removido

**Containers Docker:**
- nginx-meu_projeto
- gotrue-meu_projeto
- rest-meu_projeto
- storage-meu_projeto
- meta-meu_projeto
- imgproxy-meu_projeto

**Database PostgreSQL:**
- _supabase_meu_projeto (database completo)

**Registros do Sistema:**
- Tabela `projects`
- Tabela `project_members`
- Tabela `jobs`
- Tabela `_realtime.tenants`
- Tabela `_realtime.extensions`
- Tabela `_supavisor.tenants`
- Tabela `_supavisor.users`

**Replication Slots:**
- supabase_realtime_*_replication_slot_meu_projeto

**Arquivos Físicos:**
- servidor/projects/meu_projeto/ (pasta completa)
  - docker-compose.yml
  - .env
  - nginx/
  - pooler/
  - storage/ (todos os arquivos armazenados)

**Roteamento Traefik:**
- Removido automaticamente quando containers são deletados

### Por Que Pausar Realtime e Supavisor?

Durante a deleção, conexões ativas podem causar:
- Locks no database impedindo DROP DATABASE
- Tentativas de reconexão durante a deleção
- Erros de replication slot em uso

Pausar os containers garante que:
- Nenhuma nova conexão é criada
- Conexões existentes podem ser terminadas
- Deleção ocorre de forma limpa

### Tratamento de Erros

A API retorna `partial_success` se:
- Containers não foram removidos completamente
- Replication slots não foram dropados
- Database ainda existe após DROP DATABASE
- Script delete_project.sh falhou

Todos os erros são retornados no array `errors` da resposta.

---

## Limitações e Escalabilidade

### Limitações Atuais

**Por Projeto:**
- Porta única (range 4000-14000 = ~10.000 portas disponíveis)
- Recursos compartilhados (CPU, RAM, disco)

### Escalabilidade Horizontal

**Possível, mas não implementado:**
- Múltiplos servidores com PostgreSQL replicado
- Load balancer na frente dos Traefiks
- Storage distribuído (S3, MinIO)

**Por que PostgreSQL compartilhado?**
- Simplifica gerenciamento
- Reduz uso de recursos
- Facilita backups centralizados
- Supavisor gerencia pools eficientemente

---

## Diagramas de Fluxo

### Fluxo de Autenticação

```
┌─────────┐
│ Usuário │
└────┬────┘
     │ 1. Acessa https://ip:9091
     ▼
┌──────────┐
│ Authelia │ 2. Valida credenciais
└────┬─────┘
     │ 3. Redireciona para :4000
     ▼
┌─────────────┐
│ Nginx/Lua   │ 4. Serve Flutter Web
└─────┬───────┘
      │ 5. Usuário seleciona projeto
      ▼
┌─────────────┐
│ /set-project│ 6. Cria cookie assinado
└─────┬───────┘
      │ 7. Redireciona para Studio
      ▼
┌──────────────────┐
│ Supabase Studio  │ 8. Interface de gerenciamento
└──────────────────┘
```

### Fluxo de Requisição

```
┌────────┐
│ Studio │
└───┬────┘
    │ GET /rest/v1/tabela
    ▼
┌─────────────┐
│ Nginx/Lua   │ Lê cookie, busca service_role, injeta Authorization
└─────┬───────┘
      │ GET /projeto_x/rest/v1/tabela + Authorization
      ▼
┌─────────┐
│ Traefik │ Roteia baseado em PathPrefix
└────┬────┘
     │ GET /rest/v1/tabela (prefixo removido)
     ▼
┌──────────────┐
│ Nginx Projeto│ Valida apikey
└──────┬───────┘
       │ GET /tabela
       ▼
┌───────────┐
│ PostgREST │ Consulta database via Supavisor
└───────────┘
```

---

## Referências

- [Supabase Self-Hosting](https://supabase.com/docs/guides/self-hosting)
- [Traefik Docker Provider](https://doc.traefik.io/traefik/providers/docker/)
- [OpenResty Lua](https://openresty.org/en/)
- [Authelia Documentation](https://www.authelia.com/docs/)