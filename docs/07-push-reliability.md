# Push reliability and tenant setup

Push delivery combines a durable outbox in each tenant database with a Python
worker and the Studio gateway. Every HTTP attempt signs the exact request bytes,
path/query and a fresh nonce using the HMAC `push-v2` contract.
Header arrays are rejected; nonce retention covers the full timestamp validity
window, including allowed future clock skew. The gateway verifies outbound TLS
through `utils.outbound_tls.apply_public`.

## New tenant and existing tenant

A **new** tenant needs its own push_tokens and notifications. Run
`psql -X -f servidor/sql/push/setup.sql` against its database after Supabase Auth
is installed. This entrypoint creates tables/trigger/RLS via 00_base.sql, then
applies the canonical delivery migration. In a SQL editor, execute those two files
separately, in that order. The wrapper's \ir is psql-specific.

An **existing** push tenant runs only
`servidor/migrations/push/20261014_01_delivery_fencing.sql`. That migration does
not create the base tables. It adds delivery state, notification claims and token
generations while preserving existing records. The worker never executes DDL;
apply this migration separately to each enabled tenant database.

## Delivery behavior

Structured FCM categories; delete only explicit FcmError/UNREGISTERED (HTTP404)
and only the same token ID/value/generation/user in that tenant's connection.
A trigger changes generation on every UPDATE, including same-token RPC/upsert.
No deletion on invalid payload, mismatch, OAuth, timeout, network or transient HTTP.
No inactivity purge, validate_only requests, per-tenant Firebase projects or client
updates. Legacy deliveries without a generation snapshot cannot delete token rows.

UUID claims, expiring leases and heartbeat fence database writes. HTTP is outside
transactions. Snapshot recipients once; preserve confirmed successes and retry only
recoverable deliveries. Existing notification status strings remain unchanged.
No-token state is terminal; partial status is final only after no recovery remains.
Retry is persisted. Defaults are eight attempts per device, exponential jitter
with a 60-second base and a 3600-second maximum, and a supported Retry-After of up
to 86400 seconds. Retry-After is a lower bound. An excessive Retry-After becomes
terminal rather than retrying too early. Auth/config errors need intervention.

OAuth uses shared cache and resty.lock, expiry margin, identity/key fingerprint,
exception-safe unlock and failure cooldown. Cache hits do not generate JWTs.
Successful operation cache/lock includes tenant and payload. Default concurrency
is four HTTP calls per tenant and 32 globally, with reusable HTTP connections and
a single sequential asyncpg connection per tenant.
Bounded tenant sessions rotate fairly beyond the connection cap. LISTEN/NOTIFY,
dynamic discovery, removal and reconnection remain intact. Logs avoid raw secrets.

## Deployment and rollback

Back up and inspect each tenant; stop ALL old workers; apply the additive migration;
check HTTPS/CA/SAN and HMAC secret; build gateway/worker images; run openresty -t
with real mounts; start a canary before expanding. Keep the worker opt-in and its
read-only/no-new-privileges/cap_drop settings. Configure PUSH_API_URL with the
Studio HTTPS origin, using STUDIO_HTTPS_PORT (default 9091) and the path
`/api/internal/push`.

Rollback: stop new workers, restore previous images/config and keep additive schema
and delivery outcomes. Do not reset successful deliveries or delete historical data.
Old workers recover abandoned leases but bring back the old limitations.

## Reproducible validation and limits

The CI builds the gateway and worker from their production Dockerfiles and runs
`bash tests/push/run_local.sh`. The runner rejects failed, empty or skipped Python
test runs. For a manual run, use a checkout with full Git history and execute
these commands from the repository root:

```bash
docker build -t push-gateway:test -f studio/Dockerfile studio
docker build -t push-worker:test -f servidor/api-internal/Dockerfile servidor
docker pull postgres:15
PUSH_NGINX_IMAGE=push-gateway:test \
PUSH_PYTHON_IMAGE=push-worker:test \
  bash tests/push/run_local.sh
```

The runner creates temporary PostgreSQL/OpenResty containers on an internal
network, mocks Google and uses real TLS/RSA/JWT/HMAC. Tests include
multitenant isolation, concurrent claims, heartbeat, real DB reconnect, token renewal,
partial retry, OAuth single-flight, auth/replay and actual Lua TLS verification.
Git history is used for the OAuth regression comparison against the previous
gateway implementation. No Firebase credential or device traffic is required.

Production Firebase credentials, quotas, device delivery and prolonged load are
not validated with mocks. Delivery is at least once: a lost FCM response, expired
or capacity-limited success cache, process crash or gateway restart can duplicate.
Fencing protects DB state, not an already accepted external send.
