# OpenResty/Lua architecture

Studio Nginx uses Lua in different phases of a request lifecycle. Files live in
`studio/nginx/lua` and are loaded through the `lua_package_path` defined in
`studio/nginx/nginx.conf`.

## Module organization

| Directory | Responsibility |
| --- | --- |
| `project_context/` | Project resolution from the tab URL and `X-Studio-Project-Ref` header, active ref, and context headers. |
| `security/` | Authentication, authorization, HMAC, service keys, and upload limits. |
| `studio_compat/` | Compatibility responses and endpoints expected by Supabase Studio. |
| `proxy_rewrites/` | URI, method, query-string, and payload translation before proxying. |
| `admin_api/` | Administrative operations, users, members, and Authelia integration. |
| `cache/` | Access to caches and databases used by Lua handlers. |
| `api/` | API handlers outside the previous domains, such as AI. |
| `init/` | Global and OpenResty-worker initialization. |
| `resty/` | Libraries compatible with the OpenResty namespace. |
| `utils/` | Small utilities without state or domain rules. |

Modules loaded with `require` use the full domain name, for example
`require("security.get_service_key")`. Files called directly by Nginx use the
absolute path under `/usr/local/openresty/lualib`.

## Request flow

1. `init/init.lua` validates at startup the Fernet key used to transport
   `service_role`.
2. `project_context/` resolves the ref from the URL (`request_uri`) and/or
   `X-Studio-Project-Ref` header and sets `ngx.var.project_ref`.
3. `security/` authenticates the user, restricts the route, and injects
   internal credentials when needed.
4. `proxy_rewrites/` adapts the Studio contract to the upstream contract.
5. The proxy forwards the request to Auth, REST, Storage, or PG Meta.
6. Response filters can adapt headers or payloads for Studio.

## Rewrites requiring care

### Analytics

`proxy_rewrites/analytics.lua` replaces `default` in the self-hosted path with
the `project_ref` resolved from the tab context before forwarding the request
to Studio. Studio's backend reuses this segment as the `project` parameter
when querying Logflare. Without this rewrite, every dashboard would query the
single-tenant `default` context regardless of the selected project.

### PG Meta

`proxy_rewrites/pg_meta.lua` recursively converts fields from camelCase to
snake_case. It also turns the `id` argument into a path segment because Studio
and postgres-meta represent individual resources differently.

### Storage

`proxy_rewrites/storage.lua` adapts bucket, listing, removal, signing, and
object-move payloads. The move route carries the bucket in the Studio path, but
the upstream expects `bucketId` in the body. Bucket updates are also converted
from `PATCH` to `PUT`.

File uploads from Storage Explorer are always resumable (tus) and use
`/storage/v1/upload/resumable` on Studio's own origin, with the tab ref in
`X-Studio-Project-Ref`. The route injects the service key, applies the
project's `FILE_SIZE_LIMIT` through `security/storage_upload_limit.lua`, and
streams the chunks (`proxy_request_buffering off`). Storage builds the create
`Location` from the project gateway's
`X-Forwarded-Host`/`X-Forwarded-Prefix`, which points to the tenant's
internal host; `proxy_rewrites/storage_resumable_location.lua` reanchors this
header at Studio's public origin so subsequent `PATCH` requests return
through this gateway. The project gateway performs the equivalent step with
`proxy_redirect`, publishing the tenant's public URL to clients that speak
directly to the API.

### Auth

`proxy_rewrites/auth.lua` translates Studio administrative routes to GoTrue
paths and injects the project service key. Methods or paths outside the known
list are rejected with HTTP 400.

### Administrative groups

Authelia's `Remote-Groups` header is treated as a CSV list, normalized with
trim and lowercase. Comparison is exact against `ADMIN_GROUPS` (default:
`admin`); multiple administrative groups can be configured as
`ADMIN_GROUPS=admin,superadmins`. Unexpected formats fail closed and are
recorded in the Nginx log.

### Avatars from the authenticated directory

`GET /api/users/{uuid}/avatar` is the canonical read route. Any user with an
active session and administrative profile can read another active account's
avatar, even without a project in common, because member selection queries the
full administrative directory. The UUID identifies the object; the session and
active state authorize the read. A malformed UUID receives 400, and a missing
or inactive account receives 404. `/api/user/me/avatar` accepts only the
current user's upload and removal; there is no second read route.

`admin_api/user_avatar_handler.lua` contains only routing, authorization,
storage, and profile synchronization. `admin_api/avatar_processor.lua`
contains reading, limits, and all libvips processing.

The Lua processor limits the body to 2 MB, validates PNG/JPEG/WebP, and uses
`ngx.pipe` with a closed argv to call `vipsheader` and `vipsthumbnail`,
without a shell. The image is fully decoded, pixel-limited, resized,
auto-oriented, and re-encoded as WebP without EXIF, ICC, or XMP. Animated
avatars are rejected. The global subprocess limit
(`AVATAR_PROCESS_MAX_CONCURRENCY`) prevents uploads from consuming all
capacity; `VIPS_CONCURRENCY` limits each process's threads.
`worker_processes auto` keeps HTTP workers per CPU — there is no Nginx worker
reserved per route — and the pipe does not block the event loop. Reads accept
only WebP accompanied by the current normalization marker; old or incomplete
files fail closed with 415 and are not converted on demand.

### Outbound TLS

Lua HTTPS calls go through `utils.outbound_tls`: public endpoints always
validate the certificate and hostname; internal endpoints respect
`SERVICE_KEY_VERIFY_TLS`, enabled by default. The entrypoint refuses to start
with `SERVER_DOMAIN=https://...` and validation disabled. The trust store
combines system CAs with the file mounted through `STUDIO_CA_CERT_PATH`; the
Node backend receives the same CA through `NODE_EXTRA_CA_CERTS`. The local
certificate includes the `DNS:nginx` SAN used by internal Studio calls.
Certificate, hostname, or CA failure is terminal for the request, with no
insecure fallback.

Installations predating this rule must regenerate only configuration and the
certificate (secrets remain) before starting the containers:

```bash
python tools/configure_studio_runtime.py \
  --studio-origin https://studio.exemplo.com:9091 \
  --force
```

The entrypoint checks the `DNS:nginx` SAN and refuses to start with an
incompatible legacy certificate.

## Conventions

- Four-space indentation and no tabs.
- `require("module")` with parentheses and the full domain name.
- Variables in `snake_case`; avoid generic names such as `get`, `data`, and
  `obj`.
- Declare dependencies once at the beginning of the module unless there is a
  reason for late loading.
- Keep short handlers across multiple lines; minified files are not accepted.
- Rewrites must have a short comment explaining incompatibilities between the
  public contract and the upstream.
- Never log cookies, HMACs, JWTs, service keys, or bodies that may contain
  secrets.

## Service-role cache

`security/get_service_key.lua` stores the decrypted key in
`lua_shared_dict service_keys`. Entries use their own namespace and carry the
`project_key_version` persisted in the `projects` table.

After a successful rotation, the API increments the version in the same
transaction that persists the keys and calls:

`POST /internal/cache/service-key/{project_ref}`

The endpoint requires `internal-hmac-v1` with
`X-Internal-Service: projects-api`, removes the previous key, and publishes the
new minimum version to the shared dictionary. Invalidation affects all
OpenResty workers without an Nginx restart or reload.

Before using an entry, the cache queries the canonical version at
`GET /api/projects/internal/key-version/{project_ref}`. When the persisted
version is greater, the old key is discarded and reloaded. If the query fails,
the module returns an empty key and the request fails closed, even if a local
entry is still within its TTL.

The timings are configurable:

- `SERVICE_KEY_CACHE_TTL_SECONDS`: key TTL; default 60 seconds;
- `SERVICE_KEY_FETCH_ERROR_TTL_SECONDS`: short backoff after an `enc-key`
  failure; default 2 seconds (capped at 10 seconds).

In normal operation, consistency is immediate after notification. If all three
invalidation attempts fail, the job ends with
`service_key_cache_invalidation_failed`. If the version API is unavailable,
the service key is not used.

Counters for `hit`, `miss`, `version_reload`, `invalidation`,
`fetch_error`, `fetch_error_backoff`, `stale_fetch`, and
`version_check_error` live in `lua_shared_dict service_key_metrics` and can
be queried with the internal token at
`GET /internal/cache/service-key-metrics`.

The required version is monotonic across workers. An `enc-key` response with a
version older than the current invalidation is discarded instead of putting the
old key back into the cache.

### Credentials and config token

`service_role` is the tenant's administrative credential. It is generated from
`JWT_SECRET_PROJETO`, stored encrypted in the control plane, and must never be
delivered to the browser. The gateway obtains it through the internal
`enc-key` endpoint, decrypts it with `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`, and
injects `apikey` only after user authentication and authorization.

`CONFIG_TOKEN_PROJETO` has a different scope: it is a secret shared among
project members to query the tenant Nginx `/config`. It must not be accepted
as `apikey`, `Authorization`, or a replacement for `service_role`.
Anon/service-role rotation preserves this token.

If PG Meta responds with `apikey administrativa ausente`, verify the
installation without printing secrets:

```bash
bash servidor/verify_key_config.sh
```

On older installations, especially confirm that
`STUDIO_SERVICE_KEY_ENCRYPTION_KEY` is a valid Fernet key and identical in
`servidor/.env` and `studio/.env`. After fixing the files, recreate the
`projects-api` and `nginx` containers; merely restarting a container without
recreating it may keep the old environment.

## Validating changes

When moving a module, update both the `require(...)` calls and all
`*_by_lua_file` directives in `nginx.conf`. Before deployment:

1. confirm that every file referenced by Nginx exists;
2. validate every file's syntax with `luac -p` or equivalent;
3. run tab-context and rewrite tests;
4. load the configuration with `nginx -t` in the Studio container;
5. test at least Auth, REST, Storage, and PG Meta with a real project.
