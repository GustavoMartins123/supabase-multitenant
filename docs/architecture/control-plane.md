# Control plane

O control plane administra projetos e usuários. Ele não atende diretamente as APIs públicas de Auth, REST ou Storage das aplicações.

Os componentes principais são:

- Flutter selector;
- OpenResty/Lua;
- Projects API em FastAPI;
- database `postgres`;
- scripts de lifecycle;
- Docker Socket;
- integrações internas com Realtime, Supavisor, Postgres-Meta e Studio.

## Responsabilidades

### Identidade

O Authelia autentica o usuário, mas a autorização interna usa um UUID estável salvo na tabela `users`.

O OpenResty resolve e sincroniza a identidade, depois envia para a API:

```text
X-User-Token: v1.<payload>.<assinatura>
```

O token é assinado com `NGINX_HMAC_SECRET` e possui validade curta. A API extrai o UUID, valida a assinatura e consulta o usuário no banco.

Email, username, display name e grupos são atributos sincronizados. Eles não substituem o UUID canônico.

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
- `project_members_audit`.

A tabela `projects` possui o UUID canônico, project ref, display name, versão das chaves e segredos criptografados.

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

Jobs de ações idempotentes podem ser retomados ou repetidos de forma controlada. Operações não idempotentes interrompidas são marcadas para revisão manual.

### Colaboração no Studio

O control plane também mantém recursos administrativos que não pertencem aos databases dos tenants:

- `studio_project_tags`;
- `studio_project_tag_assignments`;
- `studio_project_notes`;
- `studio_project_hints`;
- `studio_project_thread_messages`;
- `studio_project_notifications`;
- `studio_audit_log`;
- `project_name_history`.

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

Ao iniciar, a API procura jobs em `queued` ou `running`.

- jobs enfileirados podem ser retomados;
- ações idempotentes conhecidas podem ser reexecutadas;
- operações não idempotentes são encerradas com erro de revisão manual;
- rename mantém histórico separado em `project_name_history`.

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
5. uma consulta periódica da versão funciona como fallback.

O comportamento canônico do cache está documentado em [OpenResty/Lua](openresty-lua.md).

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

Os valores são normalizados, validados e gravados de forma atômica no `.env` do projeto.

A API calcula quais serviços foram afetados e permite recriar apenas os containers necessários.

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
- Service role não é enviada ao navegador.
- Project ref é validado antes de formar paths ou nomes de database.
- Segredos persistidos não usam a chave de transporte do Studio.
- Header do Postgres-Meta usa uma chave separada dos segredos persistidos.
- Operações por projeto são serializadas.
- Recovery automático é limitado a ações conhecidas como seguras.
- Autorização consulta estado persistido, não apenas headers textuais.

## Código relacionado

- `servidor/api-internal/app/main.py`
- `servidor/api-internal/app/jobs.py`
- `servidor/api-internal/app/database_schema.py`
- `servidor/api-internal/app/control_plane_service.py`
- `servidor/api-internal/app/project_secret_service.py`
- `servidor/api-internal/app/project_settings.py`
- `servidor/api-internal/app/service_key_cache.py`
- `servidor/api-internal/app/project_telemetry.py`
