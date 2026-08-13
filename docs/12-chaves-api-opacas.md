# Operação de chaves de API opacas

Este runbook cobre criação, migração, rotação, política opcional de expiração e
incidente das chaves `sb_publishable_*` e `sb_secret_*` gerenciadas pelo
projeto. O desenho completo e os critérios de aceite estão na
[especificação](specs/opaque-api-keys.md).

## Regras operacionais

- Use um slot por aplicação ou serviço consumidor.
- Nunca reutilize uma `sb_secret_*` em componentes diferentes.
- Não coloque secret keys em frontend, aplicativos móveis, repositórios, URLs
  ou logs.
- Uma chave só pode ser revelada uma vez. Copie-a diretamente para o secret
  manager do consumidor.
- Qualquer membro do projeto pode revelar uma `publishable`. Criar, alterar ou
  rotacionar slots continua exigindo admin do projeto ou admin global.
- Plaintext de `secret` exige admin e reautenticação com a senha da própria
  conta. Não existe senha global de chaves nem senha de servidor nesse fluxo.
- “Não expira” remove somente o vencimento temporal. Não impede rotação,
  revogação, disable, restrição de serviços ou qualquer outro corte explícito.
- Lifetime da credencial, TTL do reveal e lifetime de JWT/sessão são políticas
  independentes.
- Confirme a instalação somente depois de o valor correto estar no consumidor.
- Não distribua `ANON_KEY_PROJETO`, `SERVICE_ROLE_KEY_PROJETO` ou
  `API_GATEWAY_TOKEN_PROJETO`; são materiais internos.
- Falha de autorização não deve ser contornada. Corrija o estado canônico e
  repita a operação indicada.

## Pré-verificação

Antes de criar ou migrar chaves:

1. confirme que `projects-api`, `host-agent`, PostgreSQL e `key-authorizer`
   estão saudáveis;
2. confirme que o relógio do host e do PostgreSQL está sincronizado;
3. abra o projeto no Studio com uma conta owner/admin;
4. prepare o secret manager e o deploy de cada consumidor;
5. reserve uma janela para a migração de projetos legados, pois não existe
   período de dupla aceitação.

O healthcheck interno do authorizer é `/healthz`. Ele não deve ser publicado na
Internet.

## Atualização do schema

A Projects API aplica a migration
`20260812_opaque_api_key_optional_expiration.sql` quando detecta o schema
anterior. Ela torna `rotation_interval_days` e `project_api_keys.expires_at`
nullable, substitui as constraints e adapta o índice de vencimento. Não executa
`UPDATE` nas chaves: todas as linhas existentes preservam seu `expires_at`.

Depois do deploy, confirme que a migration terminou antes de permitir PATCH de
política. Falha de migration impede a inicialização canônica da Projects API;
não altere as constraints manualmente para contornar o erro.

O deploy também aplica `20260812_step_up_grants.sql`, que cria somente o ledger
de consumo dos grants de reautenticação. Ele registra ator, sessão hasheada,
ação, alvo e timestamps; nunca armazena senha, token bearer ou plaintext da API
key. Falha dessa migration impede a inicialização da Projects API.

## Projeto novo ou duplicado

Projetos novos e duplicados já nascem no modo `active`, com:

- `default-publishable`;
- `default-secret`.

Os slots iniciais preservam o padrão temporizado de 90 dias com automação
habilitada; isso evita mudar silenciosamente a política de instalações
existentes. O admin pode selecionar **Não expira** depois da criação. As
revelações iniciais expiram em 30 minutos em qualquer política.

1. No Studio, abra as configurações do projeto e a seção de API keys.
2. Faça claim de cada chave necessária. `publishable` está disponível a todos
   os membros; `secret` solicita a senha pessoal de um admin.
3. Armazene a publishable key na configuração do cliente público.
4. Armazene a secret key somente no secret manager de um backend confiável.
5. Crie slots adicionais para consumidores independentes.
6. Revogue um slot inicial que não será usado.

Se uma revelação expirar, não tente recuperar o plaintext. Faça uma rotação
imediata do slot e use a nova chave.

## Migração de projeto existente

### 1. Preparar

No Studio, escolha **Preparar migração opaca**. A operação:

- cria o token interno exclusivo do gateway;
- cria `default-publishable` e `default-secret` como `pending`;
- não muda o gateway que está atendendo o projeto.

O status passa de `legacy` para `prepared`. As chaves preparadas ainda são
rejeitadas e não servem como teste paralelo.

### 2. Revelar, instalar e confirmar

Para cada chave:

1. faça claim antes do prazo de sete dias; para `secret`, use uma conta admin e
   reautentique com a senha dessa mesma conta;
2. coloque o valor no secret manager/configuração do consumidor;
3. deixe o deploy pronto para usar o novo valor no instante do corte;
4. confirme no Studio o key ID instalado.

O corte só é liberado quando as duas chaves foram reveladas e confirmadas.
Confirmação é uma declaração operacional; ela não testa o consumidor.

### 3. Cortar

Acione **Concluir migração** dentro da janela reservada. A Projects API:

1. revalida os dois slots e as confirmações;
2. marca o início irreversível do corte;
3. para o Nginx legado;
4. materializa o gateway opaco;
5. ativa as duas chaves na mesma transação;
6. inicia o gateway e marca `active`.

Depois do corte, os JWTs públicos antigos recebem 403 como API key. Atualize os
consumidores no mesmo evento operacional.

### Abort antes do corte

Enquanto o status for `prepared`, **Abortar preparação** remove o registro
preparado e retorna o projeto ao estado `legacy`. Depois que
`cutover_started_at` existe, abort é recusado.

### Recuperação durante o corte

Se o status for `gateway_recovery_required`, corrija a causa indicada pelo job
e execute **Concluir/recuperar migração** novamente. A operação retoma o mesmo
estado e não reativa o protocolo legado.

Verificações mínimas após sucesso:

```bash
curl -i "https://HOST/PROJETO/auth/v1/settings" \
  -H "apikey: SB_PUBLISHABLE"

curl -i "https://HOST/PROJETO/rest/v1/" \
  -H "apikey: SB_SECRET"
```

Também confirme login, uma consulta REST sujeita a RLS, GraphQL, conexão
Realtime, operação de Storage e uma Function. Um JWT legado usado como
`apikey` deve receber 403.

## Criar slots adicionais

Escolha nomes ligados ao consumidor, por exemplo:

- `web-production` — publishable;
- `android-production` — publishable;
- `billing-worker` — secret;
- `backup-nightly` — secret.

Restrinja `allowed_services` ao necessário. A criação ativa a chave
imediatamente e retorna o valor uma única vez. Perder a resposta exige rotação
imediata; não há endpoint de recuperação do plaintext.

Escolha também a expiração do slot:

- **Não expira**: `rotation_interval_days = NULL`,
  `automatic_rotation_enabled = false` e `expires_at = NULL`;
- **90/180/365 dias ou personalizado**: a chave recebe `expires_at`; a rotação
  automática pode permanecer ligada ou ser desligada independentemente.

Desligar somente a rotação automática não remove uma expiração já definida.
Para mudar para `never`, envie também `automatic_rotation_enabled: false` na
mesma operação. A API rejeita automação ligada sem intervalo temporal e não
substitui esse valor silenciosamente.

## Alterar a política de expiração

A alteração usa o relógio transacional do PostgreSQL, incrementa
`api_keyset_version` e é auditada. Ela só atua sobre a versão `active` ainda
válida; versões `revoked`/`expired` nunca são reativadas.

### Temporizada para sem expiração

1. confirme que não existe rotação manual pendente;
2. no Studio, selecione **Expiração da chave → Não expira**;
3. confirme o aviso;
4. verifique `rotation_interval_days = NULL`,
   `automatic_rotation_enabled = false` e `expires_at = NULL` na listagem;
5. valide o consumidor e a auditoria.

Uma preparação automática ainda não efetiva é cancelada na mesma transação.
Pending manual, pending já efetiva ou chave ativa já vencida fazem a operação
falhar explicitamente. Para chave vencida, execute hard rotation.

### Sem expiração para temporizada

1. selecione 90, 180, 365 dias ou um intervalo entre 1 e 3650;
2. confirme a alteração; o novo `expires_at` é calculado a partir do `now()` do
   banco;
3. habilite rotação automática se desejar preparação no lead time;
4. valide a data exibida, o consumidor e a auditoria.

Se houver pending, conclua ou cancele esse lifecycle antes de mudar a política.
Alterar a política não revela novamente o plaintext.

## Rotação manual

### Corte imediato

Use para comprometimento ou troca emergencial. A versão anterior é revogada e
a nova entra em vigor na mesma transação, sem overlap.

1. execute **Rotacionar agora**;
2. capture o novo valor;
3. atualize o consumidor;
4. valide o serviço.

Existe indisponibilidade entre o corte e a atualização do consumidor. Essa é a
semântica intencional de hard rotation.

Em um slot sem expiração, o mesmo procedimento cria outra chave com
`expires_at = NULL`; a chave anterior continua sendo revogada atomicamente.
“Não expira” nunca autoriza reutilizar a versão comprometida.

### Corte programado

O agendamento é feito pela API interna
`POST /internal/projects/{project}/api-key-slots/{slot_id}/rotation`; o Studio
expÃµe somente o corte imediato nesta fase.

1. envie `activate_at` em ISO 8601 com timezone;
2. capture a chave `pending` retornada;
3. instale no consumidor;
4. confirme o key ID;
5. aguarde `activate_at` ou execute a ativação quando estiver vencida.

No instante programado, uma pendente confirmada passa a ser aceita e a antiga
deixa de ser aceita. O scheduler persiste a transição em seguida.

Uma preparação pode ser cancelada antes de ser efetivada. Uma pendente
confirmada que já atingiu `activate_at` não pode ser cancelada, pois isso faria
a chave anterior voltar. Cancelar revoga somente a pendente; não cria outra
chave.

Se uma pendente efetiva expirar durante indisponibilidade prolongada do
scheduler, execute **Rotacionar agora**. O corte emergencial revoga a pendente e
a chave anterior na mesma transação e entrega uma nova credencial.

## Rotação automática

A automação é habilitada por padrão no projeto e herdada por cada slot.

1. no lead time, o Studio recebe uma notificação de chave pendente;
2. faça claim e instale a chave;
3. confirme antes da expiração da versão ativa;
4. o corte ocorre exatamente na expiração antiga.

Sem confirmação, nenhuma nova chave é aceita e a antiga expira no horário
original. O slot entra em estado bloqueado com um erro explícito.

O opt-out pode ser feito no projeto inteiro ou no slot. Desabilitar cancela
somente preparações automáticas pendentes e não prolonga a chave ativa.
Slots configurados como **Não expira** não são candidatos do scheduler e não
geram pending automático. Cutovers manuais explicitamente agendados continuam
sendo processados.

## Incidentes

### Secret key exposta

1. identifique o slot pelo `token_hint` e pelos eventos de auditoria;
2. como admin do projeto ou admin global, execute rotação imediata e
   reautentique com sua senha pessoal antes de receber o novo plaintext;
3. distribua a nova chave pelo secret manager;
4. remova a chave exposta de código, logs e artefatos;
5. revise `last_used_at`, auditoria e acessos aos serviços permitidos;
6. corrija a causa do vazamento antes de criar outra credencial.

Não revele nem restaure a versão antiga.

Para uma chave sem expiração, não espere um evento temporal: faça hard
rotation imediatamente. Se o slot não precisar mais existir, use **Revogar
slot**. Ambas as operações continuam sendo autoritativas sobre
`expires_at = NULL`.

Se o Authelia ou a validação do grant estiver indisponível, não tente obter a
secret por outra rota. Preserve/revogue o slot conforme o incidente permitir e
restaure primeiro o caminho canônico de autenticação.

### Chave expirou sem reposição

O authorizer rejeita a chave mesmo que o status persistido ainda apareça como
`active`. `currently_accepted=false` é a informação efetiva.

- Se não houver pendente: faça rotação imediata.
- Se houver pendente válida: faça claim, instale, confirme e ative.
- Se a pendente expirou: cancele-a e faça rotação imediata.

### Authorizer ou banco indisponível

Auth, REST, GraphQL, Realtime e Functions protegidos falham com 5xx; Storage
continua passando pelo subrequest mesmo quando não recebeu API key. Restaure o
`key-authorizer` ou sua conexão de banco. Não remova `auth_request`, não injete
JWT público e não habilite uma rota de bypass.

### Migração interrompida

- `prepared`: conclua a distribuição ou aborte antes do corte.
- `gateway_recovery_required`: corrija host-agent/Docker/template e repita o
  cutover.
- `active`: não execute migração novamente; gerencie slots normalmente.

## Auditoria e dados seguros para diagnóstico

São seguros para tickets e dashboards internos:

- project ref/UUID;
- slot ID e nome;
- key ID;
- `token_hint`;
- `api_keyset_version`;
- status, timestamps e error code.

Nunca copie para tickets ou logs:

- chave opaca completa;
- hash da chave;
- JWT interno anon/service role;
- JWT secret;
- token exclusivo do gateway;
- ciphertext de revelação.

## Limite desta entrega

API keys opacas não mudam a expiração das sessões dos usuários. A assinatura
continua HS256 internamente nesta fase. A migração P-256/ES256/JWKS é uma fase
separada e precisa de corte coordenado entre Auth, PostgREST, Realtime e
Storage. Access JWTs de usuário continuam curtos e são renovados por refresh
token enquanto a sessão for válida; nenhuma API key prolonga a sessão.
