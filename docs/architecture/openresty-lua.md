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

## Cache de service role

`security/get_service_key.lua` armazena a chave descriptografada no
`lua_shared_dict service_keys`. As entradas usam namespace próprio e carregam
o `project_key_version` persistido na tabela `projects`.

Após uma rotação bem-sucedida, a API incrementa a versão na mesma transação
que persiste as chaves e chama:

`POST /internal/cache/service-key/{project_ref}`

O endpoint exige `X-Shared-Token` e `X-Internal-Service: projects-api`, remove
a chave anterior e publica a nova versão mínima no shared dictionary. A
invalidação afeta todos os workers do OpenResty sem restart ou reload do Nginx.

Antes de usar uma entrada, o cache compara sua versão com a versão requerida.
Como proteção para perda da notificação ativa, a versão do banco é consultada
periodicamente em `GET /api/projects/internal/key-version/{project_ref}`.
Quando a versão persistida for maior, a chave antiga é descartada e recarregada.

Os tempos são configuráveis:

- `SERVICE_KEY_CACHE_TTL_SECONDS`: TTL da chave; padrão de 60 segundos;
- `SERVICE_KEY_VERSION_CHECK_TTL_SECONDS`: intervalo máximo entre verificações
  de versão; padrão de 5 segundos.

Em operação normal, a consistência é imediata após a notificação. Se as três
tentativas de invalidação falharem, o job termina com
`service_key_cache_invalidation_failed`; o fallback de versão limita a janela
usual de chave antiga ao intervalo de verificação. Se tanto a notificação
quanto a API de versão estiverem indisponíveis, uma entrada existente pode ser
usada até seu TTL expirar.

Contadores de `hit`, `miss`, `version_reload`, `invalidation`, `fetch_error` e
`version_check_error` ficam no `lua_shared_dict service_key_metrics` e podem
ser consultados, com o token interno, em
`GET /internal/cache/service-key-metrics`.

### Credenciais e config token

`service_role` é a credencial administrativa do tenant. Ela é gerada a partir
de `JWT_SECRET_PROJETO`, armazenada criptografada no control plane e nunca deve
ser entregue ao navegador. O gateway a obtém pelo endpoint interno `enc-key`,
descriptografa com `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` e injeta `apikey` apenas
depois da autenticação e da autorização do usuário.

`CONFIG_TOKEN_PROJETO` tem outro escopo: é um segredo compartilhado entre os
membros do projeto para consultar o `/config` do Nginx do tenant. Ele não pode
ser aceito como `apikey`, `Authorization` ou substituto da `service_role`.
Rotação de anon/service role preserva esse token.

Se PG Meta responder `apikey administrativa ausente`, valide a instalação sem
imprimir segredos:

```bash
bash servidor/verify_key_config.sh
```

Em instalações antigas, confirme especialmente que
`STUDIO_SERVICE_KEY_ENCRYPTION_KEY` é uma chave Fernet válida e idêntica em
`servidor/.env` e `studio/.env`. Depois de corrigir os arquivos, recrie os
containers `projects-api` e `nginx`; apenas reiniciar um container sem recriá-lo
pode manter o ambiente antigo.

## Validação de mudanças

Ao mover um módulo, atualize tanto os `require(...)` quanto todas as diretivas
`*_by_lua_file` do `nginx.conf`. Antes do deploy:

1. confirme que todo arquivo referenciado pelo Nginx existe;
2. valide a sintaxe de todos os arquivos com `luac -p` ou equivalente;
3. execute os testes de cookies e rewrites;
4. carregue a configuração com `nginx -t` no container do Studio;
5. teste ao menos Auth, REST, Storage e PG Meta com um projeto real.
