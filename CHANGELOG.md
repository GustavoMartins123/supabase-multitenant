## 2026-08-25 — Fix: perfil de recursos nunca chegava ao .env do projeto

- `apply_project_resource_limits` gravava so os valores **derivados** do perfil (`PROJECT_MEM_LIMIT`, `PROJECT_CPUS`, `PROJECT_PIDS_LIMIT`) e nunca o `PROJECT_RESOURCE_PROFILE` que os gerou;
- a API de settings le o perfil justamente desse arquivo (`SETTINGS_WHITELIST`), entao o seletor do Studio abria vazio com "Valor obrigatorio" em **todo** projeto — os limites nos containers estavam corretos, so a origem da escolha nao era persistida;
- o helper passa a gravar o perfil junto dos limites, removendo a chave antiga antes de reescrever (idempotente). Vale para criacao, duplicacao, rename e rotate, que compartilham o helper;
- `tools/migrate_project_resource_limits.py` tambem so escrevia o trio derivado e resolvia o perfil **sempre do .env raiz**, o que sobrescreveria um projeto `large` com o default global. Agora tem `profile_for()`, que prefere o perfil proprio do projeto e so cai no raiz quando ausente, e grava a chave do perfil;
- projetos existentes: `python3 tools/migrate_project_resource_limits.py` mostra o plano, `--apply` grava (preserva dono e modo 600);
- novos contratos: o perfil precisa ser persistido ao lado dos limites, e a migracao nao pode rebaixar o perfil proprio do projeto.

## 2026-08-25 — Studio: abas no dialogo de configuracoes e fix do seletor de perfil

- **layout quebrado:** no `Row` de cada configuracao, todos os campos tem largura limitada por `SizedBox` (28/120/180) menos o `select`. `DropdownButtonFormField` se dimensiona pelo item mais largo e consumia a linha inteira, deixando ~1 caractere para o `Expanded` do rotulo — "Perfil de Recursos" era renderizado uma letra por linha. O select agora fica em `SizedBox(width: 220)` com `isExpanded`, e ganhou a mesma `_fieldDecoration` e cores escuras dos demais campos;
- **abas por assunto:** o dialogo empilhava nove secoes num scroll unico. Agora sao quatro abas — Geral (status, URL, identidade), Chaves (chaves opacas, rotacao automatica, config token), Ambiente (configuracoes do `.env`) e Acesso (membros, telemetria de usuarios);
- cada aba rola sozinha e o rodape (Excluir/Transferir/Fechar) segue global. As secoes so montam quando a aba e aberta, entao as consultas de dados deixam de disparar todas de uma vez;
- o gating por papel foi preservado: config token e telemetria continuam restritos a admin, apenas realocados para as abas correspondentes.

## 2026-08-25 — install.sh avisa quando derruba um host-agent ativo

- a instalacao nao sobe o agent de proposito (banco e API precisam vir antes, e o `start.sh` orquestra), mas ela **para** quem estava rodando para migrar o ownership e nao dizia nada;
- o efeito pratico e uma reinstalacao aparentemente bem-sucedida seguida de `host_agent_offline` no proximo comando, sem pista da causa;
- quando o servico estava ativo, o final da instalacao agora imprime que ele foi parado e o comando exato para retomar. Contrato garante o aviso sem reintroduzir start automatico.

## 2026-08-24 — Fix: build do projeto bloqueado pelo sandbox e rollback rodando em dobro

- **buildx sem escrita:** `docker compose build` grava o estado do builder em `~/.docker/buildx`, e `ProtectHome=read-only` bloqueava: o build do nginx do projeto morria com `failed to update builder last activity time: ... read-only file system`, a 72% da criacao — depois de banco, tenants Realtime/Supavisor e Storage ja criados. O unit ganha `ReadWritePaths=-"__SERVICE_HOME__/.docker"`, resolvido pelo `install.sh` via `getent passwd`;
- **rollback duplo:** o script roda com `set -Eeuo pipefail`, e `-E` propaga o trap `ERR` para subshells. A falha dentro de `( docker compose up )` disparava `rollback_transaction` no subshell (que completava: `HOST_AGENT_ROLLBACK_COMPLETE=1`) e o `exit` so encerrava o subshell — o shell principal via o retorno nao-zero e rodava o rollback de novo, agora tentando dropar um banco ja removido (`database "_supabase_x" does not exist`) e terminando em `HOST_AGENT_ROLLBACK_FAILED=1`. Um projeto limpo com sucesso era reportado como residuo;
- `rollback_transaction` agora compara `$BASHPID` com `MAIN_SHELL_PID` e sai imediatamente quando roda num subshell, deixando o rollback real para o shell principal — onde as variaveis `CREATED_*` de fato vivem (as alteradas no subshell nem voltariam);
- `render_unit` passou a receber o home do servico como argumento em vez de consultar `getent` internamente: renderizador puro, testavel com usuario sintetico;
- novos contratos: `ReadWritePaths` do `~/.docker`, e o guard de subshell obrigatoriamente antes de qualquer remocao no rollback.

## 2026-08-24 — Fix: recuperacao travava em diretorio de projeto meio-criado

- `cleanup_stale_state` sempre rodava `docker compose down --env-file .env`. Uma criacao que falha antes de renderizar os arquivos deixa o diretorio so com `nginx/` e `pooler/`: o compose sai com 1 por falta do env-file, a recuperacao devolve `HOST_AGENT_ROLLBACK_FAILED=stale_compose` e o nome do projeto fica impossivel de reutilizar;
- o `compose down` passa a rodar so quando `.env` e `docker-compose.yml` existem — sem eles nao ha stack a derrubar, e a varredura por `label=com.docker.compose.project` logo abaixo ja cobre qualquer container que tenha subido;
- contrato novo em `StaleRecoveryContract`.

## 2026-08-24 — Fix: provisionamento do platform_reader quebrava a criacao de projeto

- `psql_exec_stdin` usava so `$1` e **descartava os argumentos seguintes**: o `-v reader_pwd=...` nunca chegava ao psql e o `:'reader_pwd'` ia sem substituicao para o Postgres (`syntax error at or near ":"`), derrubando toda criacao com "falha ao provisionar a role platform_reader";
- o helper agora repassa `"$@"`, e a senha migrou do argv para o stdin — argumentos de processo sao visiveis em `ps` para qualquer usuario local, e o helper ja canalizava o SQL por stdin;
- segundo defeito no mesmo passo: `auth.sessions` nasce nas migrations do GoTrue, que so rodam quando o container do projeto sobe. Um banco recem-criado do `_supabase_template` tem `auth.users` mas nao `auth.sessions`, e o `GRANT` rodava antes do `docker compose up` — falharia sempre em projeto novo;
- `provision_platform_reader` foi dividido: `provision_platform_reader_role` continua cedo (fail-fast na senha antes de trabalho caro) e `grant_platform_reader_on_tenant` roda depois dos containers, com `wait_for_auth_sessions` (poll com timeout, `PLATFORM_READER_WAIT_TIMEOUT`, default 60s). O grant segue restrito a `auth.users` e `auth.sessions` — sem `ALL TABLES IN SCHEMA auth` nem `ALTER DEFAULT PRIVILEGES`, que alcancariam `refresh_tokens`, `instances` e futuras tabelas do GoTrue;
- `duplicate`/`restore` partem de bancos ja migrados e seguem usando `provision_platform_reader`, onde o wait retorna de imediato;
- novos contratos: nenhum segredo no argv do psql, `psql_exec_stdin` obrigado a repassar argumentos, e o GRANT obrigado a rodar depois do `docker compose up`.

## 2026-08-24 — Fix: host-agent offline reportava residuo fisico inexistente

- quando nenhum worker esta ativo, o comando e cancelado ainda em `queued` — nenhum script roda no host. Mesmo assim a criacao caia no `except HostAgentError` generico e reportava "A limpeza fisica nao foi confirmada; uma nova tentativa fara a recuperacao", sugerindo residuo que nao existe;
- `HostAgentOffline` (ja importado em `main.py`, ate agora sem uso) passa a ter tratamento proprio antes do `HostAgentError`: mensagem diz que nada foi provisionado e que basta iniciar o servico, com `current_step="host_agent_offline"`;
- os demais fluxos (duplicate/delete/rotate/recreate) ja usavam mensagens neutras e ficaram como estao.

## 2026-08-24 — Fix: sandbox do systemd deixava o repositorio somente-leitura

- `ReadWritePaths=` recebe uma LISTA separada por espaco. O unit template usava `ReadWritePaths=-__SERVIDOR_DIR__` sem aspas: num deployment sob `~/Área de trabalho/...` o systemd parseou `-/home/gustavo/Área` duas vezes e descartou o resto, entao `ProtectHome=read-only` prevaleceu e o repositorio nunca ficou gravavel;
- efeito: toda criacao de projeto falhava em `cleanup_stale_state (12%)` com `mkdir: nao foi possivel criar o diretorio ".../.generate_transaction_NNN": Sistema de arquivos somente para leitura`. Diagnostico: `systemctl show supabase-host-agent -p ReadWritePaths` mostrava o caminho truncado;
- template passa a usar `ReadWritePaths=-"__SERVIDOR_DIR__"` / `-"__AGENT_DIR__"` (`escape_systemd_value` ja escapava `\`, `"` e `%`). `WorkingDirectory=` fica sem aspas de proposito: consome o resto da linha;
- `install.sh` ganha `assert_sandbox_paths_parsed`, que le `systemctl show -p ReadWritePaths` apos o `daemon-reload` e aborta se algum caminho nao sobreviveu ao parsing — a truncagem so apareceria no primeiro `mkdir` de um job real;
- novos contratos: todo placeholder de caminho do unit precisa estar entre aspas (exceto `WorkingDirectory=`), e o instalador precisa verificar o sandbox depois do reload;
- instalacoes afetadas: reinstale com `sudo bash servidor/host-agent/install.sh`.

## 2026-08-24 — Fix: criacao de projeto quebrava com NameError em `body`

- `_provision_and_store_keys` montava os args do host-agent com `body.resource_profile`, mas `body` so existe no endpoint: toda criacao morria com `Worker error: name 'body' is not defined` e caia no rollback;
- o worker passa a ler `projects.resource_profile` (coluna `NOT NULL` com `CHECK small|medium|large`), gravada pelo endpoint antes de enfileirar. Isso tambem cobre `_build_recovery_runner`, que reentra no worker so com job_id/projeto/dono e nao teria como repassar o perfil;
- mesma classe de bug encontrada e corrigida no host-agent: `handle_ensure_opaque_gateway_token` usava `ensure_inside` sem importar de `.security`, quebrando o comando de token opaco em runtime;
- duplicacao herdava o perfil errado: o `INSERT` da copia nao definia `resource_profile` (caia no default `medium`) e o worker nao enviava o valor ao agent — um projeto `large` virava `medium` em silencio. O `INSERT ... SELECT` agora copia o perfil do original na mesma transacao e o worker repassa o valor persistido;
- CI ganha varredura `ruff --select F821` (nomes indefinidos): `compileall` valida sintaxe e nao pega `NameError`, que so aparece em runtime no meio do job. Contrato em `test_ci_workflow_contract.py` impede o passo de sumir;
- `drop_supabase_replication_slots` migrou de `main.py` para `project_deletion.py`, junto das demais primitivas de exclusao fisica.

## 2026-08-24 — Fix: exclusao de projeto rodava SQL privilegiado como platform_app

- com a API migrada para `platform_app` (DML so nas tabelas do schema `public`), o fluxo de delete continuou usando o pool da aplicacao para operacoes que exigem administracao: `DELETE`/`SELECT` em `_realtime.*` e `_supavisor.*`, `pg_terminate_backend` em backends de outros papeis, `pg_drop_replication_slot` e `DROP DATABASE`;
- efeito: a exclusao morreria em "Limpando metadata global" (55%) com `permission denied for schema _realtime`, apos os containers, o tenant de Storage e os tenants globais ja terem sido removidos — projeto meio apagado e database orfao;
- novo `global_admin_connection()` em `project_deletion.py` abre a conexao dedicada de `META_ADMIN_DSN` (`platform_meta_admin`, membro de `supabase_admin`); os dois blocos privilegiados do delete — metadata global + drop, e a verificacao final — passam a usa-la, enquanto a limpeza do control plane continua no pool de `platform_app`;
- novo contrato `PrivilegedStatementRoutingContract`: fatia `main.py` por bloco de conexao e proibe marcadores privilegiados dentro de qualquer `async with pool.acquire()`, alem de exigir que `drain_database_connections`/`drop_database_force` recebam a conexao administrativa;
- instalacoes afetadas: recrie o container `projects-api`.

## 2026-08-24 — Fix: host_agent_rw sem leitura das tabelas de autorizacao

- o cutover para a identidade dedicada concedeu apenas as tabelas `host_agent_*` e `project_container_state`, mas o agent tambem le `projects`, `users`, `user_groups` e `project_members` para reautorizar cada comando por conta propria;
- efeito na instalacao limpa: `start.sh` parava em "Schema do host-agent indisponivel" — `information_schema.columns` esconde `projects.tenant_uuid` de quem nao tem privilegio, entao o probe de schema dava falso negativo mesmo com as migrations aplicadas; passando dele, todo comando falharia com permission denied;
- `ensure_host_agent_rw_role` passa a conceder `SELECT` por coluna exatamente nas colunas consultadas: `projects` (`id`, `name`, `owner_id`, `tenant_uuid`, `automatic_key_rotation_enabled`), `users` (`id`, `is_active`), `user_groups` (`user_id`, `group_name`), `project_members` (`project_id`, `user_id`, `role`) — nenhum segredo de projeto (`anon_key`, `service_role`, `config_token`, hashes de chave) e alcancavel, e a escrita continua restrita as tabelas do agent;
- `load_authorization_context` deixa de usar `to_jsonb(projects)->>'tenant_uuid'`: referencia de linha inteira exige `SELECT` na tabela toda e anularia o escopo por coluna;
- contrato ampliado em `test_host_agent_contract.py`: as colunas concedidas sao comparadas exatamente com as que o agent consulta, e privilegios de escrita fora das tabelas do agent sao proibidos;
- instalacoes afetadas: recrie o container `control-plane-migrations` para aplicar os grants.

## 2026-08-24 — Fix: GRANT CONNECT explicito para platform_app/platform_meta_admin

- o database do control plane tem CONNECT revogado do PUBLIC (hardening); as duas roles novas nao recebiam o grant e a API morria com InsufficientPrivilegeError no startup;
- ambas agora recebem `GRANT CONNECT ON DATABASE ...` no mesmo padrao fetchval+execute do key_authorizer; contrato estendido exige o grant explicito para as quatro identidades.

## 2026-08-24 — Fix: senha de platform_app/platform_meta_admin nunca era aplicada

- `ensure_platform_app_role` e `ensure_platform_meta_admin_role` chamavam `conn.execute("SELECT format('ALTER ROLE ... PASSWORD %L', ...)")`: o SELECT so retorna a string, o ALTER nunca roda — as roles nasciam sem senha e a API morria com InvalidPasswordError no startup;
- corrigido para o padrao correto (`fetchval` + `execute(password_statement)`), o mesmo de key_authorizer/host_agent_rw;
- novo contrato em `test_api_dsn_separation_contract.py`: toda alteracao de senha de role precisa passar por fetchval+execute, e nenhum execute direto do SELECT de formato e permitido;
- instalacoes afetadas: recrie o container `control-plane-migrations` para aplicar as senhas antes de subir a API.

## 2026-08-24 — Fix: `import os` ausente em main.py quebrava o startup da API

- o fail-fast de META_ADMIN_DSN/PLATFORM_READER_DB_PASSWORD usava `os.getenv` sem `import os` no topo de `main.py` — py_compile nao pega NameError e o container morria no boot;
- novo contrato AST (`test_main_stdlib_imports_contract.py`): qualquer modulo stdlib usado como nome global em main.py precisa estar importado; cobre essa classe de regressao offline, sem depender das dependencias do app.

## 2026-08-24 — Fix: setup.sh agora gera HOST_AGENT_DB_PASSWORD

- o cutover estrito das identidades esqueceu de gerar a senha do host-agent no setup: instalacao limpa falhava no `install.sh` com "HOST_AGENT_DB_PASSWORD ausente ou placeholder";
- `setup.sh` gera as cinco senhas de identidade (KEY_AUTHORIZER, PLATFORM_READER, PLATFORM_APP, META_ADMIN, HOST_AGENT) pelo mesmo gerador;
- novo contrato `test_setup_secret_generation_contract.py`: deriva as chaves diretamente do `.env.example` — qualquer identidade de banco nova passa a exigir, obrigatoriamente, geracao no setup.

## 2026-08-24 — CI permanente e suíte E2E opt-in da plataforma

- novo workflow `.github/workflows/ci.yml` em toda PR/main: suite smoke de contratos, sintaxe Python/Bash/Lua, ShellCheck, validacao dos arquivos Compose e `flutter analyze`;
- nova suite opt-in `tests/smoke/test_platform_e2e_integration.py` (`RUN_PLATFORM_E2E=1` em instalacao descartavel): criacao real com perfil de recursos aplicado ao `.env`, gateway fail-closed sem credencial (401) e comportamento com key-authorizer fora do ar (5xx) com recuperacao verificada;
- contrato `test_ci_workflow_contract.py` impede o CI de sumir ou de ligar a flag de E2E no runner;

## 2026-08-24 — Separação de DSN da Projects API (platform_app) e cutover estrito do host-agent

- nova `DB_DSN` da Projects API: role dedicada `platform_app` (DML completo apenas nas tabelas do schema public do control plane; sem administracao de cluster, sem databases de tenant, CONNECTION LIMIT 100);
- Postgres-Meta passa a usar `META_ADMIN_DSN` com a credencial dedicada `platform_meta_admin` (membro de `supabase_admin`, revogavel e auditavel): o superuser global deixa de existir no ambiente da API;
- migrations provisionam as quatro identidades (`key_authorizer`, `host_agent_rw`, `platform_app`, `platform_meta_admin`) e exigem as senhas correspondentes; compose falha com `:?` se qualquer uma estiver ausente;
- host-agent em cutover estrito: a derivacao legada por `POSTGRES_USER/POSTGRES_PASSWORD` foi removida — sem `HOST_AGENT_DB_PASSWORD` util, o agent recusa iniciar; setup gera todas as novas senhas;
- instalacoes existentes: adicione `PLATFORM_APP_DB_PASSWORD` e `META_ADMIN_DB_PASSWORD` ao `.env`, rode o container `control-plane-migrations` para provisionar as roles e recrie `projects-api` e o host-agent;
- novos contratos: `test_api_dsn_separation_contract.py`; docs EN/PT-BR atualizadas (tabela de identidades).

## 2026-08-24 — Perfil de recursos por projeto e telemetria com identidade dedicada

- migration `0005_project_resource_profile.sql`: coluna `projects.resource_profile` (small|medium|large, default `medium`);
- criacao e duplicacao aceitam `resource_profile` no payload; o valor persiste no control plane, viaja na intencao HMAC ate o host-agent (`resource_profile` validado no protocolo) e chega aos scripts via `PROJECT_RESOURCE_PROFILE_OVERRIDE`;
- edicao pela aba de configuracoes: nova chave `PROJECT_RESOURCE_PROFILE` (dropdown no Flutter), gravada junto com o trio resolvido `PROJECT_MEM_LIMIT/PROJECT_CPUS/PROJECT_PIDS_LIMIT`; chaves derivadas rejeitadas se enviadas diretamente; `auth/rest/nginx` marcados como serviços afetados;
- Flutter: dropdown de perfil no dialog de novo projeto (retorno estruturado name+profile) e campo de selecao nas configuracoes de ambiente;
- telemetria usa a role `platform_reader` (por tenant: CONNECT + SELECT em auth.users/auth.sessions), fail-closed: compose exige a senha com `:?`, o startup da API recusa placeholder e o endpoint responde 503 sem ela; scripts de create/duplicate/restore provisionam a role idempotentemente (`lib/tenant_reader_role.sh`);
- docs canonicas EN + PT-BR atualizadas (identidades de banco em control-plane; limites de recursos em project-lifecycle);
- novos contratos: `test_resource_profile_contract.py`.
- instalacoes existentes: gere `PLATFORM_READER_DB_PASSWORD` no `.env`, aplique a migration 0005 e rode o migrador de limites antes do proximo recreate.

## 2026-08-24 — Limites de recursos por projeto e identidade dedicada do host-agent

- containers nginx/auth/rest de cada projeto passam a subir com `mem_limit`/`memswap_limit`, `cpus` e `pids_limit` definidos via interpolacao fail-closed (`${PROJECT_MEM_LIMIT:?...}`): projeto sem limites no `.env` recusa o start em vez de rodar sem controle;
- novo perfil `PROJECT_RESOURCE_PROFILE` (small|medium|large) no `.env.example`, resolvido para valores concretos no `.env` do projeto em create/duplicate/rename/rotate_key; instalacoes existentes usam o migrador idempotente `tools/migrate_project_resource_limits.py` (dry-run por padrao, `--apply` grava), seguido de recreate;
- nova identidade de banco `host_agent_rw` provisionada pelo comando privilegiado de migrations (`ensure_host_agent_rw_role`): apenas lease/heartbeat/resultado em `host_agent_workers`/`host_agent_commands` e inventario em `project_container_state`; sem acesso a qualquer outra tabela do control plane nem a databases de tenant;
- host-agent resolve o DSN como: `HOST_AGENT_DB_DSN` explicito > identidade dedicada (`HOST_AGENT_DB_PASSWORD`) > derivacao legada de `POSTGRES_*`; o fallback legado sera removido junto com a separacao de DSN da Projects API;
- `control-plane-migrations` exige `HOST_AGENT_DB_PASSWORD` (compose com `:?`) e o install.sh do agent recusa placeholder — alinhe o `.env` antes de reinstalar;
- pendencias da mesma frente que continuam abertas: role restrita para o DSN normal da Projects API (hoje ainda superuser), quotas de conexao/statement_timeout por tenant e quota de disco (hoje so observabilidade);
- novos contratos: `test_project_resource_limits_contract.py` e `HostAgentRoleContractTest`.

## 2026-08-24 — Volume do Storage sem world-writable, perfil TLS de produção e sandbox do host-agent

- `chmod 777` removido de `start.sh`, `setup.sh` e `servidor/host-agent/install.sh`: os diretorios `servidor/volumes/storage{,/objects}` passam a ser `2775` (setgid, sem escrita para "outros") e os tres scripts falham explicitamente quando o UID do operador/host-agent nao corresponde a `STORAGE_RUN_AS_USER` — contrato que o 777 mascarava e que o lifecycle ja exigia (`storage_enforce_namespace_ownership` faz `chown -R` como usuario comun);
- Traefik ganha perfil TLS de producao por variaveis de ambiente: `TRAEFIK_ENABLE_TLS`, `TRAEFIK_TLS_MODE=file|acme` e `TRAEFIK_ACME_EMAIL`. Com TLS ativo, o renderer emite routers `websecure` com certificado (arquivo em `servidor/traefik/certs/traefik/{tls.crt,tls.key}` ou Let's Encrypt via HTTP-01), router `force-https` (prioridade 150: acima do catch-all, abaixo dos routers de scanner) e redirect permanente; porta 443 publicada; `acme.json` montado. Fail-closed: certificado ausente no modo file, email placeholder no modo acme ou `SERVER_PROTO=https` sem TLS abortam o render e preservam a ultima configuracao valida; `traefik.yml` declara `websecure` e o resolver `letsencrypt` inertes;
- unit systemd do host-agent confinada: `ProtectSystem=full`, `ProtectHome=read-only`, `PrivateTmp=true`, `CapabilityBoundingSet=` vazio, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`, `RestrictRealtime`, `RestrictSUIDSGID`, `LockPersonality`, `ProtectClock/Hostname/KernelLogs`; `ReadWritePaths` resolvido pelo instalador para `SERVIDOR_DIR`/`AGENT_DIR`;
- novas docs canonicas de HTTPS (`docs/01-https-setup.md` / `docs/pt-br/01-setup-https.md`) descrevem o fluxo por variaveis de ambiente; o procedimento manual antigo de editar Traefik/routers foi retirado;
- novos contratos: `test_storage_volume_permissions_contract.py`, `test_traefik_tls_profile_contract.py` e `SystemdSandboxContractTest` em `test_host_agent_contract.py`.
- instalacoes existentes: gere os certificados do modo escolhido antes de ligar `TRAEFIK_ENABLE_TLS`; reinstale o host-agent (`sudo bash servidor/host-agent/install.sh`) para receber a sandbox; se o UID do operador diferir de `STORAGE_RUN_AS_USER`, alinhe `HOST_AGENT_USER`/`STORAGE_RUN_AS_USER`.

## 2026-08-21 — `.env` global deixa de ser distribuido aos containers

- `auth` e `rest` de cada projeto nao recebem mais `env_file`: passam a rodar somente com o bloco `environment:` declarado, que ja cobria tudo que os dois consomem (222 -> 43 variaveis no `auth`, 194 -> 13 no `rest`);
- `db`, `realtime`, `supavisor`, `functions` e `storage` deixaram de montar o `.env` global; `storage` mantem o `.storage.env`, de escopo proprio;
- variaveis que so chegavam pelo `env_file` passaram a ser declaradas: `POSTGRES_USER` e `META_GUEST_PASSWORD` no `db`, os quatro `POSTGRES_*` no `functions` e `GOTRUE_MAILER_EXTERNAL_HOSTS` no `auth`;
- o worker de Edge Functions nao herda mais o ambiente do runtime: recebe `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`, `JWT_SECRET` e `PROJECT_REF`, e nada alem disso;
- com isso, 14 segredos do control plane — entre eles `PROJECT_SECRETS_MASTER_KEY`, `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` e `HOST_AGENT_HMAC_SECRET` — deixam de existir no ambiente dos containers de tenant;
- novo `tests/smoke/test_global_env_scope_contract.py` impede a volta do `env_file` global e do `...globalEnv` no runtime de functions;
- instalacoes existentes: os projetos ja criados mantem o `docker-compose.yml` antigo ate serem re-renderizados. Use Recreate com todos os servicos (ou `rotate_key.sh`, duplicate e rename, que tambem re-renderizam) e recrie a stack global com `docker compose up -d --force-recreate`.

## 2026-08-21 — Chave opaca deixa de ter visualização única

- `claim` passou a descriptografar sem consumir: a `publishable` é legível por qualquer membro do projeto e a `secret` exige admin mais step-up a cada leitura;
- a revelação cifrada não tem mais TTL e vive enquanto a versão da chave existir; rotação, revogação, disable de slot e expiração apagam o material da versão que deixa de autenticar;
- respostas de criação, rotação e claim não trazem mais `reveal_once`, e a preparação da migração não devolve `reveal_deadline`;
- `GET /api/projects/{project}/api-key-reveals` troca `expires_at` por `key_status` e `revealed_at`, e lista somente versões que ainda autenticam;
- instalações existentes: aplique a migration `0004_persistent_api_key_reveals` antes de subir a Projects API desta versão.

## 2026-08-20 — Migrations versionadas do control plane

- schema do control plane saiu do startup da Projects API e passou a viver em `servidor/api-internal/app/migrations`, com ledger `control_plane_schema_migrations`, checksum por versão, advisory lock e uma transação por versão;
- o boot da API apenas verifica a versão aplicada e recusa servir quando o banco está atrás da imagem; nenhum DDL sai do processo que atende requisições;
- `create_template.sh` ficou restrito ao bootstrap de cluster, e a identidade `key_authorizer` passou a ser provisionada pelo mesmo comando privilegiado das migrations;
- novo serviço efêmero `control-plane-migrations` no Compose: `key-authorizer` e `projects-api` só sobem depois que ele conclui com sucesso;
- corrigido o cálculo de `is_idempotent`/`retryable` no schema de `jobs`, que violava `NOT NULL` em instalações com jobs anteriores à coluna `action`;
- `jobs` convergiu para a definição canônica em instalações existentes: `NOT NULL` em `action` e `updated_at` e os `CHECK` de progresso, etapas e tentativa;
- `python -m app.migrate_project_secrets` deixou de criar schema e passou a exigir a migration aplicada;
- instalações existentes: aplique as migrations antes de subir a Projects API desta versão, com `start.sh` ou `docker compose -f docker-compose-api.yml -f <perfil> --env-file .env run --rm control-plane-migrations`.

## 2026-08-17 — Cutover HMAC interno estrito

- removido `NGINX_SHARED_TOKEN` do runtime, Traefik e OpenResty;
- removido o middleware bearer legado e qualquer fallback por derivação;
- `STUDIO_GATEWAY_HMAC_SECRET` e `PROJECTS_API_HMAC_SECRET` passam a ser obrigatórios e independentes;
- instalações existentes devem executar `python3 tools/migrate_internal_hmac_v1.py` antes do rebuild/restart;
- removida a regra morta `rewrite ^/object/sign$ /storage/v1/$1 break;`.

# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato deste arquivo segue as diretrizes do [Keep a Changelog](https://keepachangelog.com/) e este projeto adota [Versionamento Semântico](https://semver.org/).

## [Não lançado]

### 2026-08-13

- Storage API e imgproxy passaram de containers por projeto para instâncias
  globais compartilhadas, usando sem patches o modo multi-tenant oficial do
  Storage v1.61.12, registry dedicado cifrado, backend file por namespace UUID
  e proxy de data plane numa rede exclusiva dos Nginx confiáveis, mantendo a
  Admin API fora das redes alcançáveis pelos projetos.
- Lifecycle de create, duplicate, rename, delete, settings, backup e restore
  passou a registrar, validar e remover tenants pela Admin API oficial, com
  rollback compensatório, quiescência fail-closed por tenant nas operações
  consistentes, vínculo obrigatório com `projects.tenant_uuid` e sem caminho de
  runtime para a arquitetura anterior.
- Credenciais S3/SigV4 e Storage Vectors passaram a ser isolados por tenant;
  wrappers usam o Nginx do projeto, clones recebem credenciais/namespace novos e
  rename preserva objetos pela identidade imutável.
- Adicionada ferramenta transitória, resumível e fail-closed para converter
  projetos e backups existentes, mantendo Projects API/host-agent quiescentes
  enquanto houver estado misto e restaurando a mesma topologia Compose detectada.
- Adicionados contratos estáticos e smoke opt-in de dois tenants cobrindo
  objetos, opaque keys, S3, Vectors, imagens, limites, clones, rename,
  backup/restore, delete, headers hostis e indisponibilidade do Storage global.

- Logs do Storage global e do proxy de data plane passaram a carregar tenant,
  request ID e operacao sem query strings ou credenciais.
- O proxy de data plane passou a rejeitar com HTTP 421 requests sem host de
  tenant UUID canonico, antes que alcancem o Storage compartilhado.

### 2026-08-11

- Adicionada rotação automática de anon/service keys, habilitada por padrão e
  configurável por projeto, com agenda derivada do `exp`, jobs duráveis,
  concorrência limitada, auditoria e bloqueio explícito após falha.
- Host-agent passou a autorizar o ator de sistema exclusivamente para
  `rotate_keys` em projetos habilitados; rotações interrompidas são retomadas
  pela mesma intenção durável.
- Cache de service key passou a exigir a versão canônica em cada uso e falhar
  fechado quando a Projects API estiver indisponível.
- Script de rotação passou a exigir `PROJECT_UUID`, emitir `jti` aleatório e não
  registrar as chaves geradas em stdout.

### 2026-07-24

- Validação de nomes de projeto centralizada e aplicada à criação, duplicação e
  renomeação, incluindo bloqueio de nomes reservados pelas rotas da plataforma.
- Configuração HTTPS do Traefik passou a ser gerada pelo arquivo dinâmico, com
  `websecure`, TLS e resolução de certificados também para a Projects API e para
  os roteadores de bloqueio.

### 2026-07-22

- Fluxo de autenticação do Studio reorganizado com middleware dedicado,
  bootstrap explícito da aplicação e navegação autenticada centralizada.
- Modelos, providers e acesso à API do seletor de projetos foram reorganizados;
  o instalador do host-agent passou a aceitar usuário de serviço configurável.
- Ordem de rollback e carregamento do ambiente no rename foram corrigidos, e o
  handler de avatares passou a finalizar respostas de forma consistente.
- Utilitários temporários de migração legada e seus testes foram removidos,
  mantendo apenas os caminhos canônicos de configuração e lifecycle.

### 2026-07-21

- Python 3.10 ou superior tornou-se requisito explícito do host para setup,
  configuração do Studio/Authelia e execução do host-agent.
- Configuração de runtime e sincronização de CA do Studio foram automatizadas,
  com contextos de build reduzidos por novos `.dockerignore`.
- Requisições HTTPS de saída do OpenResty passaram a validar certificado,
  hostname e SAN; endpoints internos obedecem à política TLS configurada.
- Autorizações de pontos de restauração foram endurecidas: backup exige
  administrador do projeto e restore/delete exigem proprietário ou admin global.
- Deleção de projetos foi consolidada em um workflow coordenado, sem comandos
  parciais de remoção de tenant expostos pelo protocolo do host-agent.
- Processamento de avatar foi isolado em módulo próprio com libvips, validação de
  formato/tamanho, normalização para WebP e rejeição explícita de conteúdo inválido.

### 2026-07-20

- Integração do Studio com contexto por slug recebeu correções na propagação do
  contexto pelo proxy e passou a usar por padrão uma imagem versionada publicada.
- Contrato de contexto por URL, isolamento entre abas e proveniência do patch do
  Studio foram documentados.

### 2026-07-19

- Studio passou a acompanhar jobs assíncronos de criação, duplicação e rotação
  com polling, progresso, status e atualização reativa dos cards e diálogos.
- Criação de projeto ganhou recuperação controlada de estado residual, baseada
  no histórico durável do job, e rollback transacional mais preciso.
- Host-agent passou a aguardar o schema do control plane e tratar inicialização e
  reconexão de maneira ordenada.
- Identidade passou a distinguir o UUID canônico do projeto do `tenant_uuid`
  usado por Realtime, JWTs, backups e serviços externos.
- Contexto do Studio passou a ser resolvido pelo control plane a partir do slug
  na URL, com autorização por projeto e isolamento independente por aba.
- Fontes implícitas de contexto, incluindo cookie e valores globais, foram
  removidas; handlers de IA e proxies passaram a exigir referência explícita e
  validada do projeto.

### 2026-07-17

- Backup e restore passaram a reportar progresso detalhado em tempo real desde a
  parada dos serviços até a publicação do backup e reinício do projeto.
- Camada OpenResty/Lua recebeu comparação segura de segredos, grupos de admin
  normalizados e controle monotônico de versão do cache de service key.
- Cards de pontos de restauração passaram a exibir o usuário responsável pela
  criação, com a atribuição persistida no control plane.

### 2026-07-16

- Adicionado sistema de pontos de restauração com backup frio, manifesto,
  restauração, backup de segurança prévio e rollback transacional em caso de erro.
- Protocolo do host-agent e Studio foram ampliados para backup/restore, com dados
  isolados por UUID e registros persistidos no control plane.
- Projects API foi separada em routers de health, lifecycle, colaboração e rotas
  internas, com dependências compartilhadas e validação HMAC endurecida.
- Resolução do diretório físico de projetos no host-agent foi padronizada e
  falhas de comandos passaram a produzir diagnóstico explícito.

### 2026-07-15

- Adicionado host-agent independente, instalado como serviço `systemd`, para
  executar o lifecycle físico a partir de intenções HMAC assinadas e persistidas.
- Execução de comandos passou a usar conjunto fechado, leases, heartbeat e
  validação de identidade, retirando da Projects API o acesso direto ao Docker.
- Corrigida a visibilidade do tipo `halfvec` para o papel
  `supabase_storage_admin` nos bancos de projeto.

### 2026-07-14

- Implantação ganhou perfis explícitos `single-node` e `split-node`, utilizáveis
  de forma não interativa por `setup.sh`, `start.sh` e `stop_containers.sh`.
- Configuração dinâmica dos projetos no Traefik passou a ser renderizada e
  observada por arquivo, reforçando o isolamento do acesso ao daemon Docker.
- Tradução de consultas do Analytics foi corrigida para projeções e uniões de
  campos escalares usadas pelo Studio.

### 2026-07-13

- Credenciais S3 Vectors passaram a ser expostas ao Studio somente pelo control
  plane e vinculadas ao Storage do tenant selecionado.
- Analytics passou a ser construído localmente com tradução de SQL do dialeto
  BigQuery para PostgreSQL e consultas/logs isolados pelo projeto selecionado.
- Acesso de Traefik e Vector ao Docker foi endurecido com interfaces restritas e
  remoção de montagens diretas do socket nos consumidores.
- Permissões de `.env` e arquivos de configuração gerados foram ajustadas para
  permitir leitura pelos usuários não root dos contêineres.

### 2026-07-12

- Adicionado perfil de usuário integrado ao Authelia, com persistência atômica,
  auditoria sem PII, edição no Studio e sincronização sem bloquear leituras.
- Upload autenticado de avatar passou a gerar URL estável por usuário; avatares
  também passaram a aparecer nas listas administrativas.
- Adicionado plugin local Supabase Guard no Traefik para validar saúde e isolar
  requisições por projeto, inclusive em instalações já existentes.
- Configurações de serviços e Docker foram externalizadas para o ambiente, e os
  scripts de start/stop passaram a carregar explicitamente o env do servidor.
- Ordem de inicialização e healthcheck do Studio foram corrigidos para evitar
  respostas 502 antes de o dashboard estar pronto.
- Storage Vectors ganhou roteamento centralizado no Studio, backend `pgvector`
  por projeto, adaptação das rotas de buckets/índices e credenciais SigV4 isoladas.
- Lifecycle de vetores foi integrado à criação, duplicação e rename, com extensão
  no template, wrappers por bucket, limpeza e validação antes do commit da operação.
- Resolução assinada da referência de projeto foi compartilhada entre os proxies
  do Studio, eliminando fontes divergentes de contexto.

### 2026-07-11

- Comunicação interna ganhou tokens HMAC reutilizáveis e autenticação assinada
  para o push-worker, com controles de papel nos membros de projeto.
- Jobs passaram a ser persistentes, idempotentes quando aplicável e consultáveis,
  com tentativas, retry, etapas, progresso e caudas limitadas de stdout/stderr.
- Segredos dos projetos foram migrados para envelope encryption AES-256-GCM com
  DEK por tenant e chaves separadas por domínio criptográfico.
- Control plane passou a centralizar identidade, grupos, settings, segredos,
  configuração de runtime, notificações e trilha de auditoria.
- Service keys passaram a ser armazenadas cifradas e servidas por cache
  versionado, com invalidação ativa, métricas e incremento atômico na rotação.
- Metadados de expiração dos JWTs e avisos configuráveis de keys vencidas ou
  próximas do vencimento foram adicionados à API e ao Studio.
- Deleção passou a encerrar pools do Supavisor e drenar conexões antes de remover
  o banco, preservando-o quando o encerramento seguro não puder ser confirmado.
- Rename recebeu correções no Compose, Supavisor, Realtime e carregamento de env;
  snippets passaram a ser migrados junto com o slug do projeto.
- Adicionada telemetria administrativa de usuários por projeto e período, com
  filtros, auditoria e visualização nas configurações do Studio.
- Módulos Lua foram reorganizados por domínio e a documentação foi consolidada
  em índice e fontes canônicas para control plane, lifecycle e OpenResty.
- Criada suíte de smoke tests para contratos de HMAC, schema, lifecycle,
  criptografia, cache, telemetria e isolamento entre tenants.

### 2026-07-10

- Adicionado rename completo de projeto, com script de lifecycle, histórico,
  progresso e controles no Studio.
- Gerenciamento ganhou colaboração por projeto, incluindo membros, notas, tags,
  hints, threads e nome de exibição, além de métricas do Realtime.
- Confiabilidade do rename foi reforçada e artefatos de build deixaram de ser
  mantidos no repositório.

### 2026-05-12

- Autorização multi-tenant do Realtime passou a distinguir contexto ausente de
  contexto inválido e a rejeitar tokens globais em endpoints de tenant.
- Bloqueio de requisições sensíveis foi centralizado no serviço de negação do
  Traefik, com respostas 403 consistentes e cadeia de middlewares simplificada.

### 2026-05-11

- Postgres Meta foi migrado de instâncias por projeto para um serviço global,
  com conexão dinâmica cifrada e fronteira de autorização por projeto.
- Adicionado serviço de negação endurecido no Traefik para bloquear arquivos,
  prefixos e caminhos sensíveis sem expor cabeçalhos do servidor.
- Arquitetura e hardening do Postgres Meta global foram documentados.

### 2026-05-08

- Adicionado limite configurável de upload por projeto, validado no OpenResty por
  token HMAC, e rastreamento de settings pendentes até a recriação dos serviços.
- Validação de nomes passou a rejeitar palavras SQL reservadas; snippets e demais
  conteúdos do usuário passaram a exigir escopo explícito de projeto.
- URLs públicas do Storage foram alinhadas à origem externa do Studio, e rotas de
  upload receberam validação dedicada antes do encaminhamento.
- Imagem do Authelia foi atualizada para a versão estável 4.39.

## [0.13.0-alpha] - 2026-04-02 a 2026-05-07

### 2026-05-07
- Jobs passaram a persistir status e mensagem na tabela `jobs`, removendo o estado em memória do processo Python para esses dados.
- Cadastro/bootstrap de admin e cadastro de usuários comuns passaram a gerar hash Argon2id via LuaJIT FFI/libargon2, sem senha em `/tmp`, sem shell e sem senha em argumento de processo.
- Removida a dependência de `X-User-Id` na comunicação interna entre serviços Lua/Nginx.

### 2026-05-06
- Studio consolidado em origem pública única `https://<IP>:9091`, com Authelia integrado em `/auth`.
- Documentado e ajustado o redirecionamento de HTTP para HTTPS na porta `9091`.
- Removida barra final do caminho de autenticação do Authelia e corrigidos redirects.
- Adicionada validação/limpeza do cookie `supabase_project`.
- Usuário desativado passou a receber tela de acesso negado sem loop de login.
- Membros de projeto migrados para identidade por UUID e grupos normalizados no banco.
- Bootstrap do primeiro administrador passou a ocorrer pelo front, sem credencial inicial fixa.

### 2026-05-05
- Implementada autenticação interna baseada em HMAC entre Nginx/Lua, API Python e documentação relacionada.
- `NGINX_SHARED_TOKEN` mantido como camada básica da API interna, sem substituir o HMAC de usuário.
- `push_worker` integrado ao fluxo HMAC backend-to-backend para `/api/internal/push`.

### 2026-04-28
- Instruções de startup e documentação de schema atualizadas.
- Validação de settings e normalização de configuração de ambiente adicionadas.
- Identidade do usuário migrada de hash de email para UUID canônico.
- Assinatura HMAC em Lua refatorada com utilitário SHA256 próprio e suporte a Fernet.
- Sincronização de identidade de usuários com Authelia implementada.

### 2026-04-14
- Adicionado bypass de administrador do sistema para rotação de keys e acesso a settings.
- Lifetime do cookie de projeto aumentado com lógica de renovação.

### 2026-04-13
- Nomeação de containers padronizada e entrega de push notification aprimorada.
- Documentação de geração de portas aleatórias removida/atualizada.
- `SERVER_PROTO` adicionado à configuração e geração de templates de projeto refatorada.

### 2026-04-10
- Deleção de projeto refatorada para executar em background jobs.
- Templates de geração, duplicação, rotação e deleção de projetos melhorados.
- Configurações de bloqueio de signup e pool do PostgREST adicionadas à API/UI.
- Settings de projeto e mensagens de status de job adicionadas ao Studio/API.

### 2026-04-09
- Configuração de ambiente consolidada e estrutura antiga de `secrets` removida.
- `.env.example`, templates, scripts e documentação ajustados para o novo modelo de configuração.

### 2026-04-08
- Proxy Lua de conteúdo do usuário adicionado com endpoints para raiz, pastas, itens e contagem.
- Isolamento por escopo de projeto adicionado para conteúdo do usuário.
- Endpoint de item de pasta adicionado e gerenciamento de pastas aprimorado.

### 2026-04-07
- Pasta de gerenciamento de snippets adicionada com volume Docker.

### 2026-04-06
- Documentação de topologia, portas do Studio e integração do push-worker atualizada.
- `push_worker` tornou-se configurável com TLS e gerenciamento de certificados.
- Rotação de keys de projeto recebeu melhorias de erro e suporte a migração.

### 2026-04-02
- Execução de funções de IA adicionada com validação e tratamento de parâmetros.

## [0.12.0-alpha] - 2026-04-01

### Adicionado
- Sistema de UUID para identificação de projetos multi-tenant
- PROJECT_UUID salvo no .env de cada projeto
- Tenant do Realtime agora usa UUID como external_id
- Fallback para project_name em projetos antigos
- Função `get_project_uuid_from_env()` para leitura de UUID do .env
- Método `updateProjectKey()` no ProjectListNotifier para atualização cirúrgica de cache

### Alterado
- Expiração de tokens JWT reduzida de 8 anos para 3 meses
- Issuer (iss) dos JWTs agora usa UUID em vez de project_name
- UUID gerado no Python e passado como argumento para scripts shell
- Nginx usa UUID no header Host do websocket Realtime
- Rotate key mantém UUID existente
- Deleção de projetos usa UUID para Realtime e project_name para Supavisor
- Cache da ANON_KEY no Flutter agora atualiza corretamente após rotação

### Corrigido
- Bug de cache no Flutter onde ANON_KEY não atualizava após rotação
- Caminho de leitura do .env dentro do Docker (/docker/projects)

## [0.11.0-alpha] - 2026-03-23 a 2026-03-31

### Adicionado
- Sistema completo de templates de email para Auth (invite, recovery, magic link, confirmation, email change)
- Documentação de autenticação multi-tenant com validação JWT por tenant
- Sistema de transações com rollback automático nos scripts de geração
- API GeoIP self-hosted com fallback para GitHub
- Middleware de validação de token compartilhado para segurança da API
- Componentes Elixir customizados para Realtime
- Token JWT global para autenticação do Supavisor

### Alterado
- Refatoração da UI de gerenciamento com providers e componentes
- Melhorias no fluxo de convite e recuperação de senha
- Tratamento de erros nos scripts shell usando return em vez de exit
- Atualização do banco de dados GeoIP com fallback automático
- Expansão da documentação de arquitetura com detalhes de roteamento Nginx
- Modo de transferência de projetos melhorado

### Corrigido
- Caminho de montagem do volume recovery.html no Nginx
- Tratamento de CRLF em scripts shell
- Documentação sobre erro de CRLF adicionada

### Removido
- Variáveis de ambiente não utilizadas do pooler proxy port

## [0.10.0-alpha] - 2026-03-20

### Adicionado
- Autenticação para dashboard do Realtime com usuário e senha gerados automaticamente
- Geração de token de configuração para acesso à API de config

### Alterado
- Atualização de imagens Docker dos componentes principais
- Limpeza de comentários no PostgreSQL

## [0.9.0-alpha] - 2026-03-19

### Adicionado
- Sistema de rotação de chaves JWT anônimas por projeto
- Endpoint `/api/config` com validação de token
- Endpoints mock para organizações e validação de API keys
- Endpoint para consultar bancos de dados de projetos específicos
- Descoberta automática de funções disponíveis no banco
- Integração completa com IA: geração de SQL e autocompletar código
- Suporte a múltiplos provedores LLM (OpenAI, Anthropic, Groq, OpenRouter)

### Corrigido
- Tratamento de tags de "thinking" do LLM no parsing de argumentos
- Melhorias nos headers de cache control

## [0.8.0-alpha] - 2026-03-17

### Adicionado
- Documentação completa da arquitetura do sistema multi-tenant
- Template inicial do PostgreSQL documentado
- Guia de troubleshooting com principais erros e soluções
- Documentação sobre gerenciamento de logs Vector

### Alterado
- Desabilitado arquivamento WAL no docker-compose.yml
- Duplicação de projetos agora copia histórico de migrações Auth/Storage

### Removido
- Script `fix-permissions.sh` desnecessário

## [0.7.0-alpha] - 2026-03-16

### Adicionado
- Documentação de gerenciamento de usuários Authelia
- Arquivo `tarefas.md` adicionado ao `.gitignore`

## [0.6.0-alpha] - 2026-03-11 a 2026-03-12

### Adicionado
- Sistema completo de notificações push com Firebase FCM
- Worker Python para processamento de notificações
- Assinatura JWT via Nginx Lua para notificações
- Documentação de setup de notificações

### Alterado
- Refatoração completa do gateway Nginx/Lua para melhor organização

## [0.5.0-alpha] - 2026-03-05

### Adicionado
- Persistência de plugins do Traefik usando volume no host
- Validação de nome de projeto na API Python
- Padronização de hash na API Lua

### Alterado
- Removido shell script na criação de usuário do Realtime

## [0.4.0-alpha] - 2025-12-16 a 2025-12-18

### Adicionado
- Sistema de startup dinâmico para múltiplos projetos
- Script `start.sh` melhorado

### Alterado
- Atualização da imagem do Studio
- Ajustes em mudanças de diretório

### Removido
- Startup da API do Studio
- Configuração antiga do Vector
- Script de correção de permissões

## [0.3.0-alpha] - 2025-11-25 a 2025-12-12

### Adicionado
- Validação de admin key para endpoint `/rest/v1/`
- Suporte a método OPTIONS para CORS
- Script `authelia.sh` para geração de certificados SSL
- Script `stop_containers.txt` para gerenciamento Docker
- Comandos de log adicionais com queries melhoradas
- Animações e melhorias na UI do Admin Screen

### Alterado
- Tratamento aprimorado de CORS com headers refinados
- Redirecionamentos Nginx usando variável `$host` em vez de IP hardcoded
- Nova paleta de cores para consistência visual
- Versão do OpenResty atualizada no Dockerfile
- Scripts de setup e start agora requerem sudo

### Corrigido
- Extensão de arquivo de log do Vector
- Gerenciamento de partições no banco de dados

## [0.2.0-alpha] - 2025-10-17 a 2025-11-04

### Adicionado
- Documentação sobre duplicação de projetos
- Seção de troubleshooting no README

### Alterado
- Dockerfile atualizado para usar imagem base do Flutter
- Melhorias no README

## [0.1.0-alpha] - 2025-05-05

### Removido
- Pastas originais do Supabase:
  - `.github/`, `apps/`, `examples/`, `i18n/`, `packages/`, `scripts/`, `supa-mdx/`, `tests/studio-tests/`  
  - Arquivos de configuração e build: `.dockerignore`, `.misspell-fixer.ignore`, `.npmrc`, `.nvmrc`,  
    `.prettierignore`, `.prettierrc`, `.vale.ini`, `CONTRIBUTING.md`, `DEVELOPERS.md`, `Makefile`,  
    `knip.jsonc`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `supa-mdx-lint.config.toml`,  
    `tsconfig.json`, `turbo.json`

### Alterado
- Substituído o **Kong** pelo **Traefik** como gateway de API e ajustadas configurações de roteamento.  
- Arquivo `SECURITY.md` atualizado para embutir o conteúdo de `security.txt` (conservando avisos de copyright).

### Mantido
- Arquivo `LICENSE` com a Apache 2.0 na raiz do repositório.  
- Qualquer cabeçalho de copyright/patente nos arquivos de código restantes.  
- Arquivos de documentação essenciais (`README.md`, `SECURITY.md`).
