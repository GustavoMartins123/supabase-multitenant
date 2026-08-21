# Índice da documentação

Esta pasta contém a documentação técnica do `supabase-multitenant`.

A regra é simples: cada assunto deve ter uma fonte canônica. O `00-arquitetura.md` apresenta a visão geral e aponta para documentos especializados. Detalhes operacionais ou de implementação não devem ser copiados para vários arquivos.

O estado arquitetural atual assume **host-agent no lugar de acesso Docker pela API**, **API keys opacas como credenciais públicas** e **Storage/imgproxy globais multi-tenant**. Documentos que descrevam LifecycleProxy, Docker socket na Projects API ou Storage/imgproxy por projeto devem ser tratados como material histórico e corrigidos, não como caminhos alternativos suportados.

## Comece por aqui

1. [Arquitetura do sistema](00-arquitetura.md)
2. [Control plane](architecture/control-plane.md)
3. [Migrations do control plane](architecture/control-plane-migrations.md)
4. [Lifecycle dos projetos](architecture/project-lifecycle.md)
5. [Host-agent](architecture/host-agent.md)
6. [Storage compartilhado, S3 e Storage Vectors](architecture/storage-vectors-lifecycle.md)
7. [Operação de chaves de API opacas](12-chaves-api-opacas.md)
8. [Arquitetura OpenResty/Lua](architecture/openresty-lua.md)
9. [Supabase Analytics por projeto](architecture/supabase-analytics.md)
10. [Autenticação multi-tenant no Realtime](09-autenticacao-multi-tenant-realtime.md)

## Instalação e configuração

- [Setup com HTTPS](01-setup-https.md)
- [Limite de conexões do PostgreSQL](02-Como-aumentar-o-limite-conexoes-postgres.md)
- [Limite de conexões do Supavisor](03-Como-aumentar-o-limite-conexoes-pooler.md)
- [Limite de conexões do Realtime](04-Como-aumentar-o-limite-conexoes-realtime.md)
- [Setup de notificações](06-setup-notification.md)
- [Erro de CRLF no setup](08-erro-setup-crlf.md)

## Segurança

- [Política de disclosure do repositório](../../SECURITY.md)
- [Gerenciamento de usuários no Authelia](07-gerenciamento-usuarios-authelia.md)
- [Hardening do Postgres-Meta global](10-hardening-postgres-meta.md)
- [Rotação de segredos e conexões do Postgres-Meta](11-rotacao-cripto-conexoes.md)
- [Operação de chaves de API opacas](12-chaves-api-opacas.md)
- [Spec de múltiplas chaves opacas](specs/opaque-api-keys.md)

## Operação e troubleshooting

- [Principais erros](05-principais-erros.md)
- [Migração transitória para Storage compartilhado](architecture/shared-storage-migration.md)
- A visão atual de jobs, recovery, rename, backup, restore e deleção fica em [Lifecycle dos projetos](architecture/project-lifecycle.md).
- A visão atual de segredos, identidade, settings e colaboração fica em [Control plane](architecture/control-plane.md).
- A ordem de aplicação do schema, o ledger e o procedimento de forward-fix ficam em [Migrations do control plane](architecture/control-plane-migrations.md).
- O contrato físico de Docker, lease, timeout e reautorização fica em [Host-agent](architecture/host-agent.md).

## Fontes canônicas

| Assunto | Documento canônico |
| --- | --- |
| visão macro e fronteiras | `00-arquitetura.md` |
| API Python, schema central e autorização | `architecture/control-plane.md` |
| versionamento de schema, ordem do deploy e forward-fix | `architecture/control-plane-migrations.md` |
| criação, duplicação, rename, rotação, backup, restore e deleção | `architecture/project-lifecycle.md` |
| execução física no host, HMAC, lease e comandos fechados | `architecture/host-agent.md` |
| Storage multi-tenant, S3, Vectors e imgproxy | `architecture/storage-vectors-lifecycle.md` |
| conversão única de instalações anteriores | `architecture/shared-storage-migration.md` |
| módulos Lua, rewrites e cache de service key | `architecture/openresty-lua.md` |
| Logflare, Vector, fontes e acesso aos logs | `architecture/supabase-analytics.md` |
| JWT, UUID do tenant e replication slots | `09-autenticacao-multi-tenant-realtime.md` |
| fallback seguro do Postgres-Meta | `10-hardening-postgres-meta.md` |
| envelope encryption e rotação | `11-rotacao-cripto-conexoes.md` |
| chaves públicas opacas, slots, expiração opcional, migração e incidentes | `12-chaves-api-opacas.md` |
| disclosure de vulnerabilidades deste projeto | `../../SECURITY.md` |

## Regra para novas mudanças

Quando uma mudança alterar comportamento real do sistema:

1. atualize primeiro o documento canônico do assunto;
2. no `00-arquitetura.md`, altere somente a visão geral quando necessário;
3. mantenha `README.md` e `LEIAME.md` como resumos de onboarding, sem criar uma segunda especificação;
4. evite colar trechos grandes de código que mudam com frequência;
5. prefira explicar contratos, invariantes, fronteiras e estados;
6. use links para código apenas como referência de implementação;
7. mantenha `project UUID`, `tenant UUID` e `project ref` claramente separados;
8. não documente arquitetura antiga como fallback quando a migração é one-way e o runtime novo a rejeita.
