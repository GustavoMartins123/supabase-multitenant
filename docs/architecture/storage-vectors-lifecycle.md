# Shared Storage, S3, and Storage Vectors

## Adopted upstream contract

The implementation uses the official multi-tenant mode of
`supabase/storage-api:v1.61.12` without patches. The reference was checked at
the upstream repository's `v1.61.12` tag, not only at HEAD.

The global service uses:

- `MULTI_TENANT=true`;
- `DATABASE_MULTITENANT_URL` for the dedicated `_supabase_storage` registry;
- `SERVER_ADMIN_API_KEYS` and the Admin API on internal port 5001;
- `AUTH_ENCRYPTION_KEY` to encrypt sensitive registry fields;
- `REQUEST_X_FORWARDED_HOST_REGEXP` to extract a tenant UUID;
- `STORAGE_BACKEND=file` and `TenantLocation`;
- `VECTOR_BUCKET_PROVIDER=pgvector`;
- one internal `IMGPROXY_URL`.

The lifecycle is deliberately coupled to this contract verified at the
`v1.61.12` tag: it requires the canonical image, `STORAGE_BACKEND=file`,
`STORAGE_FILE_BACKEND_PATH=/var/lib/storage`, and internal `objects` bucket.
It fails before mutating data if the configuration or actually running image
differs; it does not interpret another backend as a file layout.

The Admin API is not published on the host or connected to `rede-supabase`.
The Storage container uses internal control and data-plane networks; a
credentialless global Nginx, aliased as `supabase-storage-global` on the
exclusive `supabase-storage-gateways` internal network, forwards exclusively
to `storage:5000`. Only each project's trusted Nginx joins this network;
Auth, PostgREST, and the other project containers remain outside it. The
lifecycle calls the Admin API through `docker exec`, reads the key only inside
the container, and never includes it in argv, project files, public responses,
or logs.

## Identity and physical location

The Storage tenant ID is the immutable `tenant_uuid`, persisted in
`projects.id` and materialized as `PROJECT_UUID`. `project_ref` is not used
as object identity because it changes during rename.

In the adopted version, `TenantLocation` forms the physical key as:

```text
<tenant_uuid>/<bucket_id>/<object_name>
```

With `STORAGE_FILE_BACKEND_PATH=/var/lib/storage` and
`STORAGE_S3_BUCKET=objects`, the host stores:

```text
servidor/volumes/storage/objects/<tenant_uuid>/<bucket_id>/<object_name>
```

Lifecycle helpers accept only lowercase canonical UUIDs, resolve the real root,
reject symlinks, and validate archives before extraction. There is no default
tenant, and a missing or unknown identity fails.

The Storage container runs with `cap_drop: ALL`, therefore without
`CAP_DAC_OVERRIDE`: it can write to a namespace only if it owns the
directories. `STORAGE_RUN_AS_USER` (format `UID:GID`) declares this identity
in Compose and must match the owner of `servidor/volumes/storage` on the host.
Every namespace materialization — empty creation, clone, and restore — passes
through `storage_enforce_namespace_ownership`, which adjusts ownership or
fails before delivering a tenant that Storage cannot write to.

For operations on an existing project, the `project_ref`/`tenant_uuid` pair is
also compared with `projects.tenant_uuid` in the control plane. A divergent
`.env` cannot select another project's namespace.

## Tenant HTTP resolution

Each project Nginx knows the UUID rendered in its own file and always overwrites
the value received from the client:

```nginx
proxy_set_header X-Forwarded-Host "<tenant_uuid>.storage.internal";
```

Storage accepts only hosts that fully match the UUID regexp. The data-plane
proxy also rejects with HTTP 421 any data request without this canonical host
or with an invalid value; only `/status`, used by the infrastructure
healthcheck, does not require a tenant. Therefore, `X-Forwarded-Host`,
`Host`, or any purported tenant header sent by the client cannot select
another project.

The opaque-key flow remains:

```text
sb_publishable / sb_secret
  -> project Nginx
  -> key-authorizer bound to project_ref
  -> internal anon/service_role JWT for that project
  -> global Storage with X-Forwarded-Host overwritten
```

The JWT secret, anon key, and service key are encrypted in each tenant's
registry. No global JWT is used as a substitute. An opaque key from A is not
resolved by B's gateway, and A's JWT does not validate against B's secret.

## Database and per-tenant migrations

The tenant record contains two URLs:

- direct: `supabase_storage_admin` in `_supabase_<project_ref>` through the
  `db` hostname on the control network;
- pool: `supabase_storage_admin.<project_ref>` through the `supavisor`
  hostname on the same network.

Create, duplicate, rename, and restore grant access to
`supabase_storage_admin`, set `search_path=storage,public`, and validate
pgvector. The lifecycle registers or updates these URLs through the Admin API.
Rename changes only the URLs; the tenant UUID and object namespace remain the
same.

Migrations run through the official endpoint
`POST /tenants/<uuid>/migrations`. The lifecycle expects
`migrationsStatus=COMPLETED` and `isLatest=true`. Upstream Storage serializes
migrations per tenant; different projects do not need a global lock.

## S3/SigV4 credentials

Each tenant receives its own credential through the official Admin API:

```text
POST /s3/<tenant_uuid>/credentials
```

The returned access key and secret are written only to the project's mode-0600
`.env` and the wrappers' Vault secrets. In the registry, the secret is
encrypted with `AUTH_ENCRYPTION_KEY`.

When verifying a signature, upstream calls
`getS3CredentialsByAccessKey(tenantId, accessKey)`. Therefore the access key
is searched only within the tenant already resolved by the host. Credential A
with B's host fails; there is no global lookup or substitute credential.

For `/storage/v1/s3`, the client signs the public host and path. Nginx:

- preserves `Host`, which is part of the canonical signature;
- rewrites the internal route to `/s3`;
- provides the trusted public prefix in `X-Forwarded-Prefix`;
- overwrites `X-Forwarded-Host` exclusively to resolve the tenant.

## Storage Vectors

Storage Vectors uses the same SigV4 pair as the S3 Protocol, but the signing
service is `s3vectors`. The `pgvector` provider writes metadata and tables to
the project's own database.

Each project's FDW points to its Nginx:

```text
http://supabase-nginx-<project_ref>:8080/vector
```

The wrapper signs this endpoint's `Host`. Nginx preserves this canonical host
and injects the immutable UUID into `X-Forwarded-Host`. This allows the
endpoint to change during rename without changing tenant identity. The
lifecycle reconciles `endpoint_url` after duplicate, rename, and restore.

The physical name of a pgvector table includes a hash calculated by upstream
from the bucket, tenant, and index. A `with-data` clone renames these tables in
a transaction to hashes for the new UUID. The clone also removes copied FDWs
and Vault secrets, creates new credentials, and recreates wrappers only for its
own Vector Buckets. `schema-only` creates an empty namespace and metadata.

## Create and validation

Create runs, in the relevant order:

1. creates and validates the database;
2. registers Realtime and Supavisor;
3. creates the exclusive physical namespace;
4. registers the tenant through the Admin API;
5. creates the SigV4 credential;
6. renders only the project's Auth, PostgREST, Nginx, and Postgres-Meta;
7. starts these containers;
8. validates migrations, tenant health, JWT-to-database access, S3 SigV4,
   `ListVectorBuckets`, and the real Nginx path with a hostile host header.

Any failure ends the job and triggers compensating rollback. Global Storage is
not restarted and no local container is started.

## Settings

`FILE_SIZE_LIMIT`, image transformation, S3 Protocol, Vector Buckets, and
Vector limits are tenant fields. `apply_storage_settings.sh` sends a
`PATCH /tenants/<uuid>` and validates the real tenant. Only the project Nginx
is recreated when its body limit must change; global Storage and imgproxy are
not restarted for project settings.

## Backup, restore, and delete

Backup places only the requested Storage tenant into fail-closed maintenance,
confirms through the data plane that it accepts no new operations, stops the
project containers, and archives only the contents of its namespace.
Maintenance uses a deliberately unreachable `databasePoolUrl`; it does not
use `null`, because official Storage would query `databaseUrl`. Format-2
manifest binds `project_uuid`, `storage_tenant_id`, and
`storage_layout=tenant-namespace`.

Restore rejects manifests from another UUID and archives with absolute paths,
`..`, symlinks, or special types. The current namespace is moved to
transactional staging, only the requested namespace is extracted, migrations
are rerun, and wrappers are reconciled. Other tenants remain intact.

Delete revokes all credentials through the Admin API, removes the tenant from
the registry, and only then removes the validated directory for that UUID. The
project database is removed only after this step completes.

## Observability

Global Storage JSON logs preserve `tenantId`, request ID, method, path, and
operation type when provided by upstream. The data-plane proxy records only the
path without query string, method, status, request ID, and the tenant host
already overwritten by trusted Nginx. Vector extracts only the canonical UUID
from this host and sends both streams to the Storage sink without recording
keys, tokens, passwords, or SigV4 credentials.

## Tests

- `test_shared_storage_architecture_contract.py` protects topology, routing,
  lifecycle, migration, and the absence of old paths without requiring Docker;
- `test_shared_storage_tenant_integration.py` is opt-in and runs the active
  two-tenant matrix: private objects, same bucket names, opaque keys,
  cross-tenant SigV4, Vectors, limits, images, clones, rename, backup/restore,
  delete, missing tenant, hostile header, and global unavailability.

There is no alternate bootstrap, default tenant, or fallback to local Storage.
