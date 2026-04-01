# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato deste arquivo segue as diretrizes do [Keep a Changelog](https://keepachangelog.com/) e este projeto adota [Versionamento Semântico](https://semver.org/).

## [1.1.0] - 2026-04-01

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

## [1.0.10] - 2026-03-23 a 2026-03-31

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

## [1.0.9] - 2026-03-20

### Adicionado
- Autenticação para dashboard do Realtime com usuário e senha gerados automaticamente
- Geração de token de configuração para acesso à API de config

### Alterado
- Atualização de imagens Docker dos componentes principais
- Limpeza de comentários no PostgreSQL

## [1.0.8] - 2026-03-19

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

## [1.0.7] - 2026-03-17

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

## [1.0.6] - 2026-03-16

### Adicionado
- Documentação de gerenciamento de usuários Authelia
- Arquivo `tarefas.md` adicionado ao `.gitignore`

## [1.0.5] - 2026-03-11 a 2026-03-12

### Adicionado
- Sistema completo de notificações push com Firebase FCM
- Worker Python para processamento de notificações
- Assinatura JWT via Nginx Lua para notificações
- Documentação de setup de notificações

### Alterado
- Refatoração completa do gateway Nginx/Lua para melhor organização

## [1.0.4] - 2026-03-05

### Adicionado
- Persistência de plugins do Traefik usando volume no host
- Validação de nome de projeto na API Python
- Padronização de hash na API Lua

### Alterado
- Removido shell script na criação de usuário do Realtime

## [1.0.3] - 2025-12-16 a 2025-12-18

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

## [1.0.2] - 2025-11-25 a 2025-12-12

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

## [1.0.1] - 2025-10-17 a 2025-11-04

### Adicionado
- Documentação sobre duplicação de projetos
- Seção de troubleshooting no README

### Alterado
- Dockerfile atualizado para usar imagem base do Flutter
- Melhorias no README

## [1.0.0] - 2025-05-05

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
