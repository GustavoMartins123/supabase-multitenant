# Supabase Analytics global

## Objetivo

O stack global executa Logflare como backend do Supabase Analytics e Vector como
coletor. A implementacao segue o modo self-hosted single-tenant do Supabase, mas
adapta a classificacao dos containers para a topologia multi-tenant deste
repositorio.

O pipeline antigo que gravava diretamente em `logs_db.public.logs` foi removido
do setup novo. O Logflare persiste seus metadados e tabelas no schema
`_analytics` do database `_supabase`.

## Componentes

- `supabase-analytics`: `supabase/logflare:1.43.1`;
- `supabase-vector-global`: `timberio/vector:0.53.0-alpine`;
- `supabase-studio`: consulta o Logflare internamente em `http://analytics:4000`;
- PostgreSQL global: backend minimo do Logflare em `_supabase._analytics`.

O container do Analytics nao publica portas no host. A UI interna do Logflare
tambem nao e exposta, pois o modo self-hosted desabilita autenticacao de browser.

## Segredos

O `setup.sh` gera dois tokens diferentes, ambos com pelo menos 32 caracteres:

- `LOGFLARE_PUBLIC_ACCESS_TOKEN`: somente ingestao pelo Vector;
- `LOGFLARE_PRIVATE_ACCESS_TOKEN`: consultas administrativas feitas pelo backend
  do Studio.
- `LOGFLARE_DB_ENCRYPTION_KEY`: chave Base64 de 32 bytes para colunas sensiveis
  mantidas pelo Logflare.

Os tokens ficam em `servidor/.analytics.env`, fora do `.env` raiz herdado pelos
containers de projeto. Somente o token privado e copiado para
`studio/.analytics.env`, usado apenas pelo container do Studio.
Ele nao e entregue ao Flutter nem inserido nos templates dos projetos.

`servidor/verify_key_config.sh` valida presenca, tamanho, diferenca entre os
tokens e consistencia do token privado entre servidor e Studio.

Para rotacionar a chave de criptografia, mova temporariamente a chave antiga
para `LOGFLARE_DB_ENCRYPTION_KEY_RETIRED`, gere a nova chave e reinicie o
Analytics. Remova a chave aposentada somente depois de o Logflare confirmar a
migracao.

## Isolamento e autorizacao

O Analytics e global. O Nginx do Studio intercepta
`/api/platform/projects/<ref>/analytics/...` e exige grupo Authelia `admin` antes
de encaminhar a requisicao ao backend do Studio. Membros e admins apenas de
projeto nao podem consultar o Logflare global.

Uma rede Docker interna dedicada conecta PostgreSQL, Analytics, Vector e a API
Python do servidor. O Studio permanece fora dessa rede: seu backend chama o
Nginx local, que encaminha para a API Python remota, e somente a API acessa o
Logflare. Os containers de projeto permanecem fora da rede interna.

Os eventos usam `project=default` para manter compatibilidade com as fontes
single-tenant criadas pelo Logflare. Quando o nome do container possui um sufixo
de projeto, o Vector preserva esse ref em `metadata.tenant_project`. Esse campo e
informativo; ele nao substitui autorizacao no gateway.

## Fontes encaminhadas

O Vector usa os nomes de fonte esperados pelo Logs Explorer:

- `gotrue.logs.prod`;
- `postgREST.logs.prod`;
- `storage.logs.prod.2`;
- `realtime.logs.prod`;
- `deno-relay-logs`;
- `postgres.logs`;
- `cloudflare.logs.prod` para gateways e servicos globais sem painel proprio.

Auth, PostgREST, Storage e Nginx usam o sufixo do container para preencher
`metadata.tenant_project`. Realtime, Supavisor, Edge Functions, API interna,
Postgres-Meta e banco sao compartilhados; nem toda linha emitida por esses
servicos contem contexto suficiente para atribuir com seguranca um projeto.

## Operacao

Em uma instalacao nova, o setup gera e distribui os tokens. Depois, inicie ou
recrie os stacks na ordem servidor e Studio:

```bash
cd servidor
docker compose --env-file .env up -d analytics vector

cd ../studio
docker compose --env-file .env up -d --force-recreate studio nginx
```

Verificacoes uteis:

```bash
docker compose --env-file servidor/.env -f servidor/docker-compose.yml ps analytics vector
docker logs --tail 100 supabase-analytics
docker logs --tail 100 supabase-vector-global
```

Os healthchecks sao internos; as portas `4000` do Analytics e `9001` do Vector
nao sao publicadas no host.

## Upgrade de instalacoes existentes

Instalacoes antigas podem conservar o database `logs_db` e a role
`vector_writer`. Eles nao sao apagados automaticamente, pois isso destruiria o
historico legado. Depois de confirmar que o novo pipeline esta saudavel e que os
dados antigos nao precisam ser retidos, a remocao deve ser feita manualmente com
backup previo.

## Limitacoes e producao

- Vector ainda recebe acesso read-only ao Docker socket. Isso permanece um risco
  operacional e deve migrar para um socket proxy/host-agent restrito.
- O backend minimo usa o mesmo cluster PostgreSQL observado. Se o banco falhar,
  o Analytics tambem falha; para producao critica, use um PostgreSQL separado.
- Retencao e limites de disco do Logflare precisam ser definidos conforme a
  carga real antes de habilitar logs muito verbosos.
- Logs podem conter dados pessoais ou operacionais. Mantenha redaction nos
  servicos de origem e nao exponha o dashboard direto do Logflare.

## Referencias oficiais

- [Self-hosting com Docker](https://supabase.com/docs/guides/self-hosting/docker)
- [Configuracao self-hosted do Analytics](https://supabase.com/docs/guides/self-hosting/analytics/config)
- [Self-hosting do Logflare](https://docs.logflare.app/self-hosting/)
- [Compose oficial de logs](https://github.com/supabase/supabase/blob/master/docker/docker-compose.logs.yml)
- [Pipeline Vector oficial](https://github.com/supabase/supabase/blob/master/docker/volumes/logs/vector.yml)
- [Configuracao runtime do Logflare](https://github.com/Logflare/logflare/blob/master/config/runtime.exs)
