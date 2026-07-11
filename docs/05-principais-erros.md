# Principais erros e diagnóstico

Este documento é um runbook curto para falhas comuns.

A arquitetura, os fluxos de lifecycle e o comportamento do cache não são repetidos aqui. Quando o diagnóstico depender desses assuntos, use as fontes canônicas:

- [Arquitetura do sistema](00-arquitetura.md)
- [Control plane](architecture/control-plane.md)
- [Lifecycle dos projetos](architecture/project-lifecycle.md)
- [OpenResty/Lua](architecture/openresty-lua.md)
- [Realtime multi-tenant](09-autenticacao-multi-tenant-realtime.md)

## Antes de alterar qualquer coisa

Colete primeiro:

```bash
docker ps -a
docker network inspect rede-supabase
docker logs projects-api --tail 200
docker logs nginx --tail 200
docker logs traefik-traefik-1 --tail 200
```

Para um projeto específico:

```bash
docker ps -a --filter "name=<project_ref>"
cd servidor/projects/<project_ref>
docker compose --env-file ../../.env --env-file .env ps
```

Não remova database, tenant, slot ou diretório manualmente antes de identificar a etapa que falhou. Operações de lifecycle distribuem estado entre PostgreSQL, Docker, Realtime, Supavisor e Studio.

## 1. `502 Bad Gateway` ao acessar um projeto

### Verifique o container do Nginx

```bash
docker ps -a --filter "name=supabase-nginx-<project_ref>"
docker logs supabase-nginx-<project_ref> --tail 200
```

### Verifique a rota do Traefik

```bash
docker logs traefik-traefik-1 --tail 200 | grep -F '<project_ref>'
```

### Verifique a rede

```bash
docker network inspect rede-supabase
docker inspect supabase-nginx-<project_ref> --format '{{json .NetworkSettings.Networks}}'
```

Se o projeto existe no control plane, mas os containers estão ausentes, prefira a ação de recriação/start pelo Studio ou pela Projects API. Subir manualmente o compose pode esconder um job incompleto.

## 2. Projeto criado ou duplicado não aparece no Studio

Consulte o job:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, project, action, status, progress, current_step, error_code, message
FROM jobs
WHERE project = '<project_ref>'
ORDER BY created_at DESC
LIMIT 5;
"
```

Confirme o projeto:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT id, name, display_name, owner_id, project_key_version
FROM projects
WHERE name = '<project_ref>';
"
```

Não grave `anon_key`, `service_role` ou `config_token` manualmente. Os valores persistidos usam envelope encryption e precisam ser salvos pelo fluxo da API.

## 3. Job ficou em `queued` ou `running`

A API tenta recuperar no startup apenas ações conhecidas como seguras.

Consulte os detalhes:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, action, status, current_step, progress,
       is_idempotent, retryable, retry_of, attempt,
       error_code, stdout_tail, stderr_tail
FROM jobs
WHERE job_id = '<job_uuid>';
"
```

Interpretação:

- `queued`: pode ainda estar aguardando a fila do projeto;
- `running`: confirme se o `projects-api` continua executando;
- `failed` com revisão manual: a API foi reiniciada durante uma operação não idempotente;
- `retryable = true`: use o endpoint/UI de retry em vez de repetir scripts manualmente.

## 4. Erro durante rename

O rename pode alterar:

- diretório;
- database;
- containers;
- tenant do Supavisor;
- slot principal do Realtime;
- rota do Traefik;
- snippets do Studio.

Consulte o histórico:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, old_name, new_name, status, error,
       created_at, completed_at
FROM project_name_history
ORDER BY created_at DESC
LIMIT 20;
"
```

O UUID e o `external_id` do Realtime não devem mudar.

Se o projeto foi renomeado, mas os snippets não apareceram, verifique o aviso do job e os logs:

```bash
docker logs projects-api --tail 200 | grep -i snippet
docker logs nginx --tail 200 | grep -i snippet
```

Falha na migração dos snippets é best-effort e não invalida o rename já concluído.

## 5. Chave rotacionada, mas o Studio usa a chave antiga

O cache atual é versionado. A rotação deve:

1. atualizar os segredos;
2. incrementar `project_key_version`;
3. chamar a invalidação ativa no OpenResty;
4. manter verificação periódica de versão como fallback.

Consulte a versão:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT name, project_key_version
FROM projects
WHERE name = '<project_ref>';
"
```

Verifique os logs:

```bash
docker logs projects-api --tail 200 | grep -i 'service.key\|cache'
docker logs nginx --tail 200 | grep -i 'service.key\|cache'
```

Reiniciar o Nginx limpa o cache, mas não é o mecanismo normal de consistência. Antes disso, valide:

- `STUDIO_CACHE_INVALIDATION_URL`;
- `NGINX_SHARED_TOKEN` nos dois lados;
- `X-Internal-Service: projects-api`;
- conectividade entre Projects API e Studio;
- endpoint de versão da chave.

Detalhes: [Arquitetura OpenResty/Lua](architecture/openresty-lua.md).

## 6. Realtime retorna `403`

Confirme primeiro os identificadores:

- `external_id` do Realtime: UUID do projeto;
- issuer do JWT: mesmo UUID;
- database e slot principal: baseados no project ref;
- Host do WebSocket: `<project_uuid>.localhost`.

Consulte o tenant:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT external_id
FROM _realtime.tenants
WHERE external_id = '<project_uuid>';
"
```

Quando uma requisição identifica um tenant, falha do JWT específico não cai para o secret global. O `403` pode indicar:

- issuer diferente do UUID;
- tenant ausente;
- JWT assinado com outro secret;
- Nginx injetando o Host antigo/incorreto;
- API key inválida antes do proxy WebSocket.

Detalhes: [Realtime multi-tenant](09-autenticacao-multi-tenant-realtime.md).

## 7. Replication slot ativo ou travado

Liste os slots:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT slot_name, database, active, active_pid
FROM pg_replication_slots
ORDER BY slot_name;
"
```

Existem dois formatos relevantes:

```text
supabase_realtime_replication_slot_<project_ref>
supabase_realtime_messages_replication_slot_<hash_do_project_uuid>
```

Não procure o slot temporário apenas pelo nome do projeto; ele usa hash do UUID.

Durante delete, a Projects API remove o tenant/pools, drena conexões e valida reconexões antes de remover o database. Prefira corrigir e repetir o job de deleção.

Para intervenção manual, confirme que o projeto não está em uso e termine apenas o PID associado ao slot correto:

```sql
SELECT pg_terminate_backend(active_pid)
FROM pg_replication_slots
WHERE slot_name = '<slot_exato>'
  AND active_pid IS NOT NULL;
```

Evite pausar o Realtime global, pois isso afeta todos os tenants.

## 8. Database não pode ser removido

Liste as conexões:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT pid, usename, application_name, client_addr, state
FROM pg_stat_activity
WHERE datname = '_supabase_<project_ref>';
"
```

Se novas conexões reaparecem, verifique o tenant e os pools do Supavisor antes de executar `DROP DATABASE`.

A deleção atual falha de propósito quando o pooler continua reconectando. Isso preserva o database em vez de produzir uma remoção parcial.

Detalhes: [Lifecycle dos projetos](architecture/project-lifecycle.md#deleção).

## 9. `too many clients already`

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT count(*) FROM pg_stat_activity;
SHOW max_connections;
"
```

Agrupe por database e aplicação:

```sql
SELECT datname, application_name, state, count(*)
FROM pg_stat_activity
GROUP BY datname, application_name, state
ORDER BY count(*) DESC;
```

Antes de aumentar `max_connections`, valide:

- pool size do Supavisor;
- limite de clientes por tenant;
- pool do PostgREST;
- serviços em loop de reconexão;
- jobs de delete/rename incompletos.

Guias:

- [PostgreSQL](02-Como-aumentar-o-limite-conexoes-postgres.md)
- [Supavisor](03-Como-aumentar-o-limite-conexoes-pooler.md)
- [Realtime](04-Como-aumentar-o-limite-conexoes-realtime.md)

## 10. Storage quebrado após duplicação

Confirme se a duplicação foi `schema-only` ou `with-data`.

No modo com dados, valide:

- registros em `storage.objects`;
- arquivos no diretório do projeto;
- ownership e permissões;
- extended attributes quando usados pela versão atual do Storage;
- histórico de migrations de Auth e Storage.

Não copie apenas o database e espere que os objetos físicos apareçam.

## 11. Usuário não consegue entrar no Studio

Verifique:

```bash
docker logs authelia --tail 200
docker logs nginx --tail 200
```

Confirme no arquivo do Authelia:

- usuário não desativado;
- grupo `active`;
- hash Argon2id válido;
- sintaxe YAML;
- certificado ainda válido.

A identidade do control plane é sincronizada depois da autenticação. Se o login funciona, mas o usuário recebe acesso negado, consulte `users`, `user_groups` e os logs da sincronização.

Detalhes: [Gerenciamento de usuários no Authelia](07-gerenciamento-usuarios-authelia.md).

## 12. Postgres-Meta falha ou retorna database incorreto

Execute a validação sem imprimir segredos:

```bash
bash servidor/verify_key_config.sh
```

Confirme:

- `PG_META_CRYPTO_KEY` igual na API e no Postgres-Meta;
- `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` igual na API e no Studio;
- `PG_META_INTERNAL_URL` apontando para host permitido;
- fallback usando `meta_trap` e `meta_guest`;
- membership e service role do projeto válidas.

Guias:

- [Hardening do Postgres-Meta](10-hardening-postgres-meta.md)
- [Rotação de segredos e conexões](11-rotacao-cripto-conexoes.md)

## Comandos úteis

### Logs globais

```bash
docker logs projects-api --tail 200 -f
docker logs nginx --tail 200 -f
docker logs traefik-traefik-1 --tail 200 -f
docker logs realtime-dev.supabase-realtime --tail 200 -f
docker logs supabase-pooler --tail 200 -f
docker logs supabase-db --tail 200 -f
```

### Estado do control plane

```sql
SELECT id, name, owner_id, project_key_version FROM projects ORDER BY name;
SELECT job_id, project, action, status, current_step FROM jobs ORDER BY created_at DESC;
SELECT * FROM project_name_history ORDER BY created_at DESC;
```

### Rede

```bash
docker network inspect rede-supabase
docker inspect <container> --format '{{json .NetworkSettings.Networks}}'
```

## Ao abrir uma issue

Inclua:

- versão/commit usado;
- topologia de uma ou duas máquinas;
- operação executada;
- `project_ref` anonimizado, quando necessário;
- etapa e código de erro do job;
- logs sem JWTs, cookies, HMACs, senhas ou connection strings;
- estado dos containers e da rede;
- passos para reproduzir.
