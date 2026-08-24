# Lifecycle dos projetos

O lifecycle é orquestrado pela Projects API, mas a execução física (Docker e os scripts em `servidor/generateProject/`) acontece no [host-agent](host-agent.md): a API grava a intenção assinada no banco e aguarda o agent executar o comando fechado.

As etapas de vetores embutidas em criar, duplicar, renomear e restaurar — buckets/índices S3, credenciais SigV4 por projeto e wrappers FDW — são especificadas em [Storage compartilhado, S3 e Storage Vectors](storage-vectors-lifecycle.md), a fonte canônica desse tópico. Este documento descreve quando essas etapas rodam, não como são implementadas.

Operações longas são representadas por jobs persistentes. O endpoint HTTP normalmente cria o job e retorna seu identificador; a execução continua na fila serializada do projeto.

## Identificadores usados

Antes de acompanhar qualquer fluxo, diferencie:

- `project_uuid`: `projects.id`, identidade canônica e imutável;
- `tenant_uuid`: vínculo persistido com Realtime/JWT/backups; equivale a `projects.id` nos projetos novos e pode preservar o UUID legado;
- `project_ref`: slug mutável usado em URL e recursos físicos;
- `_supabase_<project_ref>`: database;
- Realtime tenant: identificado pelo UUID;
- Storage tenant: identificado pelo `tenant_uuid` imutável;
- Supavisor tenant: identificado pelo project ref;
- slot principal do CDC: sufixado pelo project ref;
- slot temporário de broadcast: sufixado por hash derivado do UUID.

Antes de qualquer operação Storage mutável sobre um projeto existente, o lifecycle consulta `projects.tenant_uuid` no control plane e exige igualdade com o `PROJECT_UUID` canônico do ambiente. Divergência, linha ausente ou falha de consulta encerra a operação antes de tocar registry, database ou namespace.

## Criação

Fluxo resumido:

1. a API valida usuário e nome;
2. gera uma única vez `projects.id` e persiste o mesmo valor em `tenant_uuid`;
3. cria o job já com os dois identificadores duráveis;
4. o script gera JWT secret, JWTs internos anon/service role, config token e token exclusivo do gateway opaco;
5. cria `_supabase_<project_ref>` a partir de `_supabase_template`;
6. registra o tenant do Realtime com `external_id = tenant_uuid`;
7. registra o tenant do Supavisor com `external_id = project_ref`;
8. cria o namespace físico e registra o tenant no Storage global pela Admin API;
9. cria credenciais S3/SigV4 exclusivas do tenant;
10. gera `.env`, compose, Dockerfile e configuração Nginx sem Storage ou imgproxy locais;
11. sobe somente os serviços locais do projeto: Auth, PostgREST e Nginx; Postgres-Meta, Storage, imgproxy, Realtime, Supavisor e Edge Functions permanecem globais;
12. valida migrations, database, JWT, S3, Vectors e o roteamento do tenant real;
13. persiste os segredos criptografados no registro do projeto e conclui o job.

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
- tenant, credenciais e namespace do Storage;
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
- novo tenant e namespace Storage;
- novas credenciais S3/SigV4;
- novas API keys;
- novo config token.

A cópia não reutiliza segredos nem objetos por referência. `schema-only` cria namespace vazio. `with-data` captura a origem com seus serviços parados e o tenant Storage em manutenção fail-closed, copia os arquivos para o UUID novo, reidentifica as tabelas físicas de Vector e remove FDWs/Vault secrets copiados antes de criar credenciais novas.

## Rename

Rename altera o project ref, mas preserva tanto `projects.id` quanto `projects.tenant_uuid`.

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
- Storage tenant ID e namespace de objetos;
- credenciais S3/SigV4;
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

### Storage

O tenant é colocado em manutenção fail-closed antes do rename do database. O lifecycle troca `databasePoolUrl` por uma URL deliberadamente inalcançável e confirma pelo data plane que o tenant responde com erro; `null` não é usado, pois o Storage oficial passaria a usar `databaseUrl`. Depois do rename, o lifecycle atualiza `databaseUrl` e `databasePoolUrl` canônicos pela Admin API, executa as migrations oficiais e valida o mesmo tenant UUID pelo novo Nginx. Nenhum objeto é movido; apenas endpoints de wrappers Vector que contêm o project ref são reconciliados.

### Snippets

O Supabase Studio armazena snippets em diretórios que incluem usuário e slug do projeto.

Depois do rename principal, a API chama o endpoint interno do OpenResty para renomear esses diretórios.

A migração é best-effort:

- falha de snippets não invalida o projeto já renomeado;
- o job registra um aviso;
- os diretórios podem exigir correção manual ou retry específico.

## Chaves de API opacas

Projetos novos e duplicados nascem com slots `default-publishable` e `default-secret`. Projetos existentes usam preparação, claim, confirmação e corte explícitos; depois do corte, JWTs públicos legados deixam de ser aceitos.

Cada slot possui rotação, **expiração temporal opcional**, escopo de serviços e revogação próprios. `expires_at = NULL` significa que a chave permanece válida até revogação, rotação, desativação ou outro bloqueio de política; não significa chave irremovível. Para slots com timestamp, a automação pode preparar a próxima versão antes do vencimento. A automação pode ser desativada no projeto ou no slot.

O protocolo completo está em [Operação de chaves de API opacas](../12-chaves-api-opacas.md).

## Rotação dos JWTs internos

A rotação de infraestrutura gera novos JWTs internos anon e service role usando o JWT secret existente. Ela só pode recriar o Nginx de um projeto quando o gateway opaco está pronto.

Isso evita invalidar imediatamente todas as sessões de usuários finais.

Fluxo:

1. gera novos tokens;
2. atualiza arquivos do projeto;
3. atualiza configuração do Nginx;
4. persiste os segredos com envelope encryption;
5. incrementa `project_key_version`;
6. invalida o cache de service key do Studio;
7. persiste a nova expiração, conclui o job e grava a auditoria.

A invalidação do cache faz parte do sucesso da operação. Antes de usar qualquer entrada, o OpenResty precisa confirmar a versão canônica na Projects API. Se a consulta falhar, a requisição é bloqueada; uma chave em cache nunca substitui a validação de versão.

### Rotação automática

Todo projeto nasce com `automatic_key_rotation_enabled=true`. A Projects API calcula a agenda pelo claim `exp`, persiste `key_expires_at` e cria um job no mesmo runner da rotação manual sete dias antes do vencimento. O scanner:

- usa advisory lock do PostgreSQL para haver um único líder;
- bloqueia a linha com `FOR UPDATE SKIP LOCKED`;
- não cria um segundo job enquanto houver ação ativa no projeto;
- limita a concorrência global;
- registra ator de sistema, versão e expiração na auditoria.

Uma falha automática grava `automatic_key_rotation_blocked_at` e `automatic_key_rotation_last_error`. O scanner não repete a operação até um admin retomar explicitamente a automação ou concluir uma rotação manual. Não há loop silencioso nem uso da chave anterior como caminho secundário.

A opção pode ser desativada no Studio ou por `PUT /api/projects/{project_ref}/automatic-key-rotation` com `{"enabled": false}`. Os parâmetros globais são:

- `AUTOMATIC_KEY_ROTATION_LEAD_DAYS=7`;
- `AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS=300`;
- `AUTOMATIC_KEY_ROTATION_MAX_CONCURRENT=3`.

### Expiração

A API extrai metadata de expiração dos JWTs, agenda a rotação automática e avisa o Studio quando as chaves estão expiradas ou próximas do vencimento.

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
- tenant Storage e Nginx para limite de arquivo;
- tenant Storage para transformação de imagens, S3 Protocol e Vector Buckets.

A atualização de Storage envia `PATCH /tenants/<tenant_uuid>` e não reinicia o Storage ou imgproxy globais. A recriação do Nginx continua sendo um job idempotente quando sua configuração local muda.

## Pontos de restauração

Um ponto de restauração captura **dados, não identidade**: o dump do database `_supabase_<project_ref>` (sem o schema `realtime`, que é capturado à parte como no duplicate) e o tar somente de `volumes/storage/objects/<tenant_uuid>/`. O `manifest.json` formato 2 inclui UUID, Storage tenant ID, layout, ref na época, versão do Postgres e as tabelas da publication do Realtime.

Ficam fora do ponto: `.env`, JWT secret, anon/service keys, config token, tenants do Realtime/Supavisor e configuração de containers. Por isso um ponto continua restaurável depois de rotação de chaves e de rename — os arquivos vivem em `servidor/backups/<tenant_uuid>/<point_id>/`, chaveados pelo `tenant_uuid` persistido no control plane e espelhado em `PROJECT_UUID` no `.env` do projeto (imutável no rename). Um backup nunca percorre a raiz global nem inclui o namespace de outro tenant.

### Captura (fria)

O backup é frio por decisão de produto: o script para os serviços do projeto (o Postgres compartilhado continua de pé), encerra os pools do tenant no Supavisor e coloca somente o tenant Storage em manutenção fail-closed. O script confirma pelo data plane que o cache já deixou de aceitar operações, encerra as conexões Storage remanescentes, captura banco + namespace de forma atômica (`<id>.tmp` + rename), restaura as URLs canônicas do tenant e religa somente os containers que estavam rodando.

### Restauração

1. para os serviços do projeto, shutdown do tenant Realtime, terminate dos pools do Supavisor e põe o tenant Storage em manutenção fail-closed;
2. captura um **ponto automático de segurança** com o estado atual e emite `SAFETY_BACKUP_COMPLETE`;
3. dropa os replication slots, renomeia o database atual para `_supabase_<ref>_prerestore` (é o plano de rollback, não um DROP);
4. cria o database novo, restaura o dump e reaplica as correções conhecidas do duplicate: partições de `realtime.messages`, publications (com as tabelas do manifest), `TRUNCATE realtime.subscription`, `search_path`, override do `supabase_storage_admin`, grants e validação do contrato pgvector;
5. recria o slot principal e troca somente o namespace do UUID por staging transacional; o archive é rejeitado se tiver path absoluto, `..`, symlink ou tipo especial;
6. reconecta o tenant, executa migrations oficiais, religa os containers, valida JWT/S3/Vectors pelo tenant real e sincroniza os wrappers vetoriais;
7. só então remove `_supabase_<ref>_prerestore` e o staging do namespace.

Falhas disparam rollback compensatório com marker `ROLLBACK_COMPLETE`, como no rename. O ponto de segurança sobrevive à falha e vira um ponto normal na listagem.

A restauração reverte também os usuários e sessões do Auth (o schema `auth` faz parte do banco). Keys e URL do projeto não mudam.

### Control plane

A tabela `project_restore_points` guarda título (default: data/hora), descrição, status (`creating`, `ready`, `restoring`, `deleting`, `failed`), flag de ponto automático, tamanho, contadores de restauração e o job associado. Limite de 15 pontos ativos por projeto; a restauração exige uma vaga livre para o ponto automático. Todas as operações são auditadas em `studio_audit_log`. A listagem é acessível a qualquer membro; criar ponto exige admin do projeto, enquanto restaurar ou excluir ponto exige o dono ou admin global. `backup` e `restore` não são idempotentes: o recovery da API religa na intenção existente do host-agent em vez de reexecutar. O delete integral do projeto continua exclusivo de admin global, protegido também por step-up com a senha pessoal da conta Authelia atual, e remove `servidor/backups/<uuid>/` junto com os arquivos.

## Start, stop e restart

Essas operações:

- consultam o estado dos containers associado ao projeto;
- são serializadas na fila do projeto;
- atualizam status e auditoria;
- são marcadas como idempotentes e retryable.

O estado exibido pela API vem do snapshot `project_container_state` mantido pelo host-agent; a Projects API não consulta Docker diretamente.

## Deleção

A deleção precisa remover recursos sem permitir que Supavisor ou outros serviços recriem conexões no meio do processo.

Fluxo atual:

1. valida admin global e consome um grant de step-up de uso único, vinculado à sessão, ação e projeto;
2. cria job de delete;
3. remove os containers do projeto;
4. revoga credenciais, remove o tenant do registry Storage e apaga somente o namespace validado daquele UUID;
5. remove ou encerra os pools do tenant no Supavisor;
6. limpa tenant e extensões do Realtime e metadata do Supavisor;
7. drena conexões ativas do database e confirma que o pooler não reconecta;
8. remove replication slots e database;
9. remove registros do control plane;
10. remove diretório do projeto e backups do mesmo tenant UUID;
11. valida o resultado e registra auditoria.

### Proteção do database

Se o Supavisor continuar abrindo conexões mesmo após a remoção do tenant e drenagem, a deleção deve falhar antes do `DROP DATABASE`.

Preservar um database ainda referenciado é mais seguro do que concluir uma deleção parcial e inconsistente.

### Resultado parcial

Falhas de infraestrutura podem deixar:

- containers;
- tenant Storage ou namespace do tenant;
- tenants Realtime/Supavisor;
- slot;
- diretório;
- registros centrais.

O job deve expor etapa, mensagem, código de erro e tails de saída para permitir recuperação manual.

## Recovery e retry

O recovery possui duas camadas diferentes e elas não devem ser confundidas.

### API reiniciada enquanto o host-agent continua executando

A intenção de lifecycle já existe em `host_agent_commands`. O host-agent pode continuar executando mesmo com a Projects API fora do ar. Quando a API volta, o recovery religa o job à **mesma intenção persistida**, reutiliza o resultado terminal se ele já existir e não dispara um segundo script.

Esse comportamento é especialmente importante para operações distribuídas como create, duplicate, rename, rotate, backup, restore e delete.

### Ações idempotentes

Atualmente o sistema trata como idempotentes:

- start;
- stop;
- restart;
- recreate services.

Essas ações podem ser retomadas ou repetidas com controle de tentativa.

### Estado incerto ou falha terminal do host-agent

Create, duplicate, rename, rotate, backup, restore e delete possuem efeitos distribuídos. Se a intenção terminar com falha, lease expirado ou outro estado em que o resultado físico não possa ser provado, a API **não reexecuta cegamente** a operação.

O job preserva:

- etapa atual;
- progresso;
- stdout/stderr sanitizados;
- código de erro;
- histórico de rename ou ponto de restauração, quando aplicável.

A recuperação passa então pelo rollback/reconciliação específica do domínio ou por revisão manual. A persistência da intenção evita confundir um restart normal da API com autorização para repetir uma operação não idempotente.

## Testes relevantes

- `tests/smoke/test_tenant_lifecycle.py`
- `tests/smoke/test_host_agent_contract.py`
- `tests/smoke/test_jobs_contract.py`
- `tests/smoke/test_restore_points_contract.py`
- `tests/smoke/test_project_access_and_deletion_contract.py`
- `tests/smoke/test_service_key_cache_contract.py`
- `tests/smoke/test_key_generation_contract.py`
- `tests/smoke/test_opaque_api_keys.py`
- `tests/smoke/test_opaque_api_key_optional_expiration.py`
- `tests/smoke/test_project_telemetry.py`
- `tests/smoke/test_shared_storage_architecture_contract.py`
- `tests/smoke/test_shared_storage_tenant_integration.py` (opt-in, instalação descartável)
- `tests/smoke/test_storage_vector_lifecycle_integration.py`

Os nomes dos testes podem evoluir; procure também por contratos de lifecycle em `tests/smoke/`.
