# Arquitetura OpenResty/Lua

O Nginx do Studio usa Lua em fases diferentes do ciclo de uma requisição. Os
arquivos ficam em `studio/nginx/lua` e são carregados pelo `lua_package_path`
definido em `studio/nginx/nginx.conf`.

## Organização dos módulos

| Diretório | Responsabilidade |
| --- | --- |
| `project_context/` | Seleção do projeto, cookie assinado, referência ativa e headers de contexto. |
| `security/` | Autenticação, autorização, HMAC, service keys e limites de upload. |
| `studio_compat/` | Respostas e endpoints de compatibilidade esperados pelo Supabase Studio. |
| `proxy_rewrites/` | Tradução de URI, método, query string e payload antes do proxy. |
| `admin_api/` | Operações administrativas, usuários, membros e integração com Authelia. |
| `cache/` | Acesso aos caches e bancos usados pelos handlers Lua. |
| `api/` | Handlers de API que não pertencem aos domínios anteriores, como IA. |
| `init/` | Inicialização global e de workers do OpenResty. |
| `resty/` | Bibliotecas compatíveis com o namespace OpenResty. |
| `utils/` | Utilitários pequenos sem estado ou regra de domínio. |

Módulos carregados com `require` usam o nome completo do domínio, por exemplo
`require("security.get_service_key")`. Arquivos chamados diretamente pelo
Nginx usam o caminho absoluto sob `/usr/local/openresty/lualib`.

## Fluxo de uma requisição

1. `init/init.lua` valida o segredo usado para assinar o cookie de projeto.
2. `project_context/` valida o cookie e determina `ngx.var.project_ref`.
3. `security/` autentica o usuário, restringe a rota e injeta credenciais
   internas quando necessário.
4. `proxy_rewrites/` adapta o contrato do Studio ao contrato do upstream.
5. O proxy encaminha a requisição para Auth, REST, Storage ou PG Meta.
6. Filtros de resposta podem adaptar headers ou payloads para o Studio.

## Rewrites que exigem cuidado

### PG Meta

`proxy_rewrites/pg_meta.lua` converte campos recursivamente de camelCase para
snake_case. Também transforma o argumento `id` em um segmento do path porque
o Studio e o postgres-meta representam recursos individuais de formas
diferentes.

### Storage

`proxy_rewrites/storage.lua` adapta payloads de bucket, listagem, remoção,
assinatura e movimentação de objetos. A rota de movimentação carrega o bucket
no path do Studio, mas o upstream espera `bucketId` no corpo. Atualizações de
bucket também são convertidas de `PATCH` para `PUT`.

### Auth

`proxy_rewrites/auth.lua` traduz as rotas administrativas do Studio para os
paths do GoTrue e injeta a service key do projeto. Métodos ou paths fora da
lista conhecida são rejeitados com HTTP 400.

## Convenções

- Indentação de quatro espaços e nenhuma tabulação.
- `require("modulo")` com parênteses e nome completo do domínio.
- Variáveis em `snake_case`; evite nomes genéricos como `get`, `data` e `obj`.
- Dependências devem ser declaradas uma única vez no início do módulo quando
  não houver motivo para carregamento tardio.
- Handlers curtos permanecem em múltiplas linhas; arquivos minificados não são
  aceitos.
- Rewrites devem ter um comentário curto explicando incompatibilidades entre
  o contrato público e o upstream.
- Nunca registrar cookies, HMACs, JWTs, service keys ou corpos que possam
  conter segredos.

## Validação de mudanças

Ao mover um módulo, atualize tanto os `require(...)` quanto todas as diretivas
`*_by_lua_file` do `nginx.conf`. Antes do deploy:

1. confirme que todo arquivo referenciado pelo Nginx existe;
2. valide a sintaxe de todos os arquivos com `luac -p` ou equivalente;
3. execute os testes de cookies e rewrites;
4. carregue a configuração com `nginx -t` no container do Studio;
5. teste ao menos Auth, REST, Storage e PG Meta com um projeto real.
