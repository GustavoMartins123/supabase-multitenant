# Spec: múltiplas chaves de API opacas por projeto

Status: núcleo implementado; validação em stack Docker e fase ES256/JWKS pendentes  
Branch: `opaque-keys`  
Última revisão técnica: 2026-08-12

## 1. Objetivo

Substituir os JWTs públicos `anon` e `service_role` por chaves de API opacas,
permitir várias credenciais independentes por projeto e separar três ciclos:

1. a identidade do componente cliente, representada pela API key opaca;
2. a autorização interna `anon` ou `service_role`, representada por JWTs que
   ficam somente no servidor;
3. a assinatura e a expiração dos JWTs de sessão emitidos pelo Auth.

O lifetime temporal de cada slot é uma política opcional. Uma versão pode ter
`expires_at` definido ou permanecer válida sem prazo até uma transição explícita
de lifecycle.

Depois do corte de um projeto, seu gateway opera somente no modo opaco. JWTs
legados enviados como `apikey` não são aceitos como caminho alternativo.

## 2. Decisão arquitetural

O self-host oficial do Supabase suporta uma chave `sb_publishable_*` e uma
`sb_secret_*`. A plataforma gerenciada aceita várias chaves por projeto e
recomenda uma secret key por componente. Este projeto implementa a segunda
semântica no self-host por meio de um registro próprio, sem alterar os serviços
Supabase internos.

```text
cliente
  -> Nginx do projeto
       -> auth_request / key-authorizer
            -> PostgreSQL do control plane
            -> valida projeto, gateway, chave, papel, serviço e tempo
       -> traduz a chave opaca para JWT interno anon/service_role
       -> preserva o JWT de sessão do usuário quando houver
       -> serviço Supabase
```

O `key-authorizer` é data plane separado da Projects API. Ele usa uma role
PostgreSQL própria, sem superuser, sem `BYPASSRLS`, com `SELECT` somente nas
colunas necessárias e `UPDATE` somente em `last_used_at`.

## 3. Referências primárias

- [Supabase — Understanding API keys](https://supabase.com/docs/guides/getting-started/api-keys): separa a identidade da aplicação da autenticação do usuário e recomenda uma secret key por componente.
- [Supabase self-hosted — New API Keys and Asymmetric Authentication](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-keys): documenta a limitação de uma chave por papel, a tradução para JWT interno e o fluxo do Realtime.
- [Supabase self-hosted — Envoy API Gateway](https://supabase.com/docs/guides/self-hosting/self-hosted-envoy): referência atual das rotas, da tradução e do `x-api-key` do Realtime.
- [Supabase — User sessions](https://supabase.com/docs/guides/auth/sessions): access JWT curto, refresh token e política de expiração de sessão.
- [Supabase — JWT Signing Keys](https://supabase.com/docs/guides/auth/signing-keys): estados de chave, JWKS e rotação sem encerrar sessões cujos JWTs ainda são válidos.
- [Nginx `auth_request`](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html): autorização por subrequest; somente 2xx libera a requisição.
- [Nginx njs request reference](https://nginx.org/en/docs/njs/reference.html): documenta que `$arg_*` retorna o primeiro argumento, ignora caixa e não faz percent-decoding; o authorizer compensa essas ambiguidades usando também `$args` bruto.
- [Traefik access logs](https://doc.traefik.io/traefik/reference/install-configuration/observability/logs-and-accesslogs/): permite remover query parameters dos logs; necessário porque o WebSocket do Realtime leva `apikey` na URL.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): geração, privilégio mínimo, automação, auditoria, rotação, revogação e expiração.
- [AWS Secrets Manager rotation functions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): referência para preparar, instalar, testar e concluir uma rotação.
- [JWT Best Current Practices — RFC 8725](https://datatracker.ietf.org/doc/rfc8725): base para a futura migração de assinatura.
- [Python `secrets`](https://docs.python.org/3/library/secrets.html): CSPRNG e comparação constante.
- [GitHub — token formats](https://github.blog/engineering/behind-githubs-new-authentication-token-formats/): prefixo identificável, separador e checksum.
- [NIST SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): gestão de material criptográfico e cryptoperiods distintos.

## 4. Invariantes

### 4.1 Fail-closed e ausência de fallback

- O gateway opaco nunca compara uma credencial pública com
  `ANON_KEY_PROJETO` ou `SERVICE_ROLE_KEY_PROJETO`.
- Falha do authorizer, do banco, do token exclusivo do gateway ou da tradução
  bloqueia a requisição.
- Uma chave fora do formato canônico é rejeitada antes do lookup.
- Expiração temporal, quando configurada, é aplicada pelo relógio do PostgreSQL
  no caminho de autorização; não depende de o scheduler já ter atualizado o
  status persistido.
- Uma chave antiga nunca é prorrogada automaticamente.
- Depois de um `activate_at` confirmado, a chave antiga nunca volta a ser
  aceita, mesmo se a pendente expirar antes de o scheduler persistir o corte.
- Não há dupla aceitação entre JWT público legado e chave opaca após o corte.
- Rollback transacional de uma escrita é permitido. Após o início do corte do
  gateway, a recuperação canônica é concluir novamente o mesmo corte; o
  protocolo legado não é restaurado automaticamente.

### 4.2 Separação de responsabilidades

- `publishable` identifica um componente público e traduz para `anon`.
- `secret` identifica um componente confidencial e traduz para
  `service_role`.
- `allowed_services` restringe cada slot a um subconjunto explícito de
  `auth`, `rest`, `graphql`, `realtime`, `storage` e `functions`.
- RLS continua sendo a fronteira de dados para `publishable`.
- `secret` continua com o impacto de `service_role` e nunca deve ser embutida
  em frontend, aplicativo móvel ou artefato distribuído.
- JWT de sessão do usuário é preservado e validado pelo serviço de destino.
- JWTs internos não são retornados por `/config`, pela Projects API ou pela UI.

### 4.3 Segredo e auditoria

- Cada API key contém 32 bytes aleatórios gerados por CSPRNG.
- O registro persiste somente SHA-256 do token completo.
- O plaintext aparece apenas na resposta de criação/rotação ou na revelação
  cifrada da versão da chave.
- A revelação é apagada quando a versão a que pertence deixa de autenticar.
- Respostas com plaintext usam `Cache-Control: no-store`.
- Auditoria e notificações registram UUID, slot, ação e `token_hint`; nunca
  token, hash ou JWT interno.
- O Nginx não produz access log da rota WebSocket e o Traefik remove todos os
  query parameters de seus access logs, porque o Realtime transporta a chave
  na URL de upgrade.
- O token exclusivo de cada gateway é armazenado no `.env` do projeto e o
  control plane persiste apenas seu hash.

## 5. Modelo de domínio

### 5.1 Slot

Um slot representa um consumidor durável, como `web`, `android`,
`billing-worker` ou `backup`.

Tabela `project_api_key_slots`:

| Campo | Contrato |
| --- | --- |
| `id` | UUID canônico |
| `project_id` | FK com cascade |
| `name` | `^[a-z][a-z0-9_-]{2,39}$`, sem normalização silenciosa |
| `kind` | `publishable` ou `secret` |
| `allowed_services` | lista canônica, não vazia e sem duplicatas na API |
| `automatic_rotation_enabled` | herda a opção do projeto na criação |
| `rotation_interval_days` | `NULL` para não expirar ou entre 1 e 3650; padrão 90 |
| `status` | `active` ou `disabled` |
| campos de bloqueio | falha automática explícita que exige intervenção |
| `created_by` e timestamps | rastreabilidade |

Há no máximo uma versão persistida como `active` e uma como `pending` por
slot. Slots diferentes são identidades diferentes e podem coexistir.

O contrato canônico usa o campo já existente como política: `NULL` significa
`never` e um inteiro significa lifetime temporizado. Não há enum redundante.
`automatic_rotation_enabled = true` exige um intervalo; intervalo definido com
automação desligada é válido e significa “expira sem reposição automática”.
Ao mudar de temporizado para `never`, o cliente deve enviar explicitamente os
dois campos; a API não substitui silenciosamente `true` por `false`.

### 5.2 Versão de chave

Tabela `project_api_keys`:

| Campo | Contrato |
| --- | --- |
| `id` | UUID público de auditoria |
| `slot_id` | FK do consumidor |
| `secret_hash` | digest único globalmente |
| `token_hint` | identificação visual não autenticadora |
| `status` | `pending`, `active`, `revoked` ou `expired` |
| `activate_at` | instante programado do corte |
| `expires_at` | `NULL` para ausência de expiração temporal ou limite absoluto verificado no data plane |
| `activated_at`, `revoked_at` | timestamps de transição |
| `revealed_at`, `confirmed_at` | entrega e confirmação do consumidor |
| `last_used_at` | telemetria amostrada em cinco minutos |
| `replaces_key_id` | linhagem da rotação |
| `rotation_trigger` | `initial`, `manual` ou `automatic` |

`status` representa o estado persistido; `currently_accepted` é calculado com
estado do slot e da versão, confirmação, `activate_at`, `expires_at` e a
existência de uma nova versão efetiva. Uma linha ainda persistida como `active`
nunca é aceita depois de um `expires_at` definido. `expires_at = NULL` remove
somente esse evento temporal; revogação, disable e cutover continuam valendo.

### 5.3 Revelação

`project_api_key_reveals` contém uma linha por versão de chave, cifrada pelo DEK
do projeto com purpose/AAD que inclui o key ID. `claim` descriptografa sem
consumir: uma publishable é legível por qualquer membro do projeto e uma secret
exige admin do projeto mais step-up a cada leitura.

A linha vive exatamente enquanto a versão a que pertence. Rotação, revogação,
disable de slot e expiração apagam o material da versão que deixa de autenticar;
`claim` em uma chave sem material armazenado recebe `410 Gone`. `revealed_at`
registra a primeira entrega e continua sendo pré-requisito do corte da
migração.

### 5.4 Estado do projeto

`projects` possui:

- `api_keyset_version`: versão monotônica do conjunto;
- `api_gateway_token_hash`: autentica o Nginx daquele projeto;
- `opaque_keys_prepared_at`: registro inicial preparado;
- `opaque_gateway_cutover_started_at`: a entrada legada já começou a ser
  removida e abort não é mais permitido;
- `opaque_keys_activated_at`: as chaves iniciais foram ativadas;
- `opaque_gateway_ready_at`: o gateway opaco foi iniciado com sucesso.

Estados expostos:

```text
legacy -> prepared -> gateway_recovery_required -> active
```

`prepared` pode voltar transacionalmente para `legacy` somente antes do início
do corte. `gateway_recovery_required` só avança para `active` ao repetir e
concluir o corte.

## 6. Formato da chave

```text
sb_publishable_<43-char-base64url>_<8-char-checksum>
sb_secret_<43-char-base64url>_<8-char-checksum>
```

- 43 caracteres codificam 32 bytes sem padding;
- checksum é o prefixo Base64URL de
  `SHA-256(project_uuid || "|" || prefix || random)`;
- o checksum vincula o token ao projeto e detecta erro de cópia; não substitui
  o hash autenticador;
- tamanho, caixa, alfabeto, separadores e whitespace precisam ser canônicos;
- o formato é deliberadamente mais longo que os 22 caracteres aleatórios do
  self-host oficial.

## 7. Regras do gateway

### 7.1 Fontes da API key

- Header `apikey` para Auth, REST, GraphQL, Storage e Functions.
- Query `apikey` para Realtime WebSocket.
- Header e query simultâneos só são aceitos quando idênticos.
- Query deve usar exatamente `apikey=<valor>` em caixa baixa, uma única vez e
  sem percent-encoding. O authorizer compara `$arg_apikey` com `$args` bruto
  para neutralizar o comportamento permissivo do Nginx.

### 7.2 Authorization

Para rotas protegidas:

1. sem `Authorization`: injeta `Bearer <jwt-interno-do-papel>`;
2. `Bearer` contendo a mesma chave opaca: substitui pelo JWT interno;
3. outro `Bearer` canônico: preserva byte a byte como sessão do usuário;
4. outra chave opaca ou valor ambíguo: rejeita.

Storage aceita requisições sem API key para preservar URLs assinadas e SigV4.
Nesse caso o authorizer ainda valida projeto e gateway e preserva
`Authorization`. Storage e Functions preservam também esquemas customizados
não-Bearer quando uma API key válida está presente.

Functions continua exigindo API key conforme a política anterior deste
projeto. Isso é uma divergência consciente do gateway oficial atual, que deixa
Storage e Functions sem enforcement de API key.

Realtime remove a API key opaca da query encaminhada, injeta o JWT interno na
query e no header `x-api-key` e preserva os demais argumentos.

Rotas públicas existentes de verificação/callback/authorize do Auth continuam
sem API key. O restante de Auth, REST, GraphQL, Realtime e Functions exige uma
chave válida. O path exato `/rest/v1/` exige papel `service_role`.

## 8. APIs canônicas

Qualquer membro do projeto pode consultar estas rotas. Para role `member`, a
resposta é filtrada no servidor e contém somente slots/reveals `publishable`:

```text
GET    /api/projects/{project}/api-key-slots
GET    /api/projects/{project}/api-key-reveals
GET    /api/projects/{project}/opaque-api-keys/migration
```

Somente admin do projeto ou admin global pode alterar o lifecycle:

```text
POST   /api/projects/{project}/api-key-slots
PATCH  /api/projects/{project}/api-key-slots/{slot_id}
POST   /api/projects/{project}/api-key-slots/{slot_id}/rotation
POST   /api/projects/{project}/api-key-slots/{slot_id}/rotation-confirmation
POST   /api/projects/{project}/api-key-slots/{slot_id}/activation
DELETE /api/projects/{project}/api-key-slots/{slot_id}/rotation
DELETE /api/projects/{project}/api-key-slots/{slot_id}

POST   /api/projects/{project}/opaque-api-keys/migration/prepare
POST   /api/projects/{project}/opaque-api-keys/migration/cutover
DELETE /api/projects/{project}/opaque-api-keys/migration
```

O claim de uma `publishable` é permitido a qualquer membro. Claim, criação ou
rotação que devolva plaintext de `secret` exige simultaneamente admin do
projeto/admin global e step-up authentication. O navegador envia a senha da
conta atual somente a `POST /api/security/step-up`; o OpenResty fixa o username
da sessão, valida a senha no Authelia e descarta o novo cookie produzido pelo
`/auth/api/firstfactor`.

O grant retornado usa prefixo `su1`, domínio HMAC diferente de `X-User-Token`,
validade fixa de cinco minutos e binding por UUID do usuário, fingerprint do
cookie de login, ação, project ref, recurso e nonce. A Projects API revalida
todos os bindings e consome o nonce uma única vez no PostgreSQL, na transação da
operação sempre que ela já é transacional. Senha, grant e plaintext não entram
em provider, cache, banco, auditoria ou logs. Falha no Authelia, assinatura,
sessão, autorização, expiração ou consumo resulta em erro explícito.

Não existem aliases legados. Listagens retornam metadados; criação, rotação
imediata e claim são as únicas respostas que podem conter plaintext.

A política de lifetime usa uma única representação nullable:

```json
{
  "automatic_rotation_enabled": false,
  "rotation_interval_days": null
}
```

Esse estado significa “não expira”. Um inteiro de 1 a 3650 representa uma
política temporizada; `automatic_rotation_enabled` pode ser `true` ou `false`
nesse caso. `true` com intervalo `null` é rejeitado pela API e pelo banco.
Respostas serializam `expires_at: null` sem data sentinela. Até o limite de
3650 dias continua sendo um vencimento real, nunca um alias para `never`.

## 9. Lifecycle e expiração

Todas as decisões temporais do lifecycle usam `now()` transacional do
PostgreSQL, a mesma fonte usada pelo authorizer. O relógio do processo não
antecipa nem posterga cutover.

Há dois modos:

- `rotation_interval_days` inteiro: cada nova versão recebe `expires_at`; a
  versão deixa de ser aceita nesse instante;
- `rotation_interval_days = NULL`: cada nova versão recebe
  `expires_at = NULL` e continua válida até rotação, revogação, disable ou
  outro corte explícito.

Alterar a política atualiza atomicamente somente uma chave ativa ainda válida.
Uma mudança para intervalo conta o novo lifetime a partir do `now()` do banco.
Chave temporalmente vencida não pode ser ressuscitada por PATCH: exige hard
rotation. Mudança de lifetime com pending manual ou já efetiva é rejeitada; ao
mudar para `never` com opt-out simultâneo, uma preparação automática ainda não
efetiva é cancelada na mesma transação.

### 9.1 Criação e rotação imediata

Uma transação bloqueia projeto e slot, revoga a versão ativa, cria a nova
versão ativa com a política de lifetime atual, incrementa
`api_keyset_version` e grava auditoria. Não há sobreposição. Se a resposta com
o segredo for perdida, a recuperação é outra rotação explícita.

### 9.2 Rotação programada

1. cria uma versão `pending` com `activate_at` e a política de lifetime do slot;
2. revela o token;
3. o operador instala no consumidor e confirma o key ID;
4. a partir de `activate_at`, o authorizer aceita a pendente confirmada e deixa
   de aceitar a anterior, mesmo antes de o scheduler persistir a transição;
5. o scheduler converte a pendente para `active`, revoga a anterior e audita.

Sem confirmação, a pendente não é aceita. Em slot temporizado, a chave anterior
continua somente até seu `expires_at` original e nunca é prorrogada. Em slot
sem expiração, uma preparação manual não confirmada também não corta a chave
anterior; o operador precisa confirmar, cancelar ou executar hard rotation.
Uma pendente confirmada não pode ser cancelada depois de `activate_at`; o corte
lógico é monotônico e precisa convergir para a persistência de `active`.
Uma rotação imediata explícita pode substituí-la de forma atômica, inclusive se
ela já expirou, sem reabilitar a chave anterior.

### 9.3 Rotação automática

- A opção do projeto nasce `true` e cada slot herda esse valor.
- Somente slots temporizados podem habilitar rotação automática. Slots com
  `rotation_interval_days = NULL` não entram nas consultas de expiração, lead
  time ou preparação automática.
- O scheduler usa advisory lock e `FOR UPDATE SKIP LOCKED`.
- No lead time, prepara uma pendente com `activate_at` exatamente igual à
  expiração da ativa.
- Admin recebe notificação, faz claim, instala e confirma.
- No instante de expiração, somente a nova confirmada é aceita.
- Sem confirmação ou reposição, o slot falha fechado e fica bloqueado com
  erro auditável.
- Desabilitar a opção do projeto ou do slot cancela apenas preparações
  automáticas anteriores a `activate_at`; não altera chaves ativas, um corte já
  efetivo ou rotações manuais.
- Transformar explicitamente a política do slot para `NULL` é uma operação
  distinta do opt-out: além de desligar a automação, remove o `expires_at` da
  chave ativa ainda válida.

### 9.4 Relação com JWTs

Esta entrega resolve o acoplamento público: uma API key opaca não possui JWT
`exp` e não muda quando o JWT interno é regenerado. Os JWTs internos HS256
`anon`/`service_role` continuam com 90 dias e com o scheduler já existente,
mas são segredos operacionais do gateway.

JWTs de sessão dos usuários continuam expirando segundo a política do Auth.
Isso é desejado e não é resolvido por API keys. Enquanto a sessão estiver
válida, o refresh token emite um novo access JWT; uma API key não pode renovar
nem prolongar uma sessão.

Portanto, três TTLs não devem ser confundidos: lifetime da API key opaca,
janela de reveal do plaintext e lifetime de JWT/sessão. Alterar qualquer um
deles não modifica os outros dois.

A futura fase ES256/JWKS trata assinatura e rotação de signing keys, não a
validade de cada sessão. Seu protocolo terá estados explícitos `standby`,
`in_use`, `previously_used` e `revoked`: Auth passa a assinar com a nova chave,
enquanto a pública anterior permanece verificável somente até vencer o maior
TTL de access JWT já emitido, acrescido da margem de propagação de JWKS. Uma
revogação emergencial ignora essa janela e encerra deliberadamente os JWTs
afetados.

## 10. Provisionamento e migração

### 10.1 Projetos novos e duplicados

O gerador cria um token de gateway exclusivo, materializa o Nginx opaco e a
Projects API persiste dois slots ativos:

- `default-publishable`;
- `default-secret`.

As duas chaves seguem legíveis enquanto existirem. Create, duplicate, rename,
restore, rotação de JWT interno e recriação do Nginx preservam o contrato do
token de gateway. Leitores de `.env` exigem uma única entrada canônica.

### 10.2 Projetos existentes

1. `prepare` garante o token de gateway e cria os dois slots iniciais como
   `pending`, ainda rejeitados pelo gateway legado;
2. admin faz claim, instala as duas credenciais e confirma ambas;
3. `cutover` revalida tudo antes de qualquer indisponibilidade;
4. persiste `opaque_gateway_cutover_started_at`;
5. host-agent para o Nginx legado e materializa o template opaco;
6. ativa as duas chaves numa transação;
7. inicia o Nginx opaco;
8. persiste `opaque_gateway_ready_at`.

Qualquer falha após o passo 4 expõe `gateway_recovery_required`. Repetir
`cutover` é idempotente quanto ao estado já confirmado. Não há retorno
automático ao protocolo legado.

Antes do passo 4, `DELETE .../migration` remove o registro preparado numa
transação. Depois desse marco, abort é rejeitado.

## 11. Fases

### Fase 0 — especificação e contratos

- [x] mapear o acoplamento existente;
- [x] revisar todos os documentos e templates do projeto;
- [x] pesquisar referências primárias atuais;
- [x] definir formato, estados, APIs, migração e invariantes;
- [x] criar testes contratuais.

### Fase 1 — registro no control plane

- [x] schema, constraints e índices;
- [x] gerador/parser/hash/checksum;
- [x] CRUD de slots e versões;
- [x] revelação cifrada pelo tempo de vida da versão;
- [x] autorização administrativa e auditoria;
- [x] testes unitários do protocolo.

### Fase 2 — authorizer e gateway

- [x] serviço dedicado `key-authorizer`;
- [x] token exclusivo por gateway;
- [x] role PostgreSQL de privilégio mínimo;
- [x] lookup fail-closed por projeto, hash, tempo, papel e serviço;
- [x] tradução para Auth, REST, GraphQL, Realtime, Storage e Functions;
- [x] Realtime por query e `x-api-key`;
- [x] remoção das comparações públicas com JWTs internos;
- [x] testes estáticos e unitários de bypass/ambiguidade;
- [ ] testes HTTP negativos numa stack Docker real.

### Fase 3 — lifecycle e migração

- [x] create e duplicate nascem opacos;
- [x] rename, restore e rotação interna preservam o token de gateway;
- [x] preparação, confirmação, cutover e abort explícitos;
- [x] estado de recuperação sem reativar gateway legado;
- [x] bloqueio de recriação/rotação interna antes de o gateway estar pronto;
- [ ] probes reais de Auth, REST, GraphQL, Realtime, Storage e Functions.

### Fase 4 — assinatura assimétrica

- [ ] P-256 e JWKS por projeto;
- [ ] Auth assina ES256 com `kid` canônico;
- [ ] PostgREST, Realtime e Storage recebem JWKS pública;
- [ ] tokens internos ES256;
- [ ] estados `standby`, `in_use`, `previously_used` e `revoked`;
- [ ] retenção da chave anterior limitada ao maior TTL emitido mais a margem
  de propagação de JWKS;
- [ ] rotação normal e revogação emergencial separadas;
- [ ] testes de sessões durante o cryptoperiod.

Esta fase não tem implementação parcial nesta branch. HS256 continua interno e
com rotação própria até uma migração coordenada completa.

### Fase 5 — automação, UI e observabilidade

- [x] scheduler por slot;
- [x] pending, claim, confirmação e corte sem overlap;
- [x] padrão automático `true` com opt-out por projeto e slot;
- [x] UI de slots, reveal, confirmação, rotação, cancelamento e revogação;
- [x] auditoria, `last_used_at` e alertas sem segredo;
- [ ] métricas agregadas e dashboard de SLO.

### Fase 6 — validação operacional

- [x] smoke tests de protocolo e contratos;
- [x] compilação/importação Python;
- [x] análise estática Dart;
- [x] validação sintática Bash;
- [x] runbook de operação e incidente;
- [ ] build e testes numa stack Docker real;
- [ ] probes end-to-end e teste de indisponibilidade do banco/authorizer;
- [ ] changelog de release após a validação real.

## 12. Critérios de aceite

| ID | Critério | Estado |
| --- | --- | --- |
| `OK-SEC-001` | JWT legado como `apikey` recebe 403 | coberto estaticamente; E2E pendente |
| `OK-SEC-002` | chave de outro projeto recebe 403 | coberto por checksum/projeto e SQL |
| `OK-SEC-003` | serviço fora de `allowed_services` recebe 403 | coberto por authorizer |
| `OK-SEC-004` | pending não efetiva, revogada ou expirada recebe 403 | coberto por consulta temporal |
| `OK-SEC-005` | banco/authorizer indisponível produz 5xx e nunca libera | coberto por desenho; E2E pendente |
| `OK-SEC-006` | fontes de chave divergentes ou duplicadas recebem 403 | coberto pelo parser |
| `OK-SEC-007` | JWT de sessão é preservado | coberto por contrato; E2E pendente |
| `OK-SEC-008` | segredo não aparece em logs/listagens/auditoria | coberto por revisão estática |
| `OK-SEC-009` | claim é atômico e único | coberto por `DELETE ... RETURNING` |
| `OK-SEC-010` | há no máximo uma active e uma pending por slot | coberto por índices parciais |
| `OK-SEC-011` | token de gateway de outro projeto recebe 403 | coberto por hash vinculado ao projeto |
| `OK-SEC-012` | checksum inválido é rejeitado antes do lookup | coberto por teste unitário |
| `OK-SEC-013` | membro vê/gera claim somente de `publishable` | coberto por filtro server-side e teste de widget |
| `OK-SEC-014` | plaintext `secret` exige admin e step-up vinculado à ação/sessão | coberto por contrato Python/Lua/Flutter |
| `OK-SEC-015` | grant de step-up é curto, de uso único e não substitui `X-User-Token` | coberto por domínio HMAC, prefixo e ledger PostgreSQL |
| `OK-FUN-001` | projeto mantém vários slots independentes | implementado |
| `OK-FUN-002` | revogar um slot não afeta os outros | implementado |
| `OK-FUN-003` | supabase-js funciona antes/depois do login | E2E pendente |
| `OK-FUN-004` | Realtime conecta com chave opaca na query | E2E pendente |
| `OK-FUN-005` | rotação de JWT interno não muda API keys externas | implementado por separação |
| `OK-FUN-006` | lifecycle preserva a identidade do gateway | coberto por contratos; E2E pendente |
| `OK-FUN-007` | novos projetos herdam automação habilitada | implementado |
| `OK-FUN-008` | opt-out impede novas preparações sem alterar ativa | implementado |
| `OK-FUN-009` | chave ativa com `expires_at = NULL` é aceita até transição explícita | implementado |
| `OK-FUN-010` | scheduler ignora lifetime `never` e mantém slots temporizados | implementado |
| `OK-FUN-011` | mudança de política não ressuscita versão vencida ou revogada | implementado |

## 13. Decisões adiadas

- ampliar step-up para restore, revogação, alteração de policy e outras ações
  destrutivas que não revelam plaintext;
- decidir se uma futura janela elevada permitirá várias ações, em vez dos
  grants atuais estritamente vinculados e de uso único;
- escopo por tabela, schema, função ou linha;
- restrição por IP e bloqueio de secret key por User-Agent;
- cache distribuído/Redis no authorizer;
- integração automática com Vault, KMS ou secret managers externos;
- rate limit e quota individual por key ID;
- remoção do HS256 e migração ES256/JWKS;
- substituição do Nginx por Envoy.

Esses itens não recebem implementação parcial nem caminho secundário nesta
mudança.
