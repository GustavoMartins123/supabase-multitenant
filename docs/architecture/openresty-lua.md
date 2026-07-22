# Arquitetura OpenResty/Lua

O Nginx do Studio usa Lua em fases diferentes do ciclo de uma requisição. Os
arquivos ficam em `studio/nginx/lua` e são carregados pelo `lua_package_path`
definido em `studio/nginx/nginx.conf`.

## Organização dos módulos

| Diretório | Responsabilidade |
| --- | --- |
| `project_context/` | Resolução do projeto pela URL da aba e pelo header `X-Studio-Project-Ref`, referência ativa e headers de contexto. |
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

1. `init/init.lua` valida, na inicialização, a chave Fernet usada para
   transportar a `service_role`.
2. `project_context/` resolve o ref pela URL (`request_uri`) e/ou pelo header
   `X-Studio-Project-Ref` e determina `ngx.var.project_ref`.
3. `security/` autentica o usuário, restringe a rota e injeta credenciais
   internas quando necessário.
4. `proxy_rewrites/` adapta o contrato do Studio ao contrato do upstream.
5. O proxy encaminha a requisição para Auth, REST, Storage ou PG Meta.
6. Filtros de resposta podem adaptar headers ou payloads para o Studio.

## Rewrites que exigem cuidado

### Analytics

`proxy_rewrites/analytics.lua` troca o `default` do path self-hosted pelo
`project_ref` resolvido pelo contexto da aba antes de encaminhar a requisição
ao Studio. O
backend do Studio reutiliza esse segmento como parâmetro `project` ao consultar
o Logflare. Sem esse rewrite, todos os painéis consultariam o contexto
single-tenant `default`, independentemente do projeto selecionado.

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

### Grupos administrativos

O header `Remote-Groups` do Authelia é tratado como uma lista CSV, normalizada
com trim e lowercase. A comparação é exata contra `ADMIN_GROUPS` (padrão:
`admin`); múltiplos grupos administrativos podem ser configurados como
`ADMIN_GROUPS=admin,superadmins`. Formatos inesperados falham fechados e são
registrados no log do Nginx.

### Avatares do diretório autenticado

`GET /api/users/{uuid}/avatar` é a rota canônica de leitura. Qualquer usuário
com sessão e perfil administrativo ativos pode ler o avatar de outra conta
ativa, mesmo sem projeto em comum, pois a seleção de membros consulta o
diretório administrativo completo. UUID identifica o objeto; a sessão e o
estado ativo autorizam a leitura. UUID malformado recebe 400 e conta inexistente
ou inativa recebe 404. `/api/user/me/avatar` aceita apenas upload e remoção
próprios; não existe uma segunda rota de leitura.

`admin_api/user_avatar_handler.lua` mantém apenas rota, autorização, armazenamento
e sincronização de perfil. `admin_api/avatar_processor.lua` concentra leitura,
limites e todo o processamento libvips;

O processador Lua limita o corpo a 2 MB, valida PNG/JPEG/WebP e usa `ngx.pipe` com
argv fechado para chamar `vipsheader` e `vipsthumbnail`, sem shell. A imagem é
decodificada por completo, limitada por pixels, reduzida, auto-orientada e
reencodificada como WebP sem EXIF, ICC ou XMP. Avatares animados são rejeitados.
O limite global de subprocessos (`AVATAR_PROCESS_MAX_CONCURRENCY`) impede que
uploads ocupem toda a capacidade; `VIPS_CONCURRENCY` limita as threads de cada
processo. `worker_processes auto` mantém os workers HTTP por CPU — não existe
worker Nginx reservado por rota — e o pipe não bloqueia o event loop. A leitura
aceita somente WebP acompanhado do marcador de normalização atual; arquivos
antigos ou incompletos falham fechados com 415 e não são convertidos sob demanda.

### TLS de saídas

Chamadas HTTPS Lua passam por `utils.outbound_tls`: endpoints públicos sempre
validam certificado e hostname; endpoints internos respeitam
`SERVICE_KEY_VERIFY_TLS`, cujo padrão é ativo. O entrypoint recusa iniciar com
`SERVER_DOMAIN=https://...` e validação desabilitada. O trust store combina as
CAs do sistema com o arquivo montado por `STUDIO_CA_CERT_PATH`; o backend Node
recebe a mesma CA via `NODE_EXTRA_CA_CERTS`. O certificado local inclui o SAN
`DNS:nginx`, usado nas chamadas internas do Studio. Falha de certificado,
hostname ou CA é terminal para a requisição, sem fallback inseguro.

Instalações anteriores a essa regra devem regenerar somente configuração e
certificado (os secrets permanecem) antes de subir os containers:

```bash
python tools/configure_studio_runtime.py \
  --studio-origin https://studio.exemplo.com:9091 \
  --force
```

O entrypoint verifica o SAN `DNS:nginx` e recusa iniciar com um certificado
legado incompatível.

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
  de versão; padrão de 5 segundos;
- `SERVICE_KEY_FETCH_ERROR_TTL_SECONDS`: backoff curto depois de uma falha no
  `enc-key`; padrão de 2 segundos (limitado a 10 segundos).

Em operação normal, a consistência é imediata após a notificação. Se as três
tentativas de invalidação falharem, o job termina com
`service_key_cache_invalidation_failed`; o fallback de versão limita a janela
usual de chave antiga ao intervalo de verificação. Se tanto a notificação
quanto a API de versão estiverem indisponíveis, uma entrada existente pode ser
usada até seu TTL expirar.

Contadores de `hit`, `miss`, `version_reload`, `invalidation`, `fetch_error`,
`fetch_error_backoff`, `stale_fetch` e `version_check_error` ficam no
`lua_shared_dict service_key_metrics` e podem ser consultados, com o token
interno, em `GET /internal/cache/service-key-metrics`.

A versão requerida é monotônica entre workers. Uma resposta `enc-key` com
versão anterior à invalidação corrente é descartada, em vez de recolocar a
chave antiga no cache.

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
3. execute os testes de contexto por aba e rewrites;
4. carregue a configuração com `nginx -t` no container do Studio;
5. teste ao menos Auth, REST, Storage e PG Meta com um projeto real.
