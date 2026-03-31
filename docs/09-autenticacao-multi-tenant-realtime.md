# Autenticação Multi-Tenant no Realtime

Este documento explica as modificações feitas no Realtime para suportar autenticação multi-tenant, permitindo que cada projeto tenha seu próprio `jwt_secret`.

---

## Contexto da Mudança

O Realtime foi modificado para suportar autenticação multi-tenant, permitindo que cada projeto tenha seu próprio `jwt_secret` ao invés de usar apenas um secret global compartilhado. Esta é uma modificação crítica que viabiliza o isolamento entre projetos.

### Problema Original

No Supabase original, o Realtime usa um único `JWT_SECRET` global para validar todos os tokens. Em um ambiente multi-tenant, isso significa que:

- Todos os projetos compartilham o mesmo secret
- Um token válido de um projeto poderia ser usado em outro projeto
- Não há isolamento real de entre projetos
- Comprometimento de um secret afeta todos os projetos

### Solução Implementada

A solução implementa um sistema de autenticação em cascata que **inverte o fluxo original**: ao invés de validar o token primeiro e depois identificar o tenant, o sistema agora identifica o tenant primeiro, busca seu JWT secret específico, e só então valida o token.

**Fluxo invertido:**
```
Original: Token → Validação (secret global) → Identificação do tenant
Novo:     Identificação do tenant → Busca secret do tenant → Validação do token
```

Isso permite que cada projeto tenha seu próprio JWT secret isolado, mantendo compatibilidade com o secret global como fallback para operações administrativas.

---

## Modificações no router.ex

**Arquivo:** `servidor/volumes/realtime/router.ex`

### 1. Extração do Token Bearer

```elixir
defp bearer_token(conn) do
  with ["Bearer " <> token] <- get_req_header(conn, "authorization") do
    {:ok, Regex.replace(~r/\s|\n/, URI.decode(token), "")}
  else
    _ -> {:error, :missing_token}
  end
end
```

**O que faz:**
- Extrai o token do header `Authorization`
- Remove espaços e quebras de linha
- Retorna `{:ok, token}` ou `{:error, :missing_token}`

### 2. Autorização com Contexto de Tenant

```elixir
defp authorize_request(conn, token, :api_jwt_secret, global_secret) do
  case tenant_auth_context(conn) do
    nil ->
      authorize_with_secret(token, global_secret)

    context ->
      case authorize_with_tenant_context(token, context) do
        :ok -> :ok
        {:error, _reason} -> authorize_with_secret(token, global_secret)
      end
  end
end
```

**Fluxo de autenticação:**

```
1. Tenta obter contexto do tenant (jwt_secret específico)
   ↓
2a. Se não encontrar contexto → usa secret global
   ↓
2b. Se encontrar contexto → tenta validar com secret do tenant
   ↓
3. Se validação com tenant falhar → fallback para secret global
```

### 3. Obtenção do Contexto de Autenticação

```elixir
defp tenant_auth_context(conn) do
  tenant_context_from_existing_tenant(conn) || tenant_context_from_payload(conn)
end
```

**Duas fontes de contexto:**

#### A) Tenant existente no banco

```elixir
defp tenant_context_from_existing_tenant(conn) do
  external_id = tenant_id_from_request(conn)

  with external_id when is_binary(external_id) <- external_id,
       %Tenant{jwt_secret: jwt_secret} <- Api.get_tenant_by_external_id(external_id, use_replica?: false) do
    %{
      tenant_id: external_id,
      secret: Crypto.decrypt!(jwt_secret),
      source: :tenant
    }
  else
    _ -> nil
  end
end
```

**Quando é usado:**
- Requisições para tenants já criados
- GET, PUT, DELETE em `/api/tenants/:tenant_id`
- Busca o `jwt_secret` criptografado no banco
- Descriptografa e retorna no contexto

#### B) Tenant no payload da requisição

```elixir
defp tenant_context_from_payload(conn) do
  tenant_params = Map.get(conn.body_params, "tenant", %{})
  external_id = tenant_id_from_request(conn)

  with jwt_secret when is_binary(jwt_secret) <- Map.get(tenant_params, "jwt_secret"),
       tenant_id when is_binary(tenant_id) <- external_id do
    %{
      tenant_id: tenant_id,
      secret: jwt_secret,
      source: :payload
    }
  else
    _ -> nil
  end
end
```

**Quando é usado:**
- POST `/api/tenants` (criação de novo tenant)
- O `jwt_secret` vem no body da requisição
- Permite validar o token antes do tenant existir no banco

### 4. Validação com Contexto de Tenant

```elixir
defp authorize_with_tenant_context(token, %{secret: secret, tenant_id: tenant_id, source: source}) do
  case authorize(token, secret, nil) do
    {:ok, claims} -> validate_tenant_claims(claims, tenant_id, source)
    {:error, reason} -> {:error, reason}
  end
end
```

**Valida o token e depois valida as claims:**

```elixir
# Para tokens do payload (criação)
defp validate_tenant_claims(claims, tenant_id, :payload) do
  case Map.get(claims, "iss") do
    ^tenant_id -> :ok
    _ -> {:error, :tenant_claim_mismatch}
  end
end

# Para tokens de tenants existentes
defp validate_tenant_claims(claims, tenant_id, :tenant) do
  case Map.get(claims, "iss") do
    nil -> :ok  # Permite tokens sem iss (compatibilidade)
    ^tenant_id -> :ok
    _ -> {:error, :tenant_claim_mismatch}
  end
end
```

**Diferença importante:**
- `:payload` - Exige que `iss` seja igual ao `tenant_id`
- `:tenant` - Permite `iss` ausente ou igual ao `tenant_id`

### 5. Extração do Tenant ID

```elixir
defp tenant_id_from_request(conn) do
  conn.path_params["tenant_id"] ||
    get_in(conn.body_params, ["tenant", "external_id"]) ||
    get_in(conn.params, ["tenant", "external_id"])
end
```

**Busca o tenant_id em ordem:**
1. Path params: `/api/tenants/:tenant_id`
2. Body params: `{"tenant": {"external_id": "..."}}`
3. Query params: `?tenant[external_id]=...`

---

## Modificações no tenant_controller_test.exs

**Arquivo:** `servidor/volumes/realtime/tenant_controller_test.exs`

### 1. Helper para Criar JWT de Tenant

```elixir
defp conn_with_tenant_jwt(conn, secret_or_tenant, tenant_id) do
  jwt =
    generate_jwt_token(secret_or_tenant, %{
      role: "authenticated",
      iss: tenant_id,
      exp: System.system_time(:second) + 100_000
    })

  put_req_header(conn, "authorization", "Bearer #{jwt}")
end
```

**O que faz:**
- Gera um JWT com o secret específico do tenant
- Inclui `iss` (issuer) igual ao `tenant_id`
- Permite testar autenticação com secret do tenant

### 2. Teste: Aceita JWT de Tenant Existente

```elixir
test "accepts tenant jwt for an existing tenant", %{conn: conn, tenant: tenant} do
  conn =
    conn
    |> conn_with_tenant_jwt(tenant, tenant.external_id)
    |> get(~p"/api/tenants/#{tenant.external_id}")

  assert json_response(conn, 200)["data"]["external_id"] == tenant.external_id
end
```

**Valida:**
- GET `/api/tenants/:tenant_id` aceita JWT assinado com secret do tenant
- Usa o struct `%Tenant{}` diretamente (que contém o `jwt_secret`)

### 3. Teste: Aceita JWT no Payload de Criação

```elixir
test "accepts tenant jwt matching the payload secret", %{conn: conn} do
  external_id = random_string()
  {:ok, port} = Containers.checkout()
  jwt_secret = random_string()

  attrs =
    default_tenant_attrs(port)
    |> Map.put("external_id", external_id)
    |> Map.put("jwt_secret", jwt_secret)

  conn =
    conn
    |> conn_with_tenant_jwt(jwt_secret, external_id)
    |> post(~p"/api/tenants", tenant: attrs)

  assert json_response(conn, 201)["data"]["external_id"] == external_id
end
```

**Valida:**
- POST `/api/tenants` aceita JWT assinado com o secret do payload
- Permite criar tenant usando seu próprio secret
- O `iss` do token deve corresponder ao `external_id`

---

## Fluxo Completo de Autenticação

### Cenário 1: Criação de Novo Tenant

```
1. Script generate_project.sh gera jwt_secret único
   JWT_SECRET_PROJETO=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n')
   # Gera 32 bytes (256 bits) em base64 URL-safe

2. Script gera tokens (anon e service_role) com esse secret
   ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"projeto_x\",...}" "$JWT_SECRET_PROJETO")

3. Script chama API do Realtime
   POST http://realtime:4000/api/tenants
   Authorization: Bearer <token_assinado_com_jwt_secret_projeto>
   Body: {
     "external_id": "projeto_x",
     "jwt_secret": "abc123...",
     ...
   }

4. Realtime recebe requisição
   - Extrai token do header
   - Chama tenant_auth_context()
   - Encontra jwt_secret no payload
   - Valida token com secret do payload
   - Verifica se iss == "projeto_x"
   - Autoriza requisição ✓

5. Tenant é criado no banco
   - jwt_secret é criptografado e salvo
```

### Cenário 2: Consulta de Tenant Existente

```
1. Cliente faz requisição
   GET http://realtime:4000/api/tenants/projeto_x
   Authorization: Bearer <token_assinado_com_jwt_secret_projeto>

2. Realtime recebe requisição
   - Extrai token do header
   - Chama tenant_auth_context()
   - Busca tenant "projeto_x" no banco
   - Descriptografa jwt_secret do banco
   - Valida token com secret do tenant
   - Verifica se iss == "projeto_x" ou iss ausente
   - Autoriza requisição ✓
```

### Cenário 3: Fallback para Secret Global

```
1. Cliente faz requisição com token global
   GET http://realtime:4000/api/tenants/projeto_x
   Authorization: Bearer <token_assinado_com_jwt_secret_global>

2. Realtime recebe requisição
   - Extrai token do header
   - Chama tenant_auth_context()
   - Busca tenant "projeto_x" no banco
   - Descriptografa jwt_secret do banco
   - Tenta validar token com secret do tenant → FALHA
   - Fallback: valida token com secret global → SUCESSO ✓
   - Autoriza requisição ✓
```

---

## Segurança e Isolamento

### Vantagens da Implementação

1. **Isolamento por projeto:**
   - Cada projeto tem seu próprio `jwt_secret`
   - Tokens de um projeto não funcionam em outro (a menos que use secret global)

2. **Compatibilidade retroativa:**
   - Secret global ainda funciona como fallback
   - Não quebra integrações existentes

3. **Validação de issuer:**
   - Campo `iss` do JWT deve corresponder ao `tenant_id`
   - Previne uso de tokens em projetos errados

4. **Criptografia no banco:**
   - `jwt_secret` é armazenado criptografado (Fernet)
   - Descriptografado apenas quando necessário

### Limitações

1. **Secret global ainda existe:**
   - Usado como fallback
   - Necessário para operações administrativas
   - Pode ser usado para acessar qualquer tenant

2. **Validação de iss opcional:**
   - Para tenants existentes (`:tenant`), `iss` pode ser `nil`
   - Mantém compatibilidade com tokens antigos

---

## Integração com o Sistema

### Como os Projetos Usam

1. **Criação de projeto:**
   - `generate_project.sh` gera `JWT_SECRET_PROJETO` único (base64 URL-safe, 256 bits)
   - Registra tenant no Realtime com esse secret
   - Gera `ANON_TOKEN` e `SERVICE_TOKEN` com esse secret

2. **Uso no projeto:**
   - Nginx do projeto valida tokens com `anon_key` ou `service_role`
   - Realtime valida tokens com `jwt_secret` do tenant
   - Ambos usam o mesmo secret (por projeto)

3. **Rotação de tokens:**
   - Script `rotate_key.sh projeto_x` regenera apenas os tokens
   - Usa o JWT_SECRET_PROJETO existente (não muda o secret)
   - Atualiza tokens no `.env` e nginx config do projeto
   - Reinicia apenas o nginx do projeto

**Por que não rotacionar o JWT_SECRET?**

Trocar o JWT_SECRET causa problemas sérios:
- Todos os tokens existentes ficam inválidos imediatamente
- Usuários autenticados são deslogados
- Aplicações integradas quebram
- Precisa sincronizar em múltiplos lugares (Realtime, sistema, projeto)

**Quando rotacionar tokens é útil:**
- Expiração programada (tokens com 8 anos de validade)
- Suspeita de vazamento de token específico
- Pode ter período de transição (aceitar token antigo e novo)

**Quando você REALMENTE precisaria trocar JWT_SECRET:**
- Comprometimento confirmado do secret (vazamento)
- Migração de sistema/formato
- Requisito de compliance obrigatório

Nesses casos raros, seria necessário:
1. Gerar novo JWT_SECRET
2. Atualizar `.env` do projeto
3. Atualizar banco do Realtime
4. Atualizar banco do sistema
5. Regenerar todos os tokens
6. Reiniciar todos os serviços do projeto
7. Notificar usuários/aplicações

### Diferença do JWT_SECRET Global

**JWT_SECRET global (ainda usado):**
- Configurado em `servidor/secrets/.env`
- Formato: base64 (64 bytes = 512 bits de entropia)
- Usado por serviços compartilhados (db, realtime, api-internal)
- Fallback para autenticação no Realtime
- Usado para operações administrativas

**JWT_SECRET_PROJETO (por projeto):**
- Gerado durante criação do projeto
- Formato: base64 URL-safe (32 bytes = 256 bits de entropia)
- Armazenado em `servidor/projects/projeto_x/.env`
- Usado para gerar tokens do projeto (anon, service_role)
- Registrado no Realtime para validação específica
- Isolamento de segurança entre projetos

---

## Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────┐
│                  Requisição com JWT Token                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  bearer_token(conn)  │
              │  Extrai token Bearer │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────────┐
              │ tenant_auth_context(conn)│
              │ Busca contexto do tenant │
              └──────────┬───────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌────────────────────┐         ┌─────────────────────┐
│ Contexto não       │         │ Contexto encontrado │
│ encontrado         │         │ (tenant ou payload) │
└────────┬───────────┘         └─────────┬───────────┘
         │                               │
         ▼                               ▼
┌────────────────────┐         ┌─────────────────────────┐
│ authorize_with_    │         │ authorize_with_tenant_  │
│ secret(global)     │         │ context(tenant_secret)  │
└────────┬───────────┘         └─────────┬───────────────┘
         │                               │
         │                     ┌─────────┴─────────┐
         │                     │                   │
         │                     ▼                   ▼
         │              ┌──────────┐        ┌──────────┐
         │              │ Sucesso  │        │  Falha   │
         │              └──────────┘        └─────┬────┘
         │                     │                  │
         │                     │                  ▼
         │                     │         ┌─────────────────┐
         │                     │         │ Fallback para   │
         │                     │         │ secret global   │
         │                     │         └────────┬────────┘
         │                     │                  │
         └─────────────────────┴──────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │ Autorizado (200) │
                    │ ou Negado (403)  │
                    └──────────────────┘
```

---

## Referências

- Ver `docs/00-arquitetura.md` para contexto geral do sistema
- Ver `servidor/volumes/realtime/router.ex` para implementação completa
- Ver `servidor/volumes/realtime/tenant_controller_test.exs` para testes
