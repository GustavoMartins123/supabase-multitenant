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
- `supabase-vector-docker-proxy`: acesso somente leitura as secoes `containers`
  e `events` da API Docker usadas para descobrir containers e acompanhar logs;
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

## Contexto, isolamento e autorizacao

O servico e o armazenamento do Analytics sao globais, mas cada consulta e
obrigatoriamente contextualizada pelo projeto selecionado. O Nginx do Studio
intercepta
`/api/platform/projects/<ref>/analytics/...` e exige grupo Authelia `admin` antes
de encaminhar a requisicao ao backend do Studio. O rewrite Lua substitui o
`default` usado pelo Studio self-hosted pelo `project_ref` validado do cookie. O
Studio envia esse valor ao endpoint do Logflare como parametro `project`, usado
pelas CTEs nativas de `logs.all` para filtrar os eventos. Membros e admins apenas
de projeto nao podem consultar o Logflare global.

Uma rede Docker interna dedicada conecta PostgreSQL, Analytics, Vector e a API
Python do servidor. O Studio permanece fora dessa rede: seu backend chama o
Nginx local, que encaminha para a API Python remota, e somente a API acessa o
Logflare. Os containers de projeto permanecem fora da rede interna.

O Vector nao monta o Docker socket. Ele acessa
`http://vector-docker-proxy:2375` por uma rede interna exclusiva. O proxy nao
publica portas, bloqueia `POST` e libera apenas as secoes `containers`, `events`,
`ping` e `version` da API Docker.

As fontes continuam globais e usam os nomes single-tenant esperados pelo
Logflare. Para Auth, PostgREST, Storage e Nginx, o Vector extrai o ref do sufixo
do container e grava o valor tanto em `project` quanto em
`metadata.tenant_project`. Para PostgreSQL, que e compartilhado, o ref e extraido
do database `_supabase_<project_ref>` presente no `log_line_prefix`. Assim, a
consulta de um projeto retorna somente seus containers dedicados e as linhas do
seu database.

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

Auth, PostgREST, Storage e Nginx usam o sufixo do container. O banco compartilhado
usa o nome do database registrado no prefixo da linha. Realtime usa um
`external_id` UUID estavel, e Edge Functions, Supavisor, API interna e
Postgres-Meta tambem sao compartilhados; linhas desses servicos que nao carregam
um ref verificavel permanecem classificadas como globais em vez de serem
atribuidas ao projeto errado.

Somente eventos novos recebem a classificacao por projeto. Instalacoes que ja
tenham historico gravado com `project=default` precisam manter esse historico
como legado ou executar uma migracao de dados especifica antes de esperar que as
linhas antigas aparecam nas consultas contextualizadas.

## Operacao

Em uma instalacao nova, o setup gera e distribui os tokens. Depois, inicie ou
recrie os stacks na ordem servidor e Studio:

```bash
cd servidor
docker compose --env-file .env up -d analytics vector-docker-proxy vector

cd ../studio
docker compose --env-file .env up -d --force-recreate studio nginx
```

Verificacoes uteis:

```bash
docker compose --env-file servidor/.env -f servidor/docker-compose.yml ps analytics vector-docker-proxy vector
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

- O proxy reduz o alcance de uma falha no Vector, mas ainda permite leitura de
  toda a secao `containers`, pois a politica da imagem e definida por prefixo da
  API, nao por endpoint individual. Ele deve permanecer em rede exclusiva e sem
  porta publicada.
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
