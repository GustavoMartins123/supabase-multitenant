# Code Review — Projects API Python + host-agent (`servidor/`)

Issues geradas a partir de revisão manual do código (commit `62e0aa3`, jul/2026).
Ordenadas por severidade. Cada issue está pronta para colar no GitHub.

---

## Issue 1 — Verificação TLS desabilitada por padrão em 3 integrações internas

**Labels:** `security`, `hardening`, `config`
**Severidade:** média

### Descrição

Três integrações internas sobre HTTPS têm verificação TLS **desligada por
padrão**, apesar de o setup já provisionar uma CA própria:

1. `api-internal/app/runtime_config.py` — `STUDIO_CACHE_INVALIDATION_VERIFY_TLS`
   default `"false"` (invalidação de cache API → Nginx)
2. `api-internal/app/push_worker.py:19` — `PUSH_VERIFY_TLS` default `"false"`,
   usando `ssl._create_unverified_context()` (API privada do CPython)
3. `studio/nginx/lua/security/get_service_key.lua:49` — `ssl_verify = false`
   (busca de service key Nginx → API)

### Impacto

O tráfego é interno à rede Docker e autenticado por HMAC/shared token, o que
mitiga. Mas um container comprometido na mesma rede poderia interceptar a
service role de transporte ou forjar respostas de invalidação. O projeto já
demonstra o padrão correto no proxy do Authelia (`proxy_ssl_verify on` +
`proxy_ssl_trusted_certificate`).

### Correção sugerida

Inverter o default para verificar usando a CA interna (`/config/ssl/ca.pem`),
mantendo a env var como escape hatch. Trocar `ssl._create_unverified_context()`
por `ssl.create_default_context()` com `check_hostname=False` apenas se
necessário.

---

## Issue 2 — Intenção do host-agent não tem validade (`issued_at` sem freshness)

**Labels:** `security`, `host-agent`, `hardening`
**Severidade:** baixa-média

### Descrição

`host_agent_protocol.py` assina `issued_at`, mas o agent
(`hostagent/agent.py::_revalidate`) verifica assinatura, argumentos e
autorização **sem checar a idade da intenção**. Uma linha assinada permanece
válida indefinidamente.

### Impacto

Para replay é preciso acesso de escrita ao banco (reverter `status` para
`queued`) — cenário que o HMAC já pressupõe como adversário. A reavaliação de
autorização contra o estado atual do banco limita o dano, e comandos como
delete falham por `project_not_found` após execução. Ainda assim, um teto de
idade (ex.: 24h) elimina a classe inteira de replay de intenções antigas.

### Correção sugerida

Em `_revalidate`, rejeitar com `intent_expired` quando
`now - issued_at > MAX_INTENT_AGE_SECONDS` (novo item no protocolo compartilhado,
para a API já gravar ciente do limite).

---

## Issue 3 — Mensagens de exceção interna persistidas e exibidas ao usuário

**Labels:** `security`, `info-disclosure`
**Severidade:** baixa-média

### Descrição

Vários fluxos persistem `str(exc)` como mensagem de job/erro exibida na UI:

- `main.py:2860, 3025, 3034, 3129` — `str(exc)[:2000]`
- `main.py:3526, 4826, 4986, 5076` — `message=str(exc)`

### Impacto

Exceções de drivers (asyncpg, httpx) podem conter trechos de SQL, DSNs,
caminhos de arquivo e versões — úteis para reconhecimento. O conteúdo vai ao
banco e é devolvido pela API a usuários autenticados do projeto.

### Correção sugerida

Mapear exceções conhecidas para mensagens curadas e logar o detalhe bruto
apenas no servidor (ou sanitizar com o mesmo `sanitize_output` do protocolo
antes de persistir).

---

## Issue 4 — `push_worker` usa `replace` global para derivar nome de projeto

**Labels:** `bug`, `minor`
**Severidade:** baixa

### Descrição

`api-internal/app/push_worker.py` (em `poll_tenant`):

```python
project_name = db_name.replace("_supabase_", "")
```

A regex de nomes permite `_` em qualquer posição, então um projeto chamado
`x_supabase_y` gera o database `_supabase_x_supabase_y` e o `replace` remove
**todas** as ocorrências → `project_name` vira `xy`.

### Impacto

Nome do projeto errado no payload de push para tenants com `_supabase_` no
nome. Não afeta entrega (o token FCM já foi resolvido), mas quebra
roteamento/logging do lado da API de push.

### Correção sugerida

`db_name.removeprefix("_supabase_")`.

---

## Issue 5 — `PUSH_API_URL` com placeholder `<SEU_IP>` como default

**Labels:** `bug`, `config`, `good first issue`
**Severidade:** baixa

### Descrição

`api-internal/app/push_worker.py:15`:

```python
API_URL = os.getenv("PUSH_API_URL", "https://<SEU_IP>:4000/api/internal/push")
```

Se a env não for definida, o worker falha em runtime com erro de DNS opaco —
diferente do padrão do próprio projeto, que faz fail-fast em config ausente
(`runtime_config.py` levanta `RuntimeError` para toda chave faltante).

### Correção sugerida

Sem default: `raise RuntimeError("Missing PUSH_API_URL")` na importação,
consistente com `INTERNAL_HMAC_SECRET` logo abaixo.

---

## Issue 6 — HMAC interno assina só o path, não a query string

**Labels:** `security`, `latent-risk`
**Severidade:** baixa (latente)

### Descrição

`api-internal/app/internal_hmac.py:21`:

```python
path = urlparse(url).path or "/"
```

A string canônica `push-v1` cobre método + path + timestamp + nonce + hash do
body, mas **não a query string**. O verificador Lua
(`check_push_worker.lua`) usa `ngx.var.uri`, que também exclui args — os dois
lados concordam, mas qualquer endpoint futuro que passe parâmetros via query
os deixará fora da assinatura (tampering de query não detectado).

### Correção sugerida

Documentar a limitação no contrato ou incluir `ngx.var.request_uri` /
`urlunsplit` normalizado na próxima versão do esquema (`push-v2`).

---

## Issue 7 — API sem endpoint de health (middleware exige token em tudo)

**Labels:** `ops`, `good first issue`
**Severidade:** baixa

### Descrição

O middleware `validate_shared_token` (`main.py:516`) cobre **todas** as rotas
e não existe `/health` ou `/livez`. Não há healthcheck configurável para
Docker/orquestrador sem distribuir o shared token para o probe.

### Correção sugerida

Exemptar `/healthz` (sem dados, só `{"ok": true}`) do middleware — padrão
comum e sem exposição de superfície relevante.

---

## Issue 8 — `main.py` monolítico (6.1k linhas, 47 rotas)

**Labels:** `maintainability`, `refactor`
**Severidade:** baixa (dívida técnica)

### Descrição

`api-internal/app/main.py` concentra middleware, helpers de autorização,
telemetria, colaboração (notas/hints/threads/tags/notificações), lifecycle e
rotas internas. O projeto já tem módulos bem recortados
(`project_secrets.py`, `host_agent_protocol.py`, `project_telemetry.py`) — o
main é a exceção.

### Correção sugerida

Extrair routers por domínio (`routers/collaboration.py`,
`routers/lifecycle.py`, `routers/internal.py`) com `APIRouter`, mantendo
helpers de auth em `dependencies.py`.

---

## Notas positivas (registradas na revisão)

- `security_tokens.py`: `hmac.compare_digest`, assinatura verificada **antes**
  de decodificar payload, janela de skew, UUID estrito
- `project_secrets.py`: envelope encryption exemplar — AES-256-GCM com AAD
  `projeto+coluna`, DEK por projeto, MultiFernet para rotação da master key,
  versionamento de formato
- `host_agent_protocol.py`: contrato byte-idêntico nos dois lados **enforced
  por smoke test**, conjunto fechado de comandos, matriz de autorização como
  função pura testável, sanitização de stdout (JWT/URIs/Bearer/KEY=valor)
- Agent: sem porta exposta, LISTEN/NOTIFY + poll, lease `FOR UPDATE SKIP
  LOCKED`, subprocess sempre argv (nunca `shell=True`), confinamento de path
  com rejeição de symlink, `assert` de handlers ↔ protocolo no startup
- Middleware global de shared token com `compare_digest`; Nginx remove
  `X-Internal-Service` do cliente no catch-all (`proxy_set_header ... ""`),
  fechando o acesso externo às rotas `internal/`
- Autorização sempre contra o banco (nunca headers/claims); auditoria em
  praticamente todas as mutações e leituras sensíveis
- SQL 100% parametrizado; os únicos SQLs dinâmicos usam identificadores
  escapados ou colunas de whitelist fixa
- `runtime_config.py`: fail-fast na importação, exige chaves distintas entre
  si (comparadas com `compare_digest`), validação anti-SSRF de
  `PG_META_INTERNAL_URL` (allowed hosts, sem userinfo/path)
- Telemetria sem SSRF (DSN derivado de config), período validado, leitura
  auditada; retry de jobs restrito a dono + failed + idempotente + retry
  único ativo
- `urllib` bloqueante corretamente isolado via `asyncio.to_thread`;
  polling de notificações com `FOR UPDATE SKIP LOCKED`
