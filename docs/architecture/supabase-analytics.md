# Supabase Analytics by project context

## Objective

The global stack runs Logflare as the Supabase Analytics backend and Vector as
the collector. The implementation follows Supabase's self-hosted single-tenant
mode but adapts container classification to this repository's multi-tenant
topology.

The old pipeline that wrote directly to `logs_db.public.logs` was removed from
the new setup. Logflare persists its metadata and tables in the `_analytics`
schema of the `_supabase` database.

## Components

- `supabase-analytics`: Logflare `v1.47.1`, built by the local Dockerfile with
  SQL adaptations in `servidor/volumes/analytics`;
- `supabase-vector-global`: `timberio/vector:0.53.0-alpine`;
- Fluent logging driver: sends each container's name, stream, and message to
  Vector's ingestion port without Docker API access;
- `supabase-studio`: queries Analytics through Studio's internal Nginx;
- Projects API: validates the `studio-nginx` identity, applies the allowlist,
  and injects the private credential used to talk to Logflare;
- global PostgreSQL: minimal Logflare backend in `_supabase._analytics`.

The Analytics container does not publish ports on the host. Logflare's internal
UI is also not exposed because self-hosted mode disables browser authentication.

## Secrets

`setup.sh` generates two different tokens, both at least 32 characters long:

- `LOGFLARE_PUBLIC_ACCESS_TOKEN`: ingestion by Vector only;
- `LOGFLARE_PRIVATE_ACCESS_TOKEN`: administrative queries made by the
  Projects API;
- `LOGFLARE_DB_ENCRYPTION_KEY`: Base64 32-byte key for sensitive columns
  maintained by Logflare.

Real tokens live server-side in `servidor/.analytics.env`, outside the root
`.env` inherited by project containers. The Studio process does not use the
private token as a credential: Compose overrides the variable required by
upstream with a non-secret value, and the server-side hook removes
`Authorization`, `X-API-KEY`, cookies, and identity headers before calling
Nginx.

Studio -> Nginx authentication uses a separate secret:

- `STUDIO_ANALYTICS_HMAC_SECRET`: known only by Studio's server-side process
  and Studio Nginx;
- signed identity: `studio-server`.

After validating this signature, Nginx removes the received HMAC headers and
creates a new signature with `STUDIO_GATEWAY_HMAC_SECRET`:

- signed identity on the second hop: `studio-nginx`;
- destination: Projects API.

The Projects API does not accept the caller's `Authorization` or `X-API-KEY`
for this route. It injects `LOGFLARE_PRIVATE_ACCESS_TOKEN` locally when
creating the request to `ANALYTICS_INTERNAL_URL`.

`STUDIO_ANALYTICS_HMAC_SECRET` must differ from
`STUDIO_GATEWAY_HMAC_SECRET` and `PROJECTS_API_HMAC_SECRET`. Nginx fails
closed at startup if the secret is missing or reused.

To rotate Logflare's encryption key, temporarily move the old key to
`LOGFLARE_DB_ENCRYPTION_KEY_RETIRED`, generate the new key, and restart
Analytics. Remove the retired key only after Logflare confirms the migration.

## Context, isolation, and authorization

The Analytics service and storage are global, but every query must be
contextualized by the selected project. Studio Nginx intercepts
`/api/platform/projects/<ref>/analytics/...` and requires the Authelia
`admin` group before forwarding the request to Studio's backend. The Lua
rewrite replaces the `default` used by self-hosted Studio with the
`project_ref` resolved from the tab context. Studio sends this value to the
Logflare endpoint as the `project` parameter, used by the native `logs.all`
CTEs to filter events. Project-only members and admins cannot query global
Logflare.

The technical route `/_internal/logflare/` does not depend on a browser
session. It is protected by a service HMAC before any gateway re-signing. A
direct request without the `studio-server` identity, with an invalid
signature, expired timestamp, or repeated nonce is rejected before reaching the
Projects API.

The guard accepts only the endpoints used by the Studio version fixed in this
repository:

- `GET /api/endpoints/query/<name>`;
- `GET|POST /api/backends`;
- `GET|PUT|DELETE /api/backends/<id>`;
- `GET /api/sources`;
- `POST /api/rules`.

Any other path or method combination returns an error. The guard also limits
queries to 16 KiB, headers to 64 entries/16 KiB, and bodies to 256 KiB;
mutations require `Content-Length` and `application/json`, and
`Transfer-Encoding` is not accepted at this boundary.

An exclusive internal Docker network connects PostgreSQL, Analytics, Vector, and
the server's Python API. Studio remains outside this network: its backend calls
the local Nginx, which forwards to the remote Python API, and only the API
accesses Logflare. Project containers remain outside the internal network.

Vector does not mount the Docker socket or query the Docker API. Services use
the `fluentd` logging driver with an asynchronous connection; the daemon sends
events to Vector's `fluent` source. The default bind is `127.0.0.1:24224` on
the server node.

Sources remain global and use the names expected by Logflare. For Auth,
PostgREST, and Nginx, Vector extracts the ref from the container suffix. For
global Storage, it parses upstream's structured JSON, validates `tenantId` as a
UUID, and also records request ID, operation, method, and path; an event
without a valid UUID remains global and is never assigned by approximation. For
shared PostgreSQL, the ref is extracted from the `_supabase_<project_ref>`
database in `log_line_prefix`. Therefore, a project query returns only its
dedicated containers and its database rows.

Logflare's PostgreSQL backend remains in `_supabase._analytics`; it is the
central event store and must not be confused with the application database.
Project database selection happens while classifying each log event, not by
switching Logflare's metadata connection per request.

## Forwarded sources

Vector uses the source names expected by Logs Explorer:

- `gotrue.logs.prod`;
- `postgREST.logs.prod`;
- `storage.logs.prod.2`;
- `realtime.logs.prod`;
- `deno-relay-logs`;
- `postgres.logs`;
- `cloudflare.logs.prod` for project Nginx instances and global gateways.

Auth, PostgREST, and Nginx use the container suffix. Storage uses the tenant
UUID from the structured event. The shared database uses the database name
recorded in the line prefix. Realtime uses a stable UUID `external_id`, and
Edge Functions, Supavisor, the internal API, and Postgres-Meta are also shared;
lines from these services that do not carry a verifiable ref remain classified
as global rather than being assigned to the wrong project.

Only new events receive per-project classification. Installations with history
already recorded as `project=default` must keep that history as legacy or run a
specific data migration before expecting old rows to appear in contextualized
queries.

## Operations

In a new installation, `tools/configure_studio_runtime.py`, called by setup,
generates `STUDIO_ANALYTICS_HMAC_SECRET` with the local Studio configuration.
Then start or recreate the stacks in server-then-Studio order:

```bash
cd servidor
docker compose --env-file .env up -d analytics vector

cd ../studio
docker compose --env-file .env up -d --build --force-recreate studio nginx
```

Useful checks:

```bash
docker compose --env-file servidor/.env -f servidor/docker-compose.yml ps analytics vector
docker logs --tail 100 supabase-analytics
docker logs --tail 100 supabase-vector-global
```

Healthchecks are internal; Analytics port `4000` and Vector port `9001` are
not published on the host.

## Upgrade existing installations

Before starting the version that requires HMAC on the internal Analytics route:

```bash
python3 tools/migrate_studio_analytics_hmac.py --dry-run
python3 tools/migrate_studio_analytics_hmac.py
```

The script generates the secret only when necessary, preserves explicit values,
rejects reuse of the other HMAC secrets, backs up `studio/.env`, and does not
print the secret. After migration, rebuild/restart Studio, Nginx, and Projects
API.

Older installations may retain the `logs_db` database and `vector_writer`
role. They are not deleted automatically because that would destroy legacy
history. After confirming that the new pipeline is healthy and old data need
not be retained, remove them manually with a prior backup.

## Limitations and production

- The Fluent port must remain limited to the host or administrative network. In
  split-node mode, publish it only between nodes and apply a firewall.
- The minimal backend uses the same observed PostgreSQL cluster. If the
  database fails, Analytics also fails; for critical production, use a
  separate PostgreSQL instance.
- Logflare retention and disk limits must be defined according to real load
  before enabling highly verbose logs.
- Logs may contain personal or operational data. Keep redaction in source
  services and do not expose the Logflare dashboard directly.

## Official references

- [Self-hosting with Docker](https://supabase.com/docs/guides/self-hosting/docker)
- [Self-hosted Analytics configuration](https://supabase.com/docs/guides/self-hosting/analytics/config)
- [Logflare self-hosting](https://docs.logflare.app/self-hosting/)
- [Official logs Compose](https://github.com/supabase/supabase/blob/master/docker/docker-compose.logs.yml)
- [Official Vector pipeline](https://github.com/supabase/supabase/blob/master/docker/volumes/logs/vector.yml)
- [Logflare runtime configuration](https://github.com/Logflare/logflare/blob/master/config/runtime.exs)
