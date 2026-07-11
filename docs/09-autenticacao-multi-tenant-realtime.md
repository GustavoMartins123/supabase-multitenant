# Autenticação multi-tenant no Realtime

O Realtime é compartilhado entre todos os projetos, mas cada projeto possui seu próprio JWT secret.

A implementação foi modificada para identificar o tenant antes de validar o JWT das rotas administrativas do Realtime.

## Identidade do tenant

O tenant do Realtime usa o UUID canônico do projeto:

```text
external_id = <project_uuid>
```

O project ref continua sendo usado no nome do database e no slot principal do CDC. O slot temporário de broadcast usa um hash derivado do UUID:

```text
database: _supabase_<project_ref>
slot principal: supabase_realtime_replication_slot_<project_ref>
slot de messages: supabase_realtime_messages_replication_slot_<hash_do_project_uuid>
```

Essa separação permite renomear o projeto sem trocar sua identidade canônica.

## Registro do tenant

Durante a criação, `generate_project.sh` recebe:

```text
<project_ref> <project_uuid>
```

Ele gera um JWT secret específico e tokens cujo issuer é o UUID:

```json
{
  "role": "anon",
  "iss": "<project_uuid>",
  "iat": 123,
  "exp": 456
}
```

O tenant é registrado com estrutura equivalente a:

```json
{
  "tenant": {
    "name": "<project_uuid>",
    "external_id": "<project_uuid>",
    "jwt_secret": "<jwt_secret_do_projeto>",
    "extensions": [
      {
        "type": "postgres_cdc_rls",
        "settings": {
          "db_name": "_supabase_<project_ref>",
          "slot_name": "supabase_realtime_replication_slot_<project_ref>"
        }
      }
    ]
  }
}
```

## Resolução do tenant no WebSocket

O Nginx do projeto encaminha o WebSocket para o Realtime global e injeta:

```text
Host: <project_uuid>.localhost
```

O Realtime usa esse host para resolver o tenant correto. O project ref não deve ser usado como identidade do tenant nesse fluxo.

## Autenticação das rotas administrativas

O patch principal fica em:

```text
servidor/volumes/realtime/router.ex
```

O fluxo atual é:

```text
Bearer token
  -> extrai tenant_id do path, body ou query
  -> procura tenant ou contexto do payload
  -> obtém o JWT secret específico
  -> valida assinatura
  -> valida o issuer
  -> autoriza ou retorna 403
```

### Contexto de tenant existente

Para operações sobre tenant já registrado:

1. extrai o `tenant_id`;
2. consulta `Api.get_tenant_by_external_id`;
3. descriptografa o `jwt_secret` armazenado pelo Realtime;
4. valida o token;
5. aceita `iss` igual ao UUID do tenant;
6. mantém compatibilidade com tokens antigos sem `iss` apenas nesse contexto.

### Contexto de criação

No `POST /api/tenants`, o tenant ainda não existe.

O router usa o `jwt_secret` presente no payload e exige:

```text
claims.iss == tenant.external_id
```

## Comportamento fail-closed

Quando uma requisição identifica um tenant, a autenticação não faz fallback para o secret global se o JWT do tenant falhar.

O código distingue três situações:

```text
sem tenant_id
  -> pode validar com o secret global da API

tenant resolvido
  -> valida somente com o secret do tenant

tenant_id informado, mas contexto ausente
  -> nega a requisição
```

Isso impede que um token global substitua silenciosamente a autenticação específica de um tenant já identificado.

O secret global continua existindo para rotas ou operações que realmente não carregam contexto de tenant, mas não funciona como bypass de tenant.

## Replication slots

Cada projeto possui pelo menos dois tipos de slot.

### Slot principal

Registrado na extensão CDC do tenant:

```text
supabase_realtime_replication_slot_<project_ref>
```

### Slot de `realtime.messages`

Criado pelo Realtime conforme a conexão de broadcast:

```text
supabase_realtime_messages_replication_slot_<hash_do_project_uuid>
```

A função modificada recebe o UUID do tenant, calcula SHA-256 e usa os primeiros 16 caracteres hexadecimais no nome do slot. Como o UUID não muda, o slot temporário permanece estável durante rename.

## Rename

Durante rename:

- o UUID do tenant permanece;
- o `external_id` do Realtime permanece;
- o database muda de `_supabase_<old_ref>` para `_supabase_<new_ref>`;
- a extensão CDC precisa apontar para o novo database;
- o slot principal precisa acompanhar o novo project ref;
- o slot temporário de broadcast continua derivado do mesmo UUID;
- o Nginx continua injetando o mesmo UUID no Host.

O fluxo completo está em [Lifecycle dos projetos](architecture/project-lifecycle.md).

## Rotação de keys

A rotação comum de anon key e service role reutiliza o JWT secret do projeto.

Ela:

- gera novos tokens;
- mantém o mesmo issuer UUID;
- atualiza Nginx e control plane;
- não troca o tenant do Realtime.

Trocar o JWT secret é uma operação diferente, pois invalida tokens e sessões existentes e exige sincronização coordenada.

## Segurança

Invariantes:

- cada projeto possui JWT secret próprio;
- o issuer dos tokens novos é o UUID do projeto;
- um token de um projeto não valida em outro;
- tenant identificado não aceita fallback global;
- o Nginx valida a API key antes do proxy WebSocket;
- o Realtime valida novamente o JWT com o secret do tenant;
- database e slot principal permanecem isolados pelo project ref;
- o slot temporário de broadcast permanece isolado pelo hash do UUID.

## Arquivos relacionados

- `servidor/volumes/realtime/router.ex`
- `servidor/volumes/realtime/replication_connection.ex`
- `servidor/volumes/realtime/tenant_controller_test.exs`
- `servidor/generateProject/generate_project.sh`
- `servidor/generateProject/duplicate_project.sh`
- `servidor/generateProject/rename_project.sh`
- `servidor/generateProject/nginxtemplate`
