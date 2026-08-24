# Control plane

The control plane manages projects and users. It does not directly serve the public Auth, REST, or Storage APIs used by applications.

The main components are:

- Flutter selector;
- OpenResty/Lua;
- Projects API on FastAPI;
- least-privilege data-plane `key-authorizer`;
- `postgres` database;
- host-agent on the server, which runs lifecycle scripts and Docker (see [host-agent](host-agent.md));
- internal integrations with Realtime, Supavisor, global Storage, Postgres-Meta, and Studio.

## Responsibilities

### Identity

`last_login_at` changes only when the HMAC token carries a fingerprint for a new Authelia session. The fingerprint is derived with SHA-256 and the cookie never leaves the gateway. Normal requests update `last_seen_at` with five-minute sampling.

Authelia authenticates the user, but internal authorization uses a stable UUID stored in the `users` table.

OpenResty resolves and synchronizes the identity, then sends the API:

```text
X-User-Token: v1.<payload>.<assinatura>
```

The token is signed with `NGINX_HMAC_SECRET` and has short validity. The API extracts the UUID, validates the signature, and queries the user in the database.

Email, username, display name, and groups are synchronized attributes. They do not replace the canonical UUID.

### Step-up authentication

Authorization answers whether the actor may perform an operation; step-up confirms that the same actor still controls the session at the sensitive moment. At this stage it is required for full project deletion and for every response exposing `sb_secret_*` plaintext.

Flutter sends the personal password only to the OpenResty endpoint. The gateway obtains the username from `auth_request), not from the client's JSON, validates the password at Authelia's internal `/auth/api/firstfactor`, and does not forward that subrequest's `Set-Cookie`. It then issues a five-minute `su1` HMAC grant bound to the UUID, current-cookie fingerprint, action, project ref, resource, and nonce.

The Projects API does not confuse this grant with `X-User-Token`: the prefix and derived key have their own domain. It revalidates authorization in PostgreSQL and inserts the nonce into `studio_step_up_grant_consumptions` with `ON CONFLICT DO NOTHING`. Each grant is therefore accepted once. Authelia unavailability, missing binding, an expired/repeated token, or a role change blocks the action. Password, complete grant, and plaintext are not persisted or audited.

### Authorization

Authorization considers:

- global administrator;
- project owner;
- member with `admin` role;
- member with `member` role;
- operation-specific rules.

The API does not trust only the groups sent by the gateway. It queries persisted state and validates ownership or membership before accessing secrets, settings, telemetry, or metadata.

## Central schema

The `postgres` database stores control-plane state.

The schema belongs to versioned migrations in `servidor/api-internal/app/migrations`. A privileged, ephemeral deployment step applies them and provisions the least-privilege identities (`key_authorizer`, `host_agent_rw`); Projects API boot only checks the version recorded in the ledger and refuses to serve when the database is behind the image. No DDL runs in the request-serving process. See [Control-plane migrations](control-plane-migrations.md).

### Database identities

| Role | Consumer | Scope |
| --- | --- | --- |
| `key_authorizer` | key-authorizer service | column-scoped `SELECT` on `projects`, `project_api_key_slots`, `project_api_keys`; `UPDATE (last_used_at)` |
| `host_agent_rw` | host-agent worker | `SELECT/INSERT/UPDATE` on `host_agent_workers` and `host_agent_commands`; `SELECT/INSERT/UPDATE/DELETE` on `project_container_state`. No access to any other control-plane table and no tenant database. |

The host-agent resolves its DSN as: explicit `HOST_AGENT_DB_DSN` → dedicated identity (`HOST_AGENT_DB_PASSWORD`, user fixed as `host_agent_rw`) → legacy derivation from `POSTGRES_USER`/`POSTGRES_PASSWORD`. The legacy fallback exists only while the Projects API still shares the privileged DSN; it is removed together with that separation.

### Identity and access

Main tables:

- `users`;
- `user_groups`;
- `user_group_audit`;
- `projects`;
- `project_members`;
- `project_members_audit`;
- `studio_step_up_grant_consumptions` (ledger without passwords or bearer tokens).

The `projects` table contains the canonical UUID (`id`), persisted binding to the external tenant (`tenant_uuid`), project ref, display name, key version, and encrypted secrets. For new projects, `tenant_uuid` receives exactly `id`; the separate column preserves auditable compatibility with legacy projects.

### Opaque API keys

The public registry does not use scalar JWT columns as client credentials:

- `project_api_key_slots` represents each consumer and its policy;
- `project_api_keys` maintains versions, digest, optional expiration, and lineage;
- `project_api_key_reveals` temporarily stores encrypted plaintext;
- `projects.api_keyset_version` versions each mutation;
- `opaque_*` timestamps represent preparation, cutover, activation, and readiness.

The `key-authorizer` authenticates each Nginx with an exclusive token whose hash is stored in `projects.api_gateway_token_hash`. Its role has only the `SELECT` permissions required by the lookup and `UPDATE(last_used_at)`. A database or subrequest failure blocks access; the Projects API is not on the hot path.

Routes live under `/api/projects/{project_ref}/api-key-*` and `/opaque-api-keys/migration`. Members receive only `publishable` metadata/reveals; mutations remain limited to project or global admins. `secret` plaintext adds step-up, and every operation revalidates persisted state, uses transactions, and never lists plaintext. See [the runbook](../12-opaque-api-key-operations.md).

### Jobs

The `jobs` table persists:

- action;
- payload;
- status;
- progress;
- current stage;
- total stages;
- timestamps;
- stdout and stderr tails;
- error code;
- idempotency;
- retry;
- current attempt.

The corresponding physical intent lives in `host_agent_commands`, with signature, lease, heartbeat, result, and `job_id` link. This separation lets the administrative job survive an API restart without turning restart into authorization to run a distributed script again.

### Studio collaboration

The control plane also maintains administrative resources that do not belong to tenant databases:

- `studio_project_tags`;
- `studio_project_tag_assignments`;
- `studio_project_notes`;
- `studio_project_hints`;
- `studio_project_thread_messages`;
- `studio_project_notifications`;
- `studio_audit_log`;
- `project_name_history`;
- `project_restore_points`.

These resources use the project UUID as their reference. A rename does not create a new project and must not break notes, tags, history, or audit records.

## Jobs and per-project queue

The Projects API serializes lifecycle operations per project. This prevents, for example, rename and delete from running simultaneously for the same tenant.

Main states:

```text
queued -> running -> done
                  -> failed
                  -> cancelled
```

The API records progress and the current stage during long operations.

### Startup recovery

At startup, the API looks for jobs in `queued` or `running` and separates two situations:

- if a corresponding `host_agent_commands` intent already exists, recovery reconnects the job to the **same intent**, follows the command while active, or reuses the persisted result; it does not launch a second execution;
- known idempotent actions can be resumed or repeated in a controlled way when no physical command is in progress;
- non-idempotent distributed operations with genuinely uncertain results are not blindly rerun; state is preserved for domain-specific rollback/reconciliation or manual review;
- rename keeps separate history in `project_name_history`, and backup/restore preserve their own records.

Recovery must not assume that rerunning any script is safe.

## Secrets

### Persistence

`anon_key`, `service_role`, and `config_token` are stored with envelope encryption.

Each project has a DEK. The DEK is wrapped by `PROJECT_SECRETS_MASTER_KEY`. Secrets use AES-256-GCM with AAD containing the project and the value's purpose.

### Distribution to containers

`servidor/.env` holds the control-plane secrets: `PROJECT_SECRETS_MASTER_KEY`, `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`, `HOST_AGENT_HMAC_SECRET`, the internal HMACs, and the global PostgreSQL password. No container that serves a tenant receives this file.

Compose is invoked with `--env-file`, which resolves `${VAR}` interpolation in the `environment:` blocks at parse time. Declaring `env_file:` on a service is therefore not required to render the file: it only injects every variable into the container process. Each service declares exactly the variables it consumes, and `storage` reads its own scoped `.storage.env`.

The project's `auth` and `rest` receive only their explicit `environment:` block. Edge Functions workers receive the tenant contract — `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`, `JWT_SECRET`, and `PROJECT_REF` — and never the environment of the runtime that spawns them.

### Service-role transport

OpenResty needs `service_role` to reproduce Supabase Studio administrative operations.

The API:

1. validates the user and project access;
2. decrypts the persisted secret;
3. encrypts the value for transport with `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`;
4. returns it only to the authorized internal route.

Nginx decrypts it, stores it in the shared cache, and injects it into upstream. The browser does not receive the key.

### Versioned cache

The `projects` table maintains `project_key_version`.

After a rotation:

1. the API persists the new keys and increments the version;
2. calls the internal invalidation endpoint in Studio;
3. OpenResty removes the previous entry and publishes the minimum version;
4. workers discard keys below that version;
5. every use confirms the canonical version in the Projects API.

Failure of the version query blocks the request. OpenResty does not use a cached service key when it cannot prove that it matches the persisted version.

### Key schedulers

The Projects API maintains two independent cycles. `key_expires_at` schedules regeneration of internal anon/service-role JWTs through the durable `rotate_key` flow. The opaque registry schedules each slot through `project_api_keys.expires_at` when that field has a timestamp and prepares a `pending` version requiring claim and confirmation. `expires_at = NULL` represents a slot without time-based expiration and is excluded from lead-time and expiration queries.

Both scanners use a PostgreSQL advisory lock and row locks for leader election and safe distribution across replicas. The opaque scheduler processes only projects whose gateway has `opaque_gateway_ready_at`. A manual pending version with explicit cutover continues converging even when the new version does not expire.

Automatic failures block new attempts for that project until explicit intervention. Re-enabling clears the block and requests a new reconciliation; disabling prevents the host-agent from authorizing the system actor.

The canonical internal-cache behavior is documented in [OpenResty/Lua](openresty-lua.md). The external lifecycle is in the [opaque-key runbook](../12-opaque-api-key-operations.md).

## Project settings

The API allows changing only a whitelist of known variables.

Current categories:

- GoTrue signup and auto-confirmation;
- anonymous users and phone;
- JWT and OTP expiration;
- minimum password length;
- PostgREST schemas and limits;
- PostgREST pool;
- upload limit;
- image transformation.

Local values are normalized, validated, and written atomically to the project's `.env`. Settings belonging to shared Storage are applied to the canonical tenant through the Admin API during the host-agent's closed command, without recreating global Storage or imgproxy.

The API calculates which services were affected and queues only the required recreation or reconciliation.

## Administrative telemetry

Owners, project admins, and global administrators can query Auth user telemetry.

The API connects directly to the project database and queries `auth.users` and `auth.sessions` for:

- 24 hours;
- 7 days;
- 30 days;
- a limited custom period.

The read is audited and does not use a browser cache. GoTrue schema compatibility failures return an explicit error without changing the project.

## Postgres-Meta

OpenResty forwards Studio calls to the Projects API. The API:

1. validates the project ref;
2. validates identity and membership;
3. checks the project's service role;
4. builds the connection to `_supabase_<project_ref>` internally;
5. encrypts the connection with `PG_META_CRYPTO_KEY`;
6. calls `postgres-meta-global`.

The client cannot control the host, user, database, or connection header.

## Internal integrations

### Projects API to host-agent

The Projects API does not execute Docker or a shell. It writes intents signed with `HOST_AGENT_HMAC_SECRET` to `host_agent_commands`, and the host-agent (a systemd service on the host) claims the lease, revalidates the signature, arguments, and authorization, and executes the closed command. The complete contract (commands, lease/heartbeat/timeout, path confinement, and output sanitization) is in [host-agent](host-agent.md).

Creation, duplication, rename, backup, restore, deletion, settings reconciliation, and other physical effects cross this boundary. Agent scripts register/reconcile Realtime, Supavisor, and Storage tenants when required.

The lifecycle Docker proxy was removed together with the API's `DOCKER_HOST`. Container state shown by status endpoints comes from the `project_container_state` snapshot maintained by the agent.

Traefik uses only the File Provider. Vector receives logs through the Fluent logging driver. No container component queries the Docker API.

### OpenResty to Projects API

Uses `internal-hmac-v1` with the `studio-nginx` identity; on user routes, `X-User-Token` remains separately required.

### Projects API to OpenResty

Used to:

- invalidate the service-key cache;
- query internal metrics;
- migrate snippet directories during rename.

The route validates `internal-hmac-v1` with `X-Internal-Service: projects-api`, timestamp, nonce, and body hash.

### Push worker

The push worker uses a backend-to-backend HMAC signature with timestamp, nonce, and body hash. This contract is separate from the user token.

## Auditing

Relevant actions must record:

- project;
- executing user;
- action;
- target type and ID;
- previous value;
- new value;
- timestamp.

Auditing is part of the control plane, not the project databases.

## Invariants

- Project UUID does not change during rename.
- `tenant_uuid` does not change during rename and identifies the Storage namespace.
- Service role is not sent to the browser.
- Project ref is validated before forming paths or database names.
- Persisted secrets do not use the Studio transport key.
- The Postgres-Meta header uses a key separate from persisted secrets.
- Operations are serialized per project.
- The Projects API does not access Docker or execute a shell.
- Automatic recovery is limited to known-safe actions or the same intent already persisted on the host-agent.
- Authorization queries persisted state, not only textual headers.

## Related code

- `servidor/api-internal/app/main.py`
- `servidor/api-internal/app/jobs.py`
- `servidor/api-internal/app/host_agent.py`
- `servidor/api-internal/app/host_agent_protocol.py`
- `servidor/api-internal/app/database_schema.py`
- `servidor/api-internal/app/control_plane_service.py`
- `servidor/api-internal/app/project_secret_service.py`
- `servidor/api-internal/app/project_settings.py`
- `servidor/api-internal/app/opaque_key_service.py`
- `servidor/api-internal/app/routers/opaque_keys.py`
- `servidor/api-internal/app/service_key_cache.py`
- `servidor/api-internal/app/project_telemetry.py`
