# Índice da documentação

Esta pasta contém a documentação técnica do `supabase-multitenant`.

A regra é simples: cada assunto deve ter uma fonte canônica. O `00-arquitetura.md` apresenta apenas a visão geral e aponta para documentos especializados. Detalhes operacionais ou de implementação não devem ser copiados para vários arquivos.

## Comece por aqui

1. [Arquitetura do sistema](00-arquitetura.md)
2. [Control plane](architecture/control-plane.md)
3. [Lifecycle dos projetos](architecture/project-lifecycle.md)
4. [Arquitetura OpenResty/Lua](architecture/openresty-lua.md)
5. [Supabase Analytics por projeto](architecture/supabase-analytics.md)
6. [Autenticação multi-tenant no Realtime](09-autenticacao-multi-tenant-realtime.md)

## Instalação e configuração

- [Setup com HTTPS](01-setup-https.md)
- [Limite de conexões do PostgreSQL](02-Como-aumentar-o-limite-conexoes-postgres.md)
- [Limite de conexões do Supavisor](03-Como-aumentar-o-limite-conexoes-pooler.md)
- [Limite de conexões do Realtime](04-Como-aumentar-o-limite-conexoes-realtime.md)
- [Setup de notificações](06-setup-notification.md)
- [Erro de CRLF no setup](08-erro-setup-crlf.md)

## Segurança

- [Gerenciamento de usuários no Authelia](07-gerenciamento-usuarios-authelia.md)
- [Hardening do Postgres-Meta global](10-hardening-postgres-meta.md)
- [Rotação de segredos e conexões do Postgres-Meta](11-rotacao-cripto-conexoes.md)

## Operação e troubleshooting

- [Principais erros](05-principais-erros.md)
- A visão atual de jobs, recovery, rename e deleção fica em [Lifecycle dos projetos](architecture/project-lifecycle.md).
- A visão atual de segredos, identidade, settings e colaboração fica em [Control plane](architecture/control-plane.md).

## Fontes canônicas

| Assunto | Documento canônico |
| --- | --- |
| visão macro e fronteiras | `00-arquitetura.md` |
| API Python, schema central e autorização | `architecture/control-plane.md` |
| criação, duplicação, rename, rotação e deleção | `architecture/project-lifecycle.md` |
| módulos Lua, rewrites e cache de service key | `architecture/openresty-lua.md` |
| Logflare, Vector, fontes e acesso aos logs | `architecture/supabase-analytics.md` |
| JWT, UUID do tenant e replication slots | `09-autenticacao-multi-tenant-realtime.md` |
| fallback seguro do Postgres-Meta | `10-hardening-postgres-meta.md` |
| envelope encryption e rotação | `11-rotacao-cripto-conexoes.md` |

## Regra para novas mudanças

Quando uma mudança alterar comportamento real do sistema:

1. atualize primeiro o documento canônico do assunto;
2. no `00-arquitetura.md`, altere somente a visão geral quando necessário;
3. evite colar trechos grandes de código que mudam com frequência;
4. prefira explicar contratos, invariantes, fronteiras e estados;
5. use links para código apenas como referência de implementação;
6. mantenha exemplos com `project UUID` e `project ref` claramente separados.
