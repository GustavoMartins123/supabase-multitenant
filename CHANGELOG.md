# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato deste arquivo segue as diretrizes do [Keep a Changelog](https://keepachangelog.com/) e este projeto adota [Versionamento Semântico](https://semver.org/).

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
