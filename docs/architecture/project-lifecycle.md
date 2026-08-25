# Project lifecycle

The lifecycle is orchestrated by the Projects API, but physical execution (Docker and the scripts in `servidor/generateProject/`) happens on the [host-agent](host-agent.md): the API writes the signed intent to the database and waits for the agent to execute the closed command.

The Vector steps embedded in create, duplicate, rename, and restore — S3 buckets/indexes, per-project SigV4 credentials, and FDW wrappers — are specified in [Shared Storage, S3, and Storage Vectors](storage-vectors-lifecycle.md), the canonical source for that topic. This document describes when those steps run, not how they are implemented.

Long-running operations are represented by persistent jobs. The HTTP endpoint normally creates the job and returns its identifier; execution continues in the project's serialized queue.

## Identifiers in use

Before following any flow, distinguish:

- `project_uuid`: `projects.id`, canonical and immutable identity;
- `tenant_uuid`: persisted binding for Realtime/JWT/backups; equals `projects.id` for new projects and may preserve the legacy UUID;
- `project_ref`: mutable slug used in URLs and physical resources;
- `_supabase_<project_ref>`: database;
- Realtime tenant: identified by UUID;
- Storage tenant: identified by the immutable `tenant_uuid`;
- Supavisor tenant: identified by the project ref;
- main CDC slot: suffixed by the project ref;
- temporary broadcast slot: suffixed by a UUID-derived hash.

Before any mutable Storage operation on an existing project, the lifecycle queries `projects.tenant_uuid` in the control plane and requires it to equal the environment's canonical `PROJECT_UUID`. A mismatch, missing row, or query failure ends the operation before touching the registry, database, or namespace.

## Creation

Summary:

1. the API validates the user and name;
2. generates `projects.id` once and persists the same value in `tenant_uuid`;
3. creates the job with both durable identifiers;
4. the script generates the JWT secret, internal anon/service-role JWTs, config token, and opaque gateway-exclusive token;
5. creates `_supabase_<project_ref>` from `_supabase_template`;
6. registers the Realtime tenant with `external_id = tenant_uuid`;
7. registers the Supavisor tenant with `external_id = project_ref`;
8. creates the physical namespace and registers the tenant in global Storage through the Admin API;
9. creates tenant-exclusive S3/SigV4 credentials;
10. generates `.env`, compose, Dockerfile, and Nginx configuration without local Storage or imgproxy;
11. starts only the project's local services: Auth, PostgREST, and Nginx; Postgres-Meta, Storage, imgproxy, Realtime, Supavisor, and Edge Functions remain global;
12. validates migrations, database, JWT, S3, Vectors, and routing for the real tenant;
13. persists encrypted secrets in the project record and completes the job.

The JWT uses the UUID as its issuer:

```json
{
  "role": "anon",
  "iss": "<tenant_uuid>"
}
```

The database name and main slot continue to use the project ref. The temporary broadcast slot uses a hash derived from the tenant UUID.

### Rollback

The script tracks created resources and attempts to remove them in the required order:

- directories;
- Storage tenant, credentials, and namespace;
- database;
- Realtime tenant;
- Supavisor tenant.

Shell rollback does not replace the API's final validation. Partial failures must appear in the job.

## Duplication

Duplication creates another project with a new UUID, new keys, and new tenants.

Modes:

- `schema-only`: copies the required structure and migration history;
- `with-data`: copies the schema, data, and storage.

Even when data is copied, the new project's identity is independent:

- new UUID;
- new JWT issuer;
- new Realtime tenant;
- new Supavisor tenant;
- new Storage tenant and namespace;
- new S3/SigV4 credentials;
- new API keys;
- new config token.

The copy does not reuse secrets or object references. `schema-only` creates an empty namespace. `with-data` captures the source with its services stopped and the Storage tenant in fail-closed maintenance, copies files to the new UUID, reidentifies Vector's physical tables, and removes copied FDWs/Vault secrets before creating new credentials.

## Rename

Rename changes the project ref but preserves both `projects.id` and `projects.tenant_uuid`.

Resources that follow the new name:

- project directory;
- `.env` and templates;
- container names;
- Traefik route;
- `_supabase_<project_ref>` database;
- Supavisor tenant;
- Realtime main slot;
- physical references used by services;
- Studio snippet directories.

Resources that retain the same identity:

- project UUID;
- membership;
- notes, tags, hints, and threads;
- audit records;
- Realtime `external_id`;
- Storage tenant ID and object namespace;
- S3/SigV4 credentials;
- UUID-derived temporary broadcast slot;
- JWT keys, unless another rotation operation is requested.

### History

Each rename creates a record in `project_name_history` with:

- previous name;
- new name;
- previous path;
- new path;
- associated job;
- status;
- error and timestamps.

### Supavisor

The old Supavisor tenant must be removed before creating the new one to avoid an identity conflict.

If a failure occurs after removal, rollback attempts to restore the old tenant.

### Realtime

The tenant remains identified by UUID. Rename updates database-bound resources, including the main slot and CDC extension configuration, without changing the canonical `external_id`.

### Storage

The tenant is put into fail-closed maintenance before the database rename. The lifecycle replaces `databasePoolUrl` with a deliberately unreachable URL and confirms through the data plane that the tenant responds with an error; `null` is not used because official Storage would fall back to `databaseUrl`. After the rename, the lifecycle updates canonical `databaseUrl` and `databasePoolUrl` through the Admin API, runs the official migrations, and validates the same tenant UUID through the new Nginx. No object is moved; only Vector-wrapper endpoints containing the project ref are reconciled.

### Snippets

Supabase Studio stores snippets in directories that include the user and project slug.

After the main rename, the API calls OpenResty's internal endpoint to rename these directories.

The migration is best-effort:

- a snippet failure does not invalidate the already-renamed project;
- the job records a warning;
- the directories may require manual correction or a dedicated retry.

## Opaque API keys

New and duplicated projects start with `default-publishable` and `default-secret` slots. Existing projects use explicit preparation, claim, confirmation, and cutover; after cutover, legacy public JWTs are no longer accepted.

Each slot has its own rotation, **optional time-based expiration**, service scope, and revocation. `expires_at = NULL` means the key remains valid until revocation, rotation, disabling, or another policy block; it does not mean the key cannot be removed. For timestamped slots, automation can prepare the next version before expiration. Automation can be disabled at the project or slot level.

The complete protocol is in [Opaque API key operations](../12-opaque-api-key-operations.md).

## Internal JWT rotation

Infrastructure rotation generates new internal anon and service-role JWTs using the existing JWT secret. It can recreate a project's Nginx only when the opaque gateway is ready.

This avoids immediately invalidating all end-user sessions.

Flow:

1. generates new tokens;
2. updates project files;
3. updates Nginx configuration;
4. persists secrets with envelope encryption;
5. increments `project_key_version`;
6. invalidates the Studio service-key cache;
7. persists the new expiration, completes the job, and records the audit event.

Cache invalidation is part of operation success. Before using any entry, OpenResty must confirm the canonical version in the Projects API. If the query fails, the request is blocked; a cached key never replaces version validation.

### Automatic rotation

Every project starts with `automatic_key_rotation_enabled=true`. The Projects API calculates the schedule from the `exp` claim, persists `key_expires_at`, and creates a job in the same runner as manual rotation seven days before expiration. The scanner:

- uses a PostgreSQL advisory lock to ensure a single leader;
- locks the row with `FOR UPDATE SKIP LOCKED`;
- does not create a second job while an action is active in the project;
- limits global concurrency;
- records the system actor, version, and expiration in the audit log.

An automatic failure records `automatic_key_rotation_blocked_at` and `automatic_key_rotation_last_error`. The scanner does not repeat the operation until an admin explicitly resumes automation or completes a manual rotation. There is no silent loop or use of the previous key as a secondary path.

The option can be disabled in Studio or through `PUT /api/projects/{project_ref}/automatic-key-rotation` with `{"enabled": false}`. Global parameters are:

- `AUTOMATIC_KEY_ROTATION_LEAD_DAYS=7`;
- `AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS=300`;
- `AUTOMATIC_KEY_ROTATION_MAX_CONCURRENT=3`.

### Expiration

The API extracts expiration metadata from JWTs, schedules automatic rotation, and notifies Studio when keys are expired or near expiration.

The window is configured by `KEY_EXPIRY_WARNING_DAYS`.

### JWT-secret rotation

Changing the JWT secret is a different, higher-impact operation:

- invalidates existing tokens;
- requires synchronization with Realtime and services;
- ends Auth sessions;
- requires a maintenance window and rollback plan.

It must not be confused with ordinary API-key rotation.

## Settings and service recreation

### Resource limits

The profile is the ceiling for the **whole project**, not per container. `PROJECT_RESOURCE_PROFILE` (`small|medium|large`) names a total in the root `.env`, and `lib/resource_profiles.sh` splits it across the three tenant containers by fixed weights — memory 1:3:4, cpus 1:2:3, pids 2:5:5 for nginx:auth:rest, with the integer-division remainder going to `rest` so the shares sum exactly to the total. `nginx` is a thin proxy; `auth` (GoTrue) and `rest` (PostgREST) carry the load.

| Profile | Project total | nginx | auth | rest |
| --- | --- | --- | --- | --- |
| `small` | 256m / 0.50 / 128 | 32m / 0.08 / 21 | 96m / 0.16 / 53 | 128m / 0.26 / 54 |
| `medium` | 1g / 1.50 / 384 | 128m / 0.25 / 64 | 384m / 0.50 / 160 | 512m / 0.75 / 160 |
| `large` | 4g / 3.00 / 768 | 512m / 0.50 / 128 | 1536m / 1.00 / 320 | 2048m / 1.50 / 320 |

Every rendered project Compose pins each service's own share through fail-closed interpolation (`${PROJECT_NGINX_MEM_LIMIT:?...}`, `${PROJECT_AUTH_CPUS:?...}`, …), so a project without limits refuses to start instead of running unconstrained. The shares are written to the project `.env` at create, duplicate, rename, and rotate-key time. Existing projects are migrated idempotently with `tools/migrate_project_resource_limits.py` (dry-run by default, `--apply` to write), which delegates to the same helper, followed by a recreate. Database-level quotas (connection limits per tenant role, statement timeouts) and disk quotas remain open items; disk usage is currently an observability concern only.

Changing settings writes the `.env` atomically and reports the affected services.

Examples:

- Auth for GoTrue options;
- REST for PostgREST schemas and pool;
- Storage tenant and Nginx for the file limit;
- Storage tenant for image transformations, S3 Protocol, and Vector Buckets.

The Storage update sends `PATCH /tenants/<tenant_uuid>` and does not restart global Storage or imgproxy. Nginx recreation remains an idempotent job when its local configuration changes.

## Restore points

A restore point captures **data, not identity**: a dump of the `_supabase_<project_ref>` database (without the `realtime` schema, which is captured separately as in duplication) and a tar containing only `volumes/storage/objects/<tenant_uuid>/`. Format-2 `manifest.json` includes the UUID, Storage tenant ID, layout, ref at capture time, Postgres version, and the tables in the Realtime publication.

The point excludes: `.env`, JWT secret, anon/service keys, config token, Realtime/Supavisor tenants, and container configuration. Therefore a point remains restorable after key rotation and rename — files live in `servidor/backups/<tenant_uuid>/<point_id>/`, keyed by the `tenant_uuid` persisted in the control plane and mirrored in `PROJECT_UUID` in the project `.env` (immutable during rename). A backup never traverses the global root or includes another tenant's namespace.

### Capture (cold)

The backup is cold by product decision: the script stops project services (shared Postgres remains up), terminates the tenant's Supavisor pools, and places only the Storage tenant into fail-closed maintenance. The script confirms through the data plane that the cache no longer accepts operations, closes remaining Storage connections, captures database + namespace atomically (`<id>.tmp` + rename), restores the tenant's canonical URLs, and restarts only containers that were running.

### Restoration

1. stop project services, shut down the Realtime tenant, terminate Supavisor pools, and put the Storage tenant into fail-closed maintenance;
2. capture an **automatic safety point** with the current state and emit `SAFETY_BACKUP_COMPLETE`;
3. drop replication slots and rename the current database to `_supabase_<ref>_prerestore` (the rollback plan, not a DROP);
4. create the new database, restore the dump, and reapply known duplication fixes: `realtime.messages` partitions, publications (with manifest tables), `TRUNCATE realtime.subscription`, `search_path`, `supabase_storage_admin` override, grants, and pgvector contract validation;
5. recreate the main slot and swap only the UUID namespace through transactional staging; reject the archive if it has an absolute path, `..`, symlink, or special type;
6. reconnect the tenant, run official migrations, restart containers, validate JWT/S3/Vectors through the real tenant, and synchronize vector wrappers;
7. only then remove `_supabase_<ref>_prerestore` and namespace staging.

Failures trigger compensating rollback with the `ROLLBACK_COMPLETE` marker, as in rename. The safety point survives the failure and becomes a normal point in the list.

Restoration also reverts Auth users and sessions (the `auth` schema is part of the database). Project keys and URL do not change.

### Control plane

The `project_restore_points` table stores title (default: date/time), description, status (`creating`, `ready`, `restoring`, `deleting`, `failed`), automatic-point flag, size, restore counters, and the associated job. There is a limit of 15 active points per project; restoration requires a free slot for the automatic point. All operations are audited in `studio_audit_log`. Listing is available to any member; creating a point requires a project admin, while restoring or deleting a point requires the owner or global admin. `backup` and `restore` are not idempotent: API recovery reconnects to the existing host-agent intent rather than rerunning it. Full project deletion remains exclusive to global admins, also protected by step-up with the current Authelia account's personal password, and removes `servidor/backups/<uuid>/` with the files.

## Start, stop, and restart

These operations:

- query the container state associated with the project;
- are serialized in the project queue;
- update status and audit records;
- are marked idempotent and retryable.

The state displayed by the API comes from the `project_container_state` snapshot maintained by the host-agent; the Projects API does not query Docker directly.

## Deletion

Deletion must remove resources without allowing Supavisor or other services to recreate connections during the process.

Current flow:

1. validate global admin and consume a one-time step-up grant bound to the session, action, and project;
2. create the delete job;
3. remove project containers;
4. revoke credentials, remove the tenant from the Storage registry, and delete only that UUID's validated namespace;
5. remove or terminate the tenant's Supavisor pools;
6. clean the Realtime tenant and extensions and Supavisor metadata;
7. drain active database connections and confirm the pooler does not reconnect;
8. remove replication slots and the database;
9. remove control-plane records;
10. remove the project directory and backups for the same tenant UUID;
11. validate the result and record the audit event.

### Database protection

If Supavisor continues opening connections after tenant removal and draining, deletion must fail before `DROP DATABASE`.

Preserving a still-referenced database is safer than completing a partial, inconsistent deletion.

### Partial result

Infrastructure failures may leave:

- containers;
- Storage tenant or tenant namespace;
- Realtime/Supavisor tenants;
- slot;
- directory;
- central records.

The job must expose the stage, message, error code, and output tails to support manual recovery.

## Recovery and retry

Recovery has two different layers, which must not be confused.

### API restarted while the host-agent continues executing

The lifecycle intent already exists in `host_agent_commands`. The host-agent can continue executing while the Projects API is down. When the API returns, recovery reconnects the job to the **same persisted intent**, reuses the terminal result if one exists, and does not launch a second script.

This behavior is especially important for distributed operations such as create, duplicate, rename, rotate, backup, restore, and delete.

### Idempotent actions

The system currently treats these as idempotent:

- start;
- stop;
- restart;
- recreate services.

These actions can be resumed or repeated with attempt control.

### Uncertain state or terminal host-agent failure

Create, duplicate, rename, rotate, backup, restore, and delete have distributed effects. If the intent ends in failure, an expired lease, or another state where the physical result cannot be proven, the API **does not blindly rerun** the operation.

The job preserves:

- current stage;
- progress;
- sanitized stdout/stderr;
- error code;
- rename or restore-point history, when applicable.

Recovery then proceeds through domain-specific rollback/reconciliation or manual review. Persisting the intent prevents a normal API restart from being mistaken for authorization to repeat a non-idempotent operation.

## Relevant tests

- `tests/smoke/test_tenant_lifecycle.py`
- `tests/smoke/test_host_agent_contract.py`
- `tests/smoke/test_jobs_contract.py`
- `tests/smoke/test_restore_points_contract.py`
- `tests/smoke/test_project_access_and_deletion_contract.py`
- `tests/smoke/test_service_key_cache_contract.py`
- `tests/smoke/test_key_generation_contract.py`
- `tests/smoke/test_opaque_api_keys.py`
- `tests/smoke/test_opaque_api_key_optional_expiration.py`
- `tests/smoke/test_project_telemetry.py`
- `tests/smoke/test_shared_storage_architecture_contract.py`
- `tests/smoke/test_shared_storage_tenant_integration.py` (opt-in, disposable installation)
- `tests/smoke/test_storage_vector_lifecycle_integration.py`

Test names may evolve; also look for lifecycle contracts in `tests/smoke/`.
