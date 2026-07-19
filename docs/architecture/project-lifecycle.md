# Lifecycle dos projetos

O lifecycle é orquestrado pela Projects API, mas a execução física (Docker e os scripts em `servidor/generateProject/`) acontece no [host-agent](host-agent.md): a API grava a intenção assinada no banco e aguarda o agent executar o comando fechado.

Operações longas são representadas por jobs persistentes. O endpoint HTTP normalmente cria o job e retorna seu identificador; a execução continua na fila serializada do projeto.

## Identificadores usados

Antes de acompanhar qualquer fluxo, diferencie:

- `project_uuid`: `projects.id`, identidade canônica e imutável;
- `tenant_uuid`: vínculo persistido com Realtime/JWT/backups; equivale a
  `projects.id` nos projetos novos e pode preservar o UUID legado;
- `project_ref`: slug mutável usado em URL e recursos físicos;
- `_supabase_<project_ref>`: database;
- Realtime tenant: identificado pelo UUID;
- Supavisor tenant: identificado pelo project ref;
- slot principal do CDC: sufixado pelo project ref;
- slot temporário de broadcast: sufixado por hash derivado do UUID.

## Criação

Fluxo resumido:

1. a API valida usuário e nome;
2. gera uma única vez `projects.id` e persiste o mesmo valor em `tenant_uuid`;
3. cria o job já com os dois identificadores duráveis;
4. o script gera JWT secret, anon key, service role e config token;
5. cria `_supabase_<project_ref>` a partir de `_supabase_template`;
6. gera `.env`, compose, Dockerfile e configuração Nginx;
7. registra o tenant do Realtime com `external_id = tenant_uuid`;
8. registra o tenant do Supavisor com `external_id = project_ref`;
9. sobe os containers;
10. persiste os segredos criptografados no registro do projeto;
11. atualiza status e auditoria.

O JWT usa o UUID como issuer:

```json
{
  "role": "anon",
  "iss": "<tenant_uuid>"
}
```

O nome do database e do slot principal continua usando o project ref. O slot temporário de broadcast usa um hash derivado do UUID do tenant.

### Rollback

O script mantém estado dos recursos criados e tenta remover, na ordem necessária:

- diretórios;
- database;
- tenant do Realtime;
- tenant do Supavisor.

O rollback de shell não substitui a validação final da API. Falhas parciais devem aparecer no job.

## Duplicação

A duplicação cria outro projeto, com novo UUID, novas chaves e novos tenants.

Modos:

- `schema-only`: copia estrutura e históricos de migration necessários;
- `with-data`: copia schema, dados e storage.

Mesmo quando os dados são copiados, a identidade do projeto novo é independente:

- novo UUID;
- novo issuer JWT;
- novo tenant Realtime;
- novo tenant Supavisor;
- novas API keys;
- novo config token.

A cópia não deve reutilizar segredos do projeto de origem.

## Rename

Rename altera o project ref, mas preserva tanto `projects.id` quanto
`projects.tenant_uuid`.

Recursos que acompanham o novo nome:

- diretório do projeto;
- `.env` e templates;
- nomes dos containers;
- rota do Traefik;
- database `_supabase_<project_ref>`;
- tenant do Supavisor;
- slot principal do Realtime;
- referências físicas usadas pelos serviços;
- diretórios de snippets do Studio.

Recursos que permanecem com a mesma identidade:

- UUID do projeto;
- membership;
- notas, tags, hints e threads;
- auditoria;
- Realtime `external_id`;
- slot temporário de broadcast derivado do UUID;
- chaves JWT, salvo quando outra operação de rotação for solicitada.

### Histórico

Cada rename cria um registro em `project_name_history` com:

- nome anterior;
- nome novo;
- path anterior;
- path novo;
- job associado;
- status;
- erro e timestamps.

### Supavisor

O tenant antigo do Supavisor precisa ser removido antes da criação do novo para evitar conflito de identidade.

Se houver falha depois da remoção, o rollback tenta restaurar o tenant antigo.

### Realtime

O tenant continua identificado pelo UUID. O rename atualiza os recursos ligados ao database, incluindo slot principal e configuração da extensão CDC, sem trocar o `external_id` canônico.

### Snippets

O Supabase Studio armazena snippets em diretórios que incluem usuário e slug do projeto.

Depois do rename principal, a API chama o endpoint interno do OpenResty para renomear esses diretórios.

A migração é best-effort:

- falha de snippets não invalida o projeto já renomeado;
- o job registra um aviso;
- os diretórios podem exigir correção manual ou retry específico.

## Rotação das API keys

A rotação padrão gera novos tokens anon e service role usando o JWT secret existente.

Isso evita invalidar imediatamente todas as sessões de usuários finais.

Fluxo:

1. gera novos tokens;
2. atualiza arquivos do projeto;
3. atualiza configuração do Nginx;
4. persiste os segredos com envelope encryption;
5. incrementa `project_key_version`;
6. invalida o cache de service key do Studio;
7. atualiza o job e a auditoria.

A invalidação do cache faz parte do sucesso da operação. Existe fallback por verificação de versão e TTL, mas a API tenta a invalidação ativa antes de concluir.

### Expiração

A API extrai metadata de expiração dos JWTs e pode avisar o Studio quando as chaves estão expiradas ou próximas do vencimento.

A janela é configurada por `KEY_EXPIRY_WARNING_DAYS`.

### Rotação do JWT secret

Trocar o JWT secret é uma operação diferente e de impacto maior:

- invalida tokens existentes;
- exige sincronização com Realtime e serviços;
- encerra sessões de Auth;
- precisa de janela de manutenção e plano de rollback.

Ela não deve ser confundida com a rotação comum das API keys.

## Settings e recriação de serviços

A alteração de settings grava o `.env` atomicamente e informa os serviços afetados.

Exemplos:

- Auth para opções do GoTrue;
- REST para schemas e pool do PostgREST;
- Storage e Nginx para limite de arquivo;
- Storage para transformação de imagens.

A recriação é executada como job idempotente conhecido.

## Pontos de restauração

Um ponto de restauração captura **dados, não identidade**: o dump do
database `_supabase_<project_ref>` (sem o schema `realtime`, que é
capturado à parte como no duplicate) e o tar do diretório `storage/`,
mais um `manifest.json` com UUID, ref na época, versão do Postgres e as
tabelas da publication do Realtime.

Ficam fora do ponto: `.env`, JWT secret, anon/service keys, config token,
tenants do Realtime/Supavisor e configuração de containers. Por isso um
ponto continua restaurável depois de rotação de chaves e de rename — os
arquivos vivem em `servidor/backups/<tenant_uuid>/<point_id>/`, chaveados
pelo `tenant_uuid` persistido no control plane e espelhado em `PROJECT_UUID`
no `.env` do projeto (imutável no rename).

### Captura (fria)

O backup é frio por decisão de produto: o script para os serviços do
projeto (o Postgres compartilhado continua de pé), encerra os pools do
tenant no Supavisor, captura banco + storage de forma atômica
(`<id>.tmp` + rename) e religa somente os containers que estavam rodando.

### Restauração

1. para os serviços do projeto, shutdown do tenant Realtime e terminate
   dos pools do Supavisor;
2. captura um **ponto automático de segurança** com o estado atual e emite
   `SAFETY_BACKUP_COMPLETE`;
3. dropa os replication slots, renomeia o database atual para
   `_supabase_<ref>_prerestore` (é o plano de rollback, não um DROP);
4. cria o database novo, restaura o dump e reaplica as correções
   conhecidas do duplicate: partições de `realtime.messages`, publications
   (com as tabelas do manifest), `TRUNCATE realtime.subscription`,
   `search_path`, override do `supabase_storage_admin`, grants e validação
   do contrato pgvector;
5. recria o slot principal, troca o diretório `storage/`
   (`storage.prerestore` como fallback), religa os containers, espera o
   Storage ficar healthy e sincroniza os wrappers vetoriais;
6. só então remove `_supabase_<ref>_prerestore` e `storage.prerestore`.

Falhas disparam rollback compensatório com marker `ROLLBACK_COMPLETE`,
como no rename. O ponto de segurança sobrevive à falha e vira um ponto
normal na listagem.

A restauração reverte também os usuários e sessões do Auth (o schema
`auth` faz parte do banco). Keys e URL do projeto não mudam.

### Control plane

A tabela `project_restore_points` guarda título (default: data/hora),
descrição, status (`creating`, `ready`, `restoring`, `deleting`,
`failed`), flag de ponto automático, tamanho, contadores de restauração e
o job associado. Limite de 15 pontos ativos por projeto; a restauração
exige uma vaga livre para o ponto automático. Todas as operações são
auditadas em `studio_audit_log` e acessíveis a qualquer membro do projeto
ou admin global. `backup` e `restore` não são idempotentes: o recovery da
API religa na intenção existente do host-agent em vez de reexecutar. O
delete do projeto remove `servidor/backups/<uuid>/` junto com os arquivos.

## Start, stop e restart

Essas operações:

- consultam os containers associados ao projeto;
- são serializadas na fila do projeto;
- atualizam status e auditoria;
- são marcadas como idempotentes e retryable.

## Deleção

A deleção precisa remover recursos sem permitir que Supavisor ou outros serviços recriem conexões no meio do processo.

Fluxo atual:

1. valida admin, membership e senha de deleção;
2. cria job de delete;
3. remove ou encerra os pools do tenant no Supavisor;
4. drena conexões ativas do database;
5. confirma que o pooler não continua reconectando;
6. remove containers do projeto;
7. limpa tenant e extensões do Realtime;
8. remove replication slots;
9. remove o database;
10. limpa tenant e usuários do Supavisor;
11. remove registros do control plane;
12. remove diretório físico;
13. valida o resultado e registra auditoria.

### Proteção do database

Se o Supavisor continuar abrindo conexões mesmo após a remoção do tenant e drenagem, a deleção deve falhar antes do `DROP DATABASE`.

Preservar um database ainda referenciado é mais seguro do que concluir uma deleção parcial e inconsistente.

### Resultado parcial

Falhas de infraestrutura podem deixar:

- containers;
- tenant;
- slot;
- diretório;
- registros centrais.

O job deve expor etapa, mensagem, código de erro e tails de saída para permitir recuperação manual.

## Recovery e retry

### Ações idempotentes

Atualmente o sistema trata como idempotentes:

- start;
- stop;
- restart;
- recreate services.

Essas ações podem ser retomadas ou repetidas com controle de tentativa.

### Ações não idempotentes

Create, duplicate, rename, rotate e delete possuem efeitos distribuídos. Quando uma delas é interrompida em estado incerto, a API não deve reiniciar cegamente o processo.

O job é marcado com erro de revisão manual, preservando:

- etapa atual;
- progresso;
- stdout/stderr;
- histórico de rename, quando aplicável.

## Testes relevantes

- `tests/smoke/test_tenant_lifecycle.py`
- `tests/smoke/test_jobs_contract.py`
- `tests/smoke/test_restore_points_contract.py`
- `tests/smoke/test_project_access_and_deletion_contract.py`
- `tests/smoke/test_service_key_cache_contract.py`
- `tests/smoke/test_key_generation_contract.py`
- `tests/smoke/test_project_telemetry.py`

Os nomes dos testes podem evoluir; procure também por contratos de lifecycle em `tests/smoke/`.
