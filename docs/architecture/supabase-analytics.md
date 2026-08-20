# Supabase Analytics por contexto de projeto

## Objetivo

O stack global executa Logflare como backend do Supabase Analytics e Vector como
coletor. A implementacao segue o modo self-hosted single-tenant do Supabase, mas
adapta a classificacao dos containers para a topologia multi-tenant deste
repositorio.

O pipeline antigo que gravava diretamente em `logs_db.public.logs` foi removido
do setup novo. O Logflare persiste seus metadados e tabelas no schema
`_analytics` do database `_supabase`.

## Componentes

- `supabase-analytics`: Logflare `v1.47.1`, compilado pelo Dockerfile local com
  as adaptacoes SQL em `servidor/volumes/analytics`;
- `supabase-vector-global`: `timberio/vector:0.53.0-alpine`;
- logging driver Fluent: envia nome, stream e mensagem de cada container para
  a porta de ingestao do Vector sem acesso a API Docker;
- `supabase-studio`: consulta Analytics pelo Nginx interno do Studio;
- Projects API: valida a identidade `studio-nginx`, aplica a allowlist e injeta
  a credencial privada usada para falar com o Logflare;
- PostgreSQL global: backend minimo do Logflare em `_supabase._analytics`.

O container do Analytics nao publica portas no host. A UI interna do Logflare
tambem nao e exposta, pois o modo self-hosted desabilita autenticacao de browser.

## Segredos

O `setup.sh` gera dois tokens diferentes, ambos com pelo menos 32 caracteres:

- `LOGFLARE_PUBLIC_ACCESS_TOKEN`: somente ingestao pelo Vector;
- `LOGFLARE_PRIVATE_ACCESS_TOKEN`: consultas administrativas feitas pela
  Projects API;
- `LOGFLARE_DB_ENCRYPTION_KEY`: chave Base64 de 32 bytes para colunas sensiveis
  mantidas pelo Logflare.

Os tokens reais ficam no lado servidor em `servidor/.analytics.env`, fora do
`.env` raiz herdado pelos containers de projeto. O processo do Studio nao usa o
token privado como credencial: o Compose sobrescreve a variavel exigida pelo
upstream com um valor nao secreto, e o hook server-side remove `Authorization`,
`X-API-KEY`, cookies e headers de identidade antes de chamar o Nginx.

A autenticacao Studio -> Nginx usa um segredo separado:

- `STUDIO_ANALYTICS_HMAC_SECRET`: conhecido somente pelo processo server-side do
  Studio e pelo Nginx do Studio;
- identidade assinada: `studio-server`.

Depois de validar essa assinatura, o Nginx remove os headers HMAC recebidos e
cria uma nova assinatura com `STUDIO_GATEWAY_HMAC_SECRET`:

- identidade assinada no segundo hop: `studio-nginx`;
- destino: Projects API.

A Projects API nao aceita `Authorization` ou `X-API-KEY` do caller para essa
rota. Ela injeta `LOGFLARE_PRIVATE_ACCESS_TOKEN` localmente ao criar a request
para `ANALYTICS_INTERNAL_URL`.

`STUDIO_ANALYTICS_HMAC_SECRET` precisa ser diferente de
`STUDIO_GATEWAY_HMAC_SECRET` e `PROJECTS_API_HMAC_SECRET`. O Nginx falha fechado
no startup se o segredo estiver ausente ou reutilizado.

Para rotacionar a chave de criptografia do Logflare, mova temporariamente a
chave antiga para `LOGFLARE_DB_ENCRYPTION_KEY_RETIRED`, gere a nova chave e
reinicie o Analytics. Remova a chave aposentada somente depois de o Logflare
confirmar a migracao.

## Contexto, isolamento e autorizacao

O servico e o armazenamento do Analytics sao globais, mas cada consulta e
obrigatoriamente contextualizada pelo projeto selecionado. O Nginx do Studio
intercepta `/api/platform/projects/<ref>/analytics/...` e exige grupo Authelia
`admin` antes de encaminhar a requisicao ao backend do Studio. O rewrite Lua
substitui o `default` usado pelo Studio self-hosted pelo `project_ref` resolvido
pelo contexto da aba. O Studio envia esse valor ao endpoint do Logflare como
parametro `project`, usado pelas CTEs nativas de `logs.all` para filtrar os
eventos. Membros e admins apenas de projeto nao podem consultar o Logflare
global.

A rota tecnica `/_internal/logflare/` nao depende de sessao de browser. Ela e
protegida por HMAC de servico antes de qualquer re-assinatura pelo gateway. Uma
request direta sem a identidade `studio-server`, com assinatura invalida,
timestamp expirado ou nonce repetido e rejeitada antes de chegar a Projects API.

O guard aceita somente os endpoints que o Studio fixado neste repositorio usa:

- `GET /api/endpoints/query/<name>`;
- `GET|POST /api/backends`;
- `GET|PUT|DELETE /api/backends/<id>`;
- `GET /api/sources`;
- `POST /api/rules`.

Qualquer outro path ou combinacao de metodo retorna erro. O guard tambem limita
query a 16 KiB, headers a 64 entradas/16 KiB e body a 256 KiB; mutacoes exigem
`Content-Length` e `application/json`, e `Transfer-Encoding` nao e aceito nessa
fronteira.

Uma rede Docker interna dedicada conecta PostgreSQL, Analytics, Vector e a API
Python do servidor. O Studio permanece fora dessa rede: seu backend chama o
Nginx local, que encaminha para a API Python remota, e somente a API acessa o
Logflare. Os containers de projeto permanecem fora da rede interna.

O Vector nao monta o Docker socket nem consulta a API Docker. Os servicos usam
o logging driver `fluentd` com conexao assincrona; o daemon envia os eventos ao
source `fluent` do Vector. O bind padrao e `127.0.0.1:24224` no node servidor.

As fontes continuam globais e usam os nomes esperados pelo Logflare. Para Auth,
PostgREST e Nginx, o Vector extrai o ref do sufixo do container. Para o Storage
global, ele analisa o JSON estruturado do upstream, valida `tenantId` como UUID
e registra também request ID, operação, método e path; evento sem UUID válido
permanece global e nunca é atribuído por aproximação. Para PostgreSQL, que é
compartilhado, o ref é extraído do database `_supabase_<project_ref>` presente
no `log_line_prefix`. Assim, a consulta de um projeto retorna somente seus
containers dedicados e as linhas do seu database.

O backend PostgreSQL do Logflare permanece em `_supabase._analytics`; ele e o
armazenamento central dos eventos e nao deve ser confundido com o database da
aplicacao. A selecao do database do projeto acontece na classificacao de cada
evento de log, nao trocando a conexao de metadados do Logflare por requisicao.

## Fontes encaminhadas

O Vector usa os nomes de fonte esperados pelo Logs Explorer:

- `gotrue.logs.prod`;
- `postgREST.logs.prod`;
- `storage.logs.prod.2`;
- `realtime.logs.prod`;
- `deno-relay-logs`;
- `postgres.logs`;
- `cloudflare.logs.prod` para os Nginx de projeto e gateways globais.

Auth, PostgREST e Nginx usam o sufixo do container. Storage usa o tenant UUID do
evento estruturado. O banco compartilhado usa o nome do database registrado no
prefixo da linha. Realtime usa um `external_id` UUID estavel, e Edge Functions,
Supavisor, API interna e Postgres-Meta tambem sao compartilhados; linhas desses
servicos que nao carregam um ref verificavel permanecem classificadas como
globais em vez de serem atribuidas ao projeto errado.

Somente eventos novos recebem a classificacao por projeto. Instalacoes que ja
tenham historico gravado com `project=default` precisam manter esse historico
como legado ou executar uma migracao de dados especifica antes de esperar que as
linhas antigas aparecam nas consultas contextualizadas.

## Operacao

Em uma instalacao nova, `tools/configure_studio_runtime.py`, chamado pelo setup,
gera `STUDIO_ANALYTICS_HMAC_SECRET` junto da configuracao local do Studio. Depois,
inicie ou recrie os stacks na ordem servidor e Studio:

```bash
cd servidor
docker compose --env-file .env up -d analytics vector

cd ../studio
docker compose --env-file .env up -d --build --force-recreate studio nginx
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

Antes de subir a versao que exige HMAC na rota interna de Analytics:

```bash
python3 tools/migrate_studio_analytics_hmac.py --dry-run
python3 tools/migrate_studio_analytics_hmac.py
```

O script gera o segredo somente quando necessario, preserva valores explicitos,
recusa reutilizacao dos outros segredos HMAC, cria backup do `studio/.env` e nao
imprime o segredo. Depois da migracao, faça rebuild/restart de Studio, Nginx e
Projects API.

Instalacoes antigas podem conservar o database `logs_db` e a role
`vector_writer`. Eles nao sao apagados automaticamente, pois isso destruiria o
historico legado. Depois de confirmar que o novo pipeline esta saudavel e que os
dados antigos nao precisam ser retidos, a remocao deve ser feita manualmente com
backup previo.

## Limitacoes e producao

- A porta Fluent deve permanecer limitada ao host ou a rede administrativa. No
  split-node, publique-a somente entre os nodes e aplique firewall.
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
