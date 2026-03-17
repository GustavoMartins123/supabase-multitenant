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
   
   Usa template pré-configurado com:
   - roles.sql (anon, service_role, authenticator, etc.)
   - jwt.sql (validação JWT)
   - webhooks.sql, logs.sql, realtime.sql, etc.

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

**Template _supabase_template:**
- Criado uma vez no setup inicial
- Contém todos os schemas e configurações base
- Cada projeto é clonado desse template

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

## Por projeto

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

## Duplicação de Projeto

### Modos de Duplicação

**Schema-Only (padrão):**
- Copia apenas estrutura (schemas, tabelas, functions, policies)
- Copia histórico de migrations (auth.schema_migrations, storage.migrations)
- Não copia dados das tabelas
- Não copia arquivos do storage
- Uso: Criar projeto novo com mesma estrutura

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