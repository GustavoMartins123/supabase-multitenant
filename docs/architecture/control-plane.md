# Control plane

O control plane administra projetos e usuários. Ele não atende diretamente as APIs públicas de Auth, REST ou Storage das aplicações.

Os componentes principais são:

- Flutter selector;
- OpenResty/Lua;
- Projects API em FastAPI;
- `key-authorizer` de data plane com privilégio mínimo;
- database `postgres`;
- host-agent no servidor, que executa os scripts de lifecycle e o Docker (ver [host-agent](host-agent.md));
- integrações internas com Realtime, Supavisor, Storage global, Postgres-Meta e Studio.

## Responsabilidades

### Identidade

`last_login_at` muda somente quando o token HMAC carrega um fingerprint de uma nova sessão Authelia. O fingerprint é derivado por SHA-256 e o cookie nunca sai do gateway. Requisições normais atualizam `last_seen_at` com amostragem de cinco minutos.

O Authelia autentica o usuário, mas a autorização interna usa um UUID estável salvo na tabela `users`.

O OpenResty resolve e sincroniza a identidade, depois envia para a API:

```text
X-User-Token: v1.<payload>.<assinatura>
```

O token é assinado com `NGINX_HMAC_SECRET` e possui validade curta. A API extrai o UUID, valida a assinatura e consulta o usuário no banco.

Email, username, display name e grupos são atributos sincronizados. Eles não substituem o UUID canônico.

### Step-up authentication

Autorização responde se o ator pode executar uma operação; step-up confirma que o mesmo ator ainda controla a sessão no instante sensível. Nesta etapa ele é obrigatório para exclusão integral de projeto e para toda resposta que exponha plaintext de `sb_secret_*`.

O Flutter envia a senha pessoal somente ao endpoint do OpenResty. O gateway obtém o username do `auth_request`, e não do JSON do cliente, valida a senha no `/auth/api/firstfactor` interno do Authelia e não encaminha o `Set-Cookie` dessa subrequisição. Depois emite um grant `su1` HMAC de cinco minutos, vinculado ao UUID, fingerprint do cookie atual, ação, project ref, recurso e nonce.

A Projects API não confunde esse grant com `X-User-Token`: prefixo e chave derivada possuem domínio próprio. Ela revalida autorização no PostgreSQL e insere o nonce em `studio_step_up_grant_consumptions` com `ON CONFLICT DO NOTHING`. Assim cada grant é aceito uma vez. Indisponibilidade do Authelia, binding ausente, token expirado/repetido ou mudança de papel bloqueia a ação. Senha, grant completo e plaintext não são persistidos nem auditados.

### Autorização

A autorização considera:

- administrador global;
- owner do projeto;
- membro com role `admin`;
- membro com role `member`;
- regras específicas da operação.

A API não confia apenas nos grupos enviados pelo gateway. Ela consulta o estado persistido e valida ownership ou membership antes de acessar segredos, settings, telemetria ou metadata.

## Schema central

O database `postgres` guarda o estado do control plane.

### Identidade e acesso

Tabelas principais:

- `users`;
- `user_groups`;
- `user_group_audit`;
- `projects`;
- `project_members`;
- `project_members_audit`;
- `studio_step_up_grant_consumptions` (ledger sem senha ou bearer).

A tabela `projects` possui o UUID canônico (`id`), o vínculo persistido com o tenant externo (`tenant_uuid`), project ref, display name, versão das chaves e segredos criptografados. Em projetos novos, `tenant_uuid` recebe exatamente o valor de `id`; a coluna separada mantém compatibilidade auditável com projetos legados.

### Chaves de API opacas

O registro público não usa as colunas escalares de JWT como credenciais de cliente:

- `project_api_key_slots` representa cada consumidor e sua política;
- `project_api_keys` mantém versões, digest, expiração opcional e linhagem;
- `project_api_key_reveals` guarda temporariamente o plaintext cifrado;
- `projects.api_keyset_version` versiona cada mutação;
- os timestamps `opaque_*` representam preparação, corte, ativação e readiness.

O `key-authorizer` autentica cada Nginx por um token exclusivo cujo hash fica em `projects.api_gateway_token_hash`. Sua role possui apenas os `SELECT` de que o lookup precisa e `UPDATE(last_used_at)`. Falha de banco ou de subrequest bloqueia o acesso; a Projects API não participa do caminho quente.

As rotas ficam sob `/api/projects/{project_ref}/api-key-*` e `/opaque-api-keys/migration`. Membros recebem somente metadados/reveals `publishable`; mutações continuam limitadas a admin do projeto ou admin global. Plaintext de `secret` acrescenta step-up, e todas as operações revalidam o estado persistido, usam transações e nunca listam plaintext. Veja [o runbook](../12-chaves-api-opacas.md).

### Jobs

A tabela `jobs` persiste:

- ação;
- payload;
- status;
- progresso;
- etapa atual;
- total de etapas;
- timestamps;
- tails de stdout e stderr;
- código de erro;
- idempotência;
- retry;
- tentativa atual.

A intenção física correspondente fica em `host_agent_commands`, com assinatura, lease, heartbeat, resultado e ligação ao `job_id`. Essa separação permite que o job administrativo sobreviva a restart da API sem transformar restart em autorização para executar novamente um script distribuído.

### Colaboração no Studio

O control plane também mantém recursos administrativos que não pertencem aos databases dos tenants:

- `studio_project_tags`;
- `studio_project_tag_assignments`;
- `studio_project_notes`;
- `studio_project_hints`;
- `studio_project_thread_messages`;
- `studio_project_notifications`;
- `studio_audit_log`;
- `project_name_history`;
- `project_restore_points`.

Esses recursos usam o UUID do projeto como referência. Um rename não cria um novo projeto e não deve quebrar notas, tags, histórico ou auditoria.

## Jobs e fila por projeto

A Projects API serializa operações de lifecycle por projeto. Isso evita executar, por exemplo, rename e delete simultaneamente para o mesmo tenant.

Estados principais:

```text
queued -> running -> done
                  -> failed
                  -> cancelled
```

A API registra progresso e etapa atual durante operações longas.

### Recovery no startup

Ao iniciar, a API procura jobs em `queued` ou `running` e separa duas situações:

- se já existe uma intenção `host_agent_commands` correspondente, o recovery religa o job à **mesma intenção**, acompanha o comando ainda ativo ou reutiliza o resultado persistido; não dispara uma segunda execução;
- ações idempotentes conhecidas podem ser retomadas ou repetidas de forma controlada quando não há comando físico em andamento;
- operações distribuídas não idempotentes com resultado realmente incerto não são reexecutadas cegamente; o estado é preservado para rollback/reconciliação específica ou revisão manual;
- rename mantém histórico separado em `project_name_history`, e backup/restore preservam seus registros próprios.

O recovery não deve presumir que repetir qualquer script é seguro.

## Segredos

### Persistência

`anon_key`, `service_role` e `config_token` são armazenados com envelope encryption.

Cada projeto possui um DEK. O DEK é envelopado pela `PROJECT_SECRETS_MASTER_KEY`. Os segredos usam AES-256-GCM com AAD contendo o projeto e a finalidade do valor.

### Transporte da service role

O OpenResty precisa da `service_role` para reproduzir operações administrativas do Supabase Studio.

A API:

1. valida usuário e acesso ao projeto;
2. descriptografa o segredo persistido;
3. cifra o valor para transporte com `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`;
4. retorna somente para a rota interna autorizada.

O Nginx descriptografa, guarda no cache compartilhado e injeta no upstream. O navegador não recebe a chave.

### Cache versionado

A tabela `projects` mantém `project_key_version`.

Depois de uma rotação:

1. a API persiste as novas chaves e incrementa a versão;
2. chama o endpoint interno de invalidação no Studio;
3. o OpenResty remove a entrada anterior e publica a versão mínima;
4. os workers descartam chaves abaixo dessa versão;
5. toda utilização confirma a versão canônica na Projects API.

Falha na consulta de versão bloqueia a requisição. O OpenResty não usa uma service key em cache quando não consegue provar que ela corresponde à versão persistida.

### Agendadores de chaves

A Projects API mantém dois ciclos independentes. `key_expires_at` agenda a regeneração dos JWTs internos anon/service role pelo fluxo durável `rotate_key`. O registro opaco agenda cada slot por `project_api_keys.expires_at` quando esse campo possui timestamp e prepara uma versão `pending` que precisa de claim e confirmação. `expires_at = NULL` representa um slot sem expiração temporal e fica fora das consultas de lead time e vencimento.

Os dois scanners usam advisory lock do PostgreSQL e locks de linha para eleição de líder e distribuição segura entre réplicas. O scheduler opaco só processa projetos cujo gateway possui `opaque_gateway_ready_at`. Pending manual com cutover explícito continua convergindo mesmo quando a nova versão não expira.

Falhas automáticas bloqueiam novas tentativas daquele projeto até intervenção explícita. Habilitar novamente limpa o bloqueio e solicita uma nova reconciliação; desabilitar impede que o host-agent autorize o ator de sistema.

O comportamento canônico do cache interno está documentado em [OpenResty/Lua](openresty-lua.md). O lifecycle externo está no [runbook de chaves opacas](../12-chaves-api-opacas.md).

## Settings de projeto

A API permite alterar apenas uma whitelist de variáveis conhecidas.

Categorias atuais:

- signup e auto-confirmação do GoTrue;
- usuários anônimos e telefone;
- expiração de JWT e OTP;
- tamanho mínimo da senha;
- schemas e limites do PostgREST;
- pool do PostgREST;
- limite de upload;
- transformação de imagens.

Os valores locais são normalizados, validados e gravados de forma atômica no `.env` do projeto. Settings pertencentes ao Storage compartilhado são aplicados ao tenant canônico pela Admin API durante o comando fechado do host-agent, sem recriar o Storage ou o imgproxy globais.

A API calcula quais serviços foram afetados e enfileira somente a recriação ou reconciliação necessária.

## Telemetria administrativa

Owners, admins do projeto e administradores globais podem consultar telemetria de usuários do Auth.

A API conecta diretamente no database do projeto e consulta `auth.users` e `auth.sessions` para intervalos:

- 24 horas;
- 7 dias;
- 30 dias;
- período customizado limitado.

A leitura é auditada e não usa cache no navegador. Falhas de compatibilidade do schema do GoTrue retornam erro explícito sem alterar o projeto.

## Postgres-Meta

O OpenResty encaminha chamadas do Studio para a Projects API. A API:

1. valida o project ref;
2. valida identidade e membership;
3. confere a service role do projeto;
4. monta internamente a conexão de `_supabase_<project_ref>`;
5. cifra a conexão com `PG_META_CRYPTO_KEY`;
6. chama o `postgres-meta-global`.

O cliente não controla host, usuário, database ou header de conexão.

## Integrações internas

### Projects API para o host-agent

A Projects API não executa Docker nem shell. Ela grava intenções assinadas com `HOST_AGENT_HMAC_SECRET` na tabela `host_agent_commands` e o host-agent (serviço systemd no host) faz o lease, revalida assinatura, argumentos e autorização e executa o comando fechado. O contrato completo (comandos, lease/heartbeat/timeout, confinamento de paths e sanitização de saída) está em [host-agent](host-agent.md).

Criação, duplicação, rename, backup, restore, deleção, reconciliação de settings e outros efeitos físicos passam por essa fronteira. Os scripts executados pelo agent registram/reconciliam tenants do Realtime, Supavisor e Storage quando a operação exige.

O proxy Docker de lifecycle foi removido junto com o `DOCKER_HOST` da API. O estado dos containers exibido nos endpoints de status vem do snapshot `project_container_state`, mantido pelo agent.

Traefik usa exclusivamente o File Provider. Vector recebe logs pelo logging driver Fluent. Nenhum componente em container consulta a API Docker.

### OpenResty para Projects API

Usa `X-Shared-Token` e, nas rotas de usuário, `X-User-Token`.

### Projects API para OpenResty

Usado para:

- invalidar cache de service key;
- consultar métricas internas;
- migrar diretórios de snippets durante rename.

A rota valida `X-Shared-Token` e `X-Internal-Service: projects-api`.

### Push worker

O push worker usa uma assinatura HMAC backend-to-backend com timestamp, nonce e hash do body. Esse contrato é separado do token de usuário.

## Auditoria

Ações relevantes devem registrar:

- projeto;
- usuário executor;
- ação;
- tipo e id do alvo;
- valor anterior;
- valor novo;
- timestamp.

A auditoria é parte do control plane, não dos databases dos projetos.

## Invariantes

- UUID do projeto não muda durante rename.
- `tenant_uuid` não muda durante rename e identifica o namespace do Storage.
- Service role não é enviada ao navegador.
- Project ref é validado antes de formar paths ou nomes de database.
- Segredos persistidos não usam a chave de transporte do Studio.
- Header do Postgres-Meta usa uma chave separada dos segredos persistidos.
- Operações por projeto são serializadas.
- A Projects API não acessa Docker nem executa shell.
- Recovery automático é limitado a ações conhecidas como seguras ou à mesma intenção já persistida no host-agent.
- Autorização consulta estado persistido, não apenas headers textuais.

## Código relacionado

- `servidor/api-internal/app/main.py`
- `servidor/api-internal/app/jobs.py`
- `servidor/api-internal/app/host_agent.py`
- `servidor/api-internal/app/host_agent_protocol.py`
- `servidor/api-internal/app/database_schema.py`
- `servidor/api-internal/app/control_plane_service.py`
- `servidor/api-internal/app/project_secret_service.py`
- `servidor/api-internal/app/project_settings.py`
- `servidor/api-internal/app/opaque_key_service.py`
- `servidor/api-internal/app/routers/opaque_keys.py`
- `servidor/api-internal/app/service_key_cache.py`
- `servidor/api-internal/app/project_telemetry.py`
