# Functions: tenant credential projection

The shared supervisor receives only `VERIFY_JWT` as an application setting
(explicitly `true` or `false`; production must use `true`). It has no root
PostgreSQL password/DSN, global JWT/anon/service keys, or mount of `projects`.
Code is read-only. Its one credential source is the read-only bind mount
`servidor/.functions-tenants` at `/home/deno/tenant-config`; Compose refuses to
create that source implicitly.

## Canonical contract

Each `<ref>.json` contains exactly five fields: `project_ref`, `project_uuid`,
`anon_key`, `service_role_key`, `jwt_secret`. The host projects only the three
necessary tenant credentials, not the full project environment, S3 credentials,
root database password, gateway/config tokens, database files or backups.
`functions_config.py` rejects missing/duplicate/noncanonical required env fields,
identity mismatch and symlink inputs. Files are replaced atomically, fsynced and
mode 0600 in a private 0700 directory. Projection and lock directories are ignored
by Git; install aligns their ownership with the host-agent service account.

Every request requires the exact `X-Project-Ref` supplied by its tenant gateway.
There is no query alias, normalization, global-tenant identity, old dotenv source
or stale cache. The supervisor reads the projection on each request and refuses
malformed, unknown-field, divergent or absent configuration with 503. JWTs must
be HS256 with that tenant's secret. Function names cannot traverse paths or invoke
`main`.

**Workers must not be reused by function path.** Edge Runtime v1.74.2 otherwise
reuses a worker with the first tenant's environment, even when a subsequent
`create` call supplies different `envVars`. The supervisor uses `forceCreate:true`
for every request. Module caching is independent and remains enabled. Workers
receive only the requested tenant's URL, anon/service keys, JWT secret and ref;
the real runtime denies their filesystem reads of supervisor credentials.

## Lifecycle and interruption

The actual create/duplicate/rename/rotate/restore/delete implementations use one
shared library, including calls made directly to their shell entrypoints. It
holds a shared global lock and sorted exclusive ref locks until completion,
including rollback. Startup `sync` holds the exclusive global lock. Duplicate
locks its source as well as its destination. Distinct projects can mutate in
parallel, while rename prevents old/new slug reuse during its transaction.

Before mutation, credentials are withdrawn and a durable `.withdrawn` marker is
written outside the container mount. Successful operations publish from the
verified canonical env; verified rename/rotate/restore rollbacks republish only
the restored env. Incomplete rollback/crash keeps the projection unavailable.
Delete never republishes; rename never preserves an old slug alias. Recreating
a deleted slug publishes the new canonical identity only after create succeeds.
Already-running requests are not retroactively cancelled.

`start.sh` runs `sync` in both server topologies before starting the stack. Sync
removes stale outputs before parsing and refuses existing projects with an
unfinished lifecycle marker. It never quietly recreates credentials after an
incomplete operation. Reinstall the host-agent to align ownership when upgrading;
stop old runtime/jobs and deploy scripts, supervisor and mount contract together.
For a manual Compose start, first run:

```bash
python3 servidor/generateProject/functions_config.py --root servidor sync
```

After a failed lifecycle, an operator must first verify or repair physical
containers, database, Storage, project UUID and env. Only after that verification
may the operator explicitly republish that tenant under the same locks:

```bash
SCRIPT_DIR="$(pwd)/servidor/generateProject"
PROJECT_ROOT="$(pwd)/servidor"
source "$SCRIPT_DIR/lib/functions_config.sh"
functions_config_lock example_project
functions_config_publish example_project
```

Do not delete a marker just to make startup pass. These local primitives require
an inherited lock descriptor; direct unlocked `publish`/`withdraw` commands fail.

## Reproducible evidence and boundary

```bash
python tools/run_functions_security_tests.py \
  --lifecycle-image servidor-projects-api:latest \
  --edge-image supabase/edge-runtime:v1.74.2
```

The runner requires existing Linux images, mounts only synthetic fixture files,
waits for HTTP readiness, and cleans up its container. Six Linux tests cover real
locks, exact projection, permissions, withdrawal, lifecycle primitive transitions,
interruption and explicit recovery. Six real Edge Runtime tests cover two tenants,
crossed JWTs, alternating worker environments, denied worker filesystem reads,
live credential changes/withdrawal and strict identity/config rejection. Required
runtime checks cannot succeed through skips.

The supervisor is still a trusted shared component: compromise of its own
process can read the three projected credentials for all tenants. This is
least-privilege projection, not per-tenant supervisor/process isolation. These
tests do not claim full physical database lifecycle or Authelia/Traefik/Storage
end-to-end validation in either topology; that integration acceptance remains
separate.
