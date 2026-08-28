# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/) e [Versionamento Semântico](https://semver.org/).

## [Não lançado]

### 2026-08-27

#### Adicionado

- Capacidade personalizada por projeto: Memória, CPUs e PIDs editáveis no Studio.
- Perfil `custom` definido no `.env` do servidor, selecionável na criação.
- `tools/platform_bottleneck_probe.py` para carga simultânea de todos os serviços, host, cgroups e SLO de p95.
- Fixtures descartáveis com lock, recuperação e limpeza automática.
- Limites de CPU, RAM e PIDs para Traefik, GeoIP, watcher e deny-service.

#### Alterado

- Perfis: `small` 256 MiB/1,85 CPU, `medium` 1 GiB/2,00 CPU e `large` 4 GiB/3,00 CPU.
- Pisos Nginx/Auth/REST em 0,40/1,20/0,25 CPU e memória rateada em 1:2:5.
- Reserva padrão do host em 25% e sobrecompromisso padrão de CPU em 100%.
- Pisos de Postgres e serviços compartilhados recalibrados.

#### Removido

- Limite global de projetos na criação e duplicação.
- Arquivo de capacidade derivada consumido pela Projects API.

#### Corrigido

- Funções Edge deixam de receber credenciais do banco do cluster.
- Setup preserva `.env` e segredos existentes em re-execução.
- Restore valida as tabelas do Realtime declaradas no backup.
- Backups e arquivos de ciclo de vida criados com permissão restrita.
- Slots de replicação sem colisão em projetos com nomes longos.
- Apenas assets estáticos do Studio ficam públicos.
- Signup do Studio com rate-limit e checagens antes do hash de senha.
- Cadeia anti-abuso do Traefik passa a cobrir HTTPS.
- Exclusão de projeto continua a limpeza após falha e mantém o registro para nova tentativa.
- Headers de identidade do cliente deixam de atravessar os proxies internos do Studio.
- `extract_token.sh` valida o nome do projeto.
- Listagem de usuários em modo admin restrita a administradores da plataforma.
- Hosts pequenos iniciam em modo degradado com aviso, sem abortar o `start.sh`.
- Valores inválidos de `PLATFORM_*` caem no padrão em vez de travar a inicialização.
- Memória e disco do host aceitam valores decimais (ex.: `7.7g`).
- Studio não é mais reconstruído a cada `start.sh`.
- Capacidade de CPU vira apenas referência informativa.
- Documentação de chaves opacas alinhada às rotas e migrations reais.
- Rota Realtime do Nginx monta a URI após `auth_request`.
- Capacidade de CPU desconta a soma efetiva dos pisos compartilhados.

### 2026-08-26

#### Adicionado

- `tools/platform_load_probe.py` para carga dos perfis e medição de cgroups.
- Overrides de capacidade para os serviços compartilhados.
- Configuração do Postgres derivada do host e carregada por `conf.d`.
- Aplicação dinâmica dos limites compartilhados.
- Teto de projetos aplicado na criação e duplicação.

#### Alterado

- Memória e PIDs passam a usar picos do cgroup.
- PIDs usam pisos independentes por serviço.
- Parâmetros de memória, conexões, WAL, workers e slots do Postgres passam a ser derivados.

#### Corrigido

- Dimensionamento do Nginx do Studio, Realtime, Postgres Meta e PostgREST.
- Reaplicação dos limites após criação, duplicação e exclusão.
- Duplicação deixa de contornar o teto de capacidade.

### 2026-08-25

#### Adicionado

- Calculador de capacidade para memória, CPU, disco, conexões, PIDs, workers, WAL e arquivos temporários.
- Relatório de capacidade com restrição limitante e origem dos baselines.
- Migração de limites existentes por `tools/migrate_project_resource_limits.py`.

#### Alterado

- Perfis passam a limitar o projeto inteiro e são rateados entre Nginx, Auth e REST.
- PostgREST recebe limite de heap GHC e pool padrão de 10 conexões.
- Baselines compartilhados usam memória anônima e picos do cgroup.
- Realtime, Supavisor e Nginx do Studio escalam com a quantidade de CPUs.
- Studio organiza configurações em abas.

#### Corrigido

- Persistência de `PROJECT_RESOURCE_PROFILE` no ambiente do projeto.
- Leitura de valores entre aspas no `.env`.
- Preservação de proprietário e permissões nas escritas atômicas.
- Aviso de reinicialização do host-agent após reinstalação.

### 2026-08-24

#### Adicionado

- CI permanente e suíte E2E opt-in.
- Perfil de recursos persistido no control plane e editável pelo Studio.
- Identidades dedicadas `platform_app`, `platform_meta_admin`, `platform_reader` e `host_agent_rw`.
- Limites fail-closed de CPU, RAM e PIDs nos containers de projeto.
- TLS por arquivo ou ACME no Traefik.
- Sandbox systemd do host-agent.

#### Corrigido

- Escrita do Docker Buildx dentro do sandbox.
- Rollback duplicado e recuperação de projetos parcialmente criados.
- Provisionamento e grants de `platform_reader`.
- Detecção de host-agent offline sem indicar resíduos inexistentes.
- Propagação do perfil na criação, duplicação e recuperação.
- Exclusão privilegiada de projetos pela conexão administrativa.
- Grants, senhas e geração de segredos das identidades dedicadas.
- Permissões do volume compartilhado do Storage.

### 2026-08-21

#### Alterado

- Containers deixam de receber o `.env` global e passam a receber apenas variáveis declaradas.
- Edge Functions deixa de herdar o ambiente completo do runtime.
- Chaves opacas permanecem reveláveis enquanto a versão estiver ativa.
- Leitura de chave `secret` exige administrador e step-up.

#### Migração

- Recriar stacks existentes para remover o ambiente global.
- Aplicar a migration `0004_persistent_api_key_reveals`.

### 2026-08-20

#### Adicionado

- Migrations versionadas do control plane com ledger, checksum, lock e transações.
- Serviço `control-plane-migrations` como dependência da Projects API e Key Authorizer.

#### Alterado

- Projects API apenas verifica a versão do schema durante o boot.
- Provisionamento do Key Authorizer passa para as migrations.

### 2026-08-17

#### Alterado

- HMAC interno passa a exigir segredos independentes para Studio Gateway e Projects API.
- Removidos `NGINX_SHARED_TOKEN`, bearer legado e fallback por derivação.

#### Removido

- Regra inativa de rewrite de `/object/sign`.

#### Migração

- Executar `python3 tools/migrate_internal_hmac_v1.py` antes do rebuild de instalações existentes.

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
