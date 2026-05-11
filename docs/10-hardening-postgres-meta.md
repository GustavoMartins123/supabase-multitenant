# Hardening do Postgres-Meta Global

Esta instalação usa um `postgres-meta-global` compartilhado entre projetos. Quando a conexão dinâmica criptografada falha, o serviço deve cair no banco vazio `meta_trap`, usando o usuário restrito `meta_guest`.

## Objetivo

Se alguém obtiver apenas a senha do `meta_guest`, o impacto esperado é:

- conseguir conectar somente no banco `meta_trap`;
- não conseguir conectar em `postgres`, `_supabase`, `_supabase_template`, `logs_db`, `template0`, `template1` ou bancos `_supabase_*`;
- não conseguir criar tabelas, tabelas temporárias, schemas, funções ou extensões;
- não conseguir assumir roles administrativas;
- não conseguir ler arquivos do servidor nem executar comandos via `COPY PROGRAM`.

## Threat Model

Este hardening não tenta proteger contra acesso root à máquina ou controle direto do container PostgreSQL. O objetivo é conter uma cadeia de falha no fluxo do `postgres-meta-global`:

- usuário autenticado no Studio;
- token de usuário válido e `service_role` válida do projeto;
- rota de `pg-meta` recebendo uma entrada inesperada;
- API Python ou `postgres-meta-global` falhando ao resolver/descriptografar a conexão dinâmica;
- fallback tentando conectar no banco padrão.

Nesse cenário, o fallback deve sempre cair em `meta_trap` com `meta_guest`, sem conseguir pivotar para bancos reais, extensões, arquivos do servidor ou roles administrativas.

## Controles Aplicados

No script `servidor/volumes/db/create_template.sh`, o `meta_guest` deve ser criado com:

- `LOGIN`, mas sem `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`;
- `NOINHERIT`;
- `CONNECTION LIMIT 5`;
- `search_path = 'pg_catalog'`;
- `statement_timeout = '5s'`;
- `idle_in_transaction_session_timeout = '5s'`;
- apenas `CONNECT` no banco `meta_trap`;
- sem `CREATE` e sem `TEMPORARY` no `meta_trap`;
- sem permissões no schema `public`;
- sem roles pré-definidas sensíveis, como `pg_monitor`, `pg_read_all_data`, `pg_write_all_data`, `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program` e `pg_signal_backend`.

O banco `meta_trap` também possui um `EVENT TRIGGER` chamado `block_meta_guest_extension_ddl`, usado para bloquear `CREATE EXTENSION`, `ALTER EXTENSION` e `DROP EXTENSION` quando o usuário da sessão for `meta_guest`. Isso é necessário porque a imagem Supabase Postgres usa `supautils.privileged_extensions`, que pode delegar criação de extensões para `supabase_admin`.

Na API Python, o endpoint `/api/projects/{ref}/meta...` também aplica controles antes de chamar o `postgres-meta-global`:

- `ref` passa por `validate_project_id`, aceitando somente o padrão interno de project id;
- a conexão do projeto é sempre montada internamente como `_supabase_{ref}`;
- query string, params e fragment do `DB_DSN` são descartados ao montar a conexão do pg-meta;
- `PG_META_INTERNAL_URL` é validado na inicialização e deve apontar para host permitido em `PG_META_ALLOWED_HOSTS`, sem path, query string, fragment ou userinfo;
- a API não repassa headers de conexão vindos do cliente; ela gera apenas `x-connection-encrypted`;
- o proxy exige usuário autenticado, membership do projeto e `service_role` válida do projeto.

## Checklist De Validação

Execute estes testes após atualizar a imagem `supabase/postgres`, recriar o banco ou alterar permissões:

```sql
SELECT current_user, session_user, current_database();

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolinherit, rolconnlimit
FROM pg_roles
WHERE rolname = 'meta_guest';

SELECT datname,
       has_database_privilege('meta_guest', datname, 'CONNECT') AS connect,
       has_database_privilege('meta_guest', datname, 'CREATE') AS create_db,
       has_database_privilege('meta_guest', datname, 'TEMPORARY') AS temp
FROM pg_database
ORDER BY datname;

SHOW search_path;
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW supautils.privileged_extensions;

SET ROLE supabase_admin;
CREATE TEMP TABLE meta_guest_temp_check(id int);
CREATE TABLE public.meta_guest_table_check(id int);
CREATE EXTENSION hstore;
CREATE EXTENSION dblink;
CREATE EXTENSION http;
CREATE EXTENSION pg_net;
SELECT pg_read_file('/etc/passwd', 0, 100);
SELECT pg_ls_dir('/');
COPY (SELECT 1) TO PROGRAM 'id';
DROP SCHEMA meta_guard CASCADE;
DROP EVENT TRIGGER block_meta_guest_extension_ddl;
```

Resultado esperado:

- `meta_guest` deve ter `CONNECT = true` somente em `meta_trap`;
- `CREATE` e `TEMPORARY` devem ser `false` para `meta_guest` em todos os bancos;
- todos os comandos de criação, extensão, leitura de arquivo, execução de programa, troca de role e remoção de proteção devem falhar;
- `pg_extension` em `meta_trap` deve conter apenas extensões essenciais já esperadas, normalmente `plpgsql`.

## Limitação Conhecida

O usuário ainda pode consultar catálogos globais como `pg_database` e, portanto, listar nomes de bancos com comandos como `\l`. Isso não equivale a permissão de conexão. A mitigação aplicada é impedir `CONNECT`, `CREATE`, `TEMPORARY`, extensão e escalada de privilégios.