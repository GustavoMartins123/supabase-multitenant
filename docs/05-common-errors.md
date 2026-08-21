# Common errors and diagnosis

This document is a short runbook for common failures.

Architecture, lifecycle flows, and cache behavior are not repeated here. When diagnosis depends on these topics, use the canonical sources:

- [System architecture](00-architecture.md)
- [Control plane](architecture/control-plane.md)
- [Project lifecycle](architecture/project-lifecycle.md)
- [OpenResty/Lua](architecture/openresty-lua.md)
- [Multi-tenant Realtime](09-multi-tenant-realtime-authentication.md)

## Before changing anything

Collect first:

```bash
docker ps -a
docker network inspect rede-supabase
docker logs projects-api --tail 200
docker logs nginx --tail 200
docker logs traefik-traefik-1 --tail 200
```

For a specific project:

```bash
docker ps -a --filter "name=<project_ref>"
cd servidor/projects/<project_ref>
docker compose --env-file ../../.env --env-file .env ps
```

Do not manually remove a database, tenant, slot, or directory before identifying the failed stage. Lifecycle operations distribute state across PostgreSQL, Docker, Realtime, Supavisor, and Studio.

## 1. `502 Bad Gateway` when accessing a project

### Check the Nginx container

```bash
docker ps -a --filter "name=supabase-nginx-<project_ref>"
docker logs supabase-nginx-<project_ref> --tail 200
```

### Check the Traefik route

```bash
docker logs traefik-traefik-1 --tail 200 | grep -F '<project_ref>'
```

### Check the network

```bash
docker network inspect rede-supabase
docker inspect supabase-nginx-<project_ref> --format '{{json .NetworkSettings.Networks}}'
```

If the project exists in the control plane but containers are missing, prefer the recreate/start action through Studio or the Projects API. Starting Compose manually can hide an incomplete job.

## 2. Created or duplicated project does not appear in Studio

Query the job:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, project, action, status, progress, current_step, error_code, message
FROM jobs
WHERE project = '<project_ref>'
ORDER BY created_at DESC
LIMIT 5;
"
```

Confirm the project:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT id, name, display_name, owner_id, project_key_version
FROM projects
WHERE name = '<project_ref>';
"
```

Do not write `anon_key`, `service_role`, or `config_token` manually. Persisted values use envelope encryption and must be saved through the API flow.

## 3. Job remains `queued` or `running`

At startup, the API attempts recovery only for actions known to be safe.

Query the details:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, action, status, current_step, progress,
       is_idempotent, retryable, retry_of, attempt,
       error_code, stdout_tail, stderr_tail
FROM jobs
WHERE job_id = '<job_uuid>';
"
```

Interpretation:

- `queued`: it may still be waiting in the project queue;
- `running`: confirm that `projects-api` is still executing;
- `failed` with manual review: the API was restarted during a non-idempotent operation;
- `retryable = true`: use the retry endpoint/UI instead of repeating scripts manually.

## 4. Error during rename

Rename may change:

- directory;
- database;
- containers;
- Supavisor tenant;
- Realtime main slot;
- Traefik route;
- Studio snippets.

Query the history:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT job_id, old_name, new_name, status, error,
       created_at, completed_at
FROM project_name_history
ORDER BY created_at DESC
LIMIT 20;
"
```

The UUID and Realtime `external_id` must not change.

If the project was renamed but snippets did not appear, check the job warning and logs:

```bash
docker logs projects-api --tail 200 | grep -i snippet
docker logs nginx --tail 200 | grep -i snippet
```

Snippet migration failure is best-effort and does not invalidate a completed rename.

## 5. Key rotated, but Studio uses the old key

The current cache is versioned. Rotation must:

1. update the secrets;
2. increment `project_key_version`;
3. call active invalidation in OpenResty;
4. require the canonical version before each service-key use.

Query the version:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT name, project_key_version
FROM projects
WHERE name = '<project_ref>';
"
```

Check the logs:

```bash
docker logs projects-api --tail 200 | grep -i 'service.key\|cache'
docker logs nginx --tail 200 | grep -i 'service.key\|cache'
```

The cache does not use the local key when the version query fails. Restarting
Nginx clears the cache, but does not fix the unavailable dependency and is not
the normal consistency mechanism. Validate:

- `STUDIO_CACHE_INVALIDATION_URL`;
- `STUDIO_GATEWAY_HMAC_SECRET` and `PROJECTS_API_HMAC_SECRET` synchronized on both sides and distinct from each other;
- `X-Internal-Service: projects-api`;
- connectivity between Projects API and Studio;
- key-version endpoint.

If `automatic_key_rotation_blocked_at` is populated, fix the recorded error
and use **Resume automatic rotation** in Studio. Do not clear the field
directly in the database: resumption is audited and triggers reconciliation.

Details: [OpenResty/Lua architecture](architecture/openresty-lua.md).

## 6. Realtime returns `403`

First confirm the identifiers:

- Realtime `external_id`: project UUID;
- JWT issuer: same UUID;
- database and main slot: based on project ref;
- WebSocket Host: `<project_uuid>.localhost`.

Query the tenant:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT external_id
FROM _realtime.tenants
WHERE external_id = '<project_uuid>';
"
```

When a request identifies a tenant, failure of the tenant-specific JWT does not fall back to the global secret. The `403` may indicate:

- issuer different from the UUID;
- missing tenant;
- JWT signed with another secret;
- Nginx injecting the old/incorrect Host;
- invalid API key before the WebSocket proxy.

Details: [Multi-tenant Realtime](09-multi-tenant-realtime-authentication.md).

## 7. Active or stuck replication slot

List the slots:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT slot_name, database, active, active_pid
FROM pg_replication_slots
ORDER BY slot_name;
"
```

There are two relevant formats:

```text
supabase_realtime_replication_slot_<project_ref>
supabase_realtime_messages_replication_slot_<hash_do_project_uuid>
```

Do not search for the temporary slot only by project name; it uses a UUID hash.

During deletion, the Projects API removes the tenant/pools, drains connections, and validates reconnections before removing the database. Prefer fixing and retrying the deletion job.

For manual intervention, confirm that the project is not in use and terminate only the PID associated with the correct slot:

```sql
SELECT pg_terminate_backend(active_pid)
FROM pg_replication_slots
WHERE slot_name = '<slot_exato>'
  AND active_pid IS NOT NULL;
```

Avoid pausing global Realtime because it affects all tenants.

## 8. Database cannot be removed

List the connections:

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT pid, usename, application_name, client_addr, state
FROM pg_stat_activity
WHERE datname = '_supabase_<project_ref>';
"
```

If new connections reappear, check the tenant and Supavisor pools before running `DROP DATABASE`.

Current deletion intentionally fails when the pooler continues reconnecting. This preserves the database instead of producing a partial removal.

Details: [Project lifecycle](architecture/project-lifecycle.md#deletion).

## 9. `too many clients already`

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "
SELECT count(*) FROM pg_stat_activity;
SHOW max_connections;
"
```

Group by database and application:

```sql
SELECT datname, application_name, state, count(*)
FROM pg_stat_activity
GROUP BY datname, application_name, state
ORDER BY count(*) DESC;
```

Before increasing `max_connections`, validate:

- Supavisor pool size;
- client limit per tenant;
- PostgREST pool;
- services in a reconnection loop;
- incomplete delete/rename jobs.

Guides:

- [PostgreSQL](02-postgresql-connection-limit.md)
- [Supavisor](03-pooler-connection-limit.md)
- [Realtime](04-realtime-connection-limit.md)

## 10. Storage broken after duplication

Confirm whether duplication was `schema-only` or `with-data`.

In data mode, validate:

- records in `storage.objects`;
- files in the clone's `servidor/volumes/storage/objects/<tenant_uuid>`, never
  in the source namespace;
- ownership and permissions;
- extended attributes when used by the current Storage version;
- Auth and Storage migration history.

Also confirm that the clone received its own tenant and SigV4 credential and
that Vector's physical tables were reidentified. Do not copy only the database
and expect physical objects to appear.

## 11. User cannot log in to Studio

Check:

```bash
docker logs authelia --tail 200
docker logs nginx --tail 200
```

Confirm in the Authelia file:

- user not disabled;
- `active` group;
- valid Argon2id hash;
- valid YAML syntax;
- certificate still valid.

Control-plane identity is synchronized after authentication. If login works but the user receives access denied, query `users`, `user_groups`, and synchronization logs.

Details: [Authelia user management](07-authelia-user-management.md).

## 12. Postgres-Meta fails or returns the wrong database

Run validation without printing secrets:

```bash
bash servidor/verify_key_config.sh
```

Confirm:

- `PG_META_CRYPTO_KEY` is the same in the API and Postgres-Meta;
- `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` is the same in the API and Studio;
- `PG_META_INTERNAL_URL` points to an allowed host;
- fallback uses `meta_trap` and `meta_guest`;
- project membership and service role are valid.

Guides:

- [Postgres-Meta hardening](10-postgres-meta-hardening.md)
- [Secret and connection rotation](11-project-secret-and-connection-rotation.md)

## Useful commands

### Global logs

```bash
docker logs projects-api --tail 200 -f
docker logs nginx --tail 200 -f
docker logs traefik-traefik-1 --tail 200 -f
docker logs realtime-dev.supabase-realtime --tail 200 -f
docker logs supabase-pooler --tail 200 -f
docker logs supabase-db --tail 200 -f
```

### Control-plane state

```sql
SELECT id, name, owner_id, project_key_version FROM projects ORDER BY name;
SELECT job_id, project, action, status, current_step FROM jobs ORDER BY created_at DESC;
SELECT * FROM project_name_history ORDER BY created_at DESC;
```

### Network

```bash
docker network inspect rede-supabase
docker inspect <container> --format '{{json .NetworkSettings.Networks}}'
```

## When opening an issue

Include:

- version/commit used;
- one- or two-machine topology;
- operation performed;
- anonymized `project_ref`, when necessary;
- job stage and error code;
- logs without JWTs, cookies, HMACs, passwords, or connection strings;
- container and network state;
- reproduction steps.
