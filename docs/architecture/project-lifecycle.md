# Lifecycle dos projetos

O lifecycle é orquestrado pela Projects API, mas a execução física (Docker e os scripts em `servidor/generateProject/`) acontece no [host-agent](host-agent.md): a API grava a intenção assinada no banco e aguarda o agent executar o comando fechado.

Operações longas são representadas por jobs persistentes. O endpoint HTTP normalmente cria o job e retorna seu identificador; a execução continua na fila serializada do projeto.

## Identificadores usados

Antes de acompanhar qualquer fluxo, diferencie:

- `project_uuid`: identidade canônica e imutável;
- `project_ref`: slug mutável usado em URL e recursos físicos;
- `_supabase_<project_ref>`: database;
- Realtime tenant: identificado pelo UUID;
- Supavisor tenant: identificado pelo project ref;
- slot principal do CDC: sufixado pelo project ref;
- slot temporário de broadcast: sufixado por hash derivado do UUID.

## Criação

Fluxo resumido:

1. a API valida usuário e nome;
2. gera o UUID canônico;
3. cria o job;
4. o script gera JWT secret, anon key, service role e config token;
5. cria `_supabase_<project_ref>` a partir de `_supabase_template`;
6. gera `.env`, compose, Dockerfile e configuração Nginx;
7. registra o tenant do Realtime com `external_id = project_uuid`;
8. registra o tenant do Supavisor com `external_id = project_ref`;
9. sobe os containers;
10. persiste o projeto e os segredos criptografados;
11. atualiza status e auditoria.

O JWT usa o UUID como issuer:

```json
{
  "role": "anon",
  "iss": "<project_uuid>"
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

Rename altera o project ref, mas preserva o UUID canônico.

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
- `tests/smoke/test_project_access_and_deletion_contract.py`
- `tests/smoke/test_service_key_cache_contract.py`
- `tests/smoke/test_key_generation_contract.py`
- `tests/smoke/test_project_telemetry.py`

Os nomes dos testes podem evoluir; procure também por contratos de lifecycle em `tests/smoke/`.
