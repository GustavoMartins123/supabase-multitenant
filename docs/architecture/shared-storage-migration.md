# Transitional migration to shared Storage

This procedure exists only to convert installations created with per-project
Storage API and imgproxy. It is not loaded by the runtime and does not create a
legacy mode, feature flag, or alternate route.

After completion, the installation operates exclusively with
`supabase-storage-global` and `supabase-imgproxy-global`. `start.sh`
explicitly rejects any project compose that still declares the old containers.

## Preconditions

Run on the installation's Linux host, from the checkout containing the new
architecture. Required:

- reviewed branch and configuration;
- external backup of the host and PostgreSQL;
- Docker/Compose, Bash, Python 3, `jq`, `openssl`, `tar`, `gzip`, `sed`,
  `grep`, `find`, and `systemctl`;
- `supabase-db` running;
- Projects API and host-agent installed in the current model;
- `STORAGE_IMAGE=supabase/storage-api:v1.61.12`, proxy
  `nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim`, and file backend in
  the canonical layout (`/var/lib/storage`, internal `objects` bucket);
  different values are rejected before conversion;
- no lifecycle job or command in `queued` or `running`;
- space for a second temporary copy of objects and backups.

Do not start create, duplicate, rename, delete, backup, restore, settings, or
rotation during the window.

## Execution

```bash
cd /path/to/supabase-multitenant
bash servidor/generateProject/migrate_shared_storage.sh
```

The tool:

1. verifies that no lifecycle is active;
2. records from Compose labels whether the Projects API uses `single-node` or
   `split-node`, then stops Projects API and host-agent, preventing new intents;
3. completes only canonical global keys in `servidor/.env`;
4. creates `.storage.env` with mode 0600 and random keys if it does not exist;
5. creates `_supabase_storage`, reconciles the internal DB/Supavisor networks,
   and starts Storage, imgproxy, and the global proxy restricted to the data plane;
6. discovers directories under `servidor/projects/`;
7. checks `PROJECT_UUID` against `projects.tenant_uuid`;
8. stops the project stack;
9. copies `storage/stub/stub` to
   `volumes/storage/objects/<PROJECT_UUID>` without removing the source;
10. reidentifies physical pgvector tables from `stub` to the UUID;
11. registers the tenant, runs migrations, and creates a new SigV4 credential
    through the official Admin API;
12. renders compose/env/Nginx only for the shared architecture;
13. starts Auth, PostgREST, Nginx, and Postgres-Meta;
14. validates tenant health, database, JWT, S3, Vectors, and Nginx while
    attempting to overwrite `X-Forwarded-Host`;
15. reconciles Vector wrappers;
16. archives the old directory in the internal report and only then removes the
    project-directory copy;
17. converts format-1 backups to format-2 namespace archives;
18. after all projects and backups, rebuilds the Projects API with the same
    topology override detected before stopping and restarts the host-agent.

Each project has a state file. The source copy is not deleted until the new
tenant passes complete validation.

## Report and resume

Each execution creates:

```text
servidor/storage-migration-reports/<timestamp-pid>/
```

The directory contains `summary.tsv`, per-project states, previous
configurations, old Storage archives, and replaced backups. It is internal,
ignored by Git, and may contain sensitive data; never publish it.

If interrupted, use exactly the directory reported in the error:

```bash
bash servidor/generateProject/migrate_shared_storage.sh \
  --resume servidor/storage-migration-reports/<timestamp-pid>
```

`--resume` detects the recorded stage. An incomplete project is reverted to its
previous state inside the tool before being attempted again. Ambiguous state —
for example, two physical namespaces or an existing tenant without state — is
blocked for inspection; a side is never chosen automatically.

The `projects-api.compose-override` marker accepts only the
`docker-compose.single-node.yml` and `docker-compose.split-node.yml`
overrides. A missing or tampered marker, or ambiguous topology, interrupts the
resume; the tool does not choose a default profile.

If any project remains partial, Projects API and host-agent stay stopped. This
is intentional: new code and old stacks cannot operate at the same time. Fix
the cause and resume the same report.

## Operational migration rollback

Before the global `COMPLETE` marker, supported rollback is per project and part
of the tool itself: it removes the new tenant, returns Vector hashes to
`stub`, restores compose/env, and replaces the old directory from the archive.

If the entire change must be abandoned after projects have completed, keep the
runtime stopped and restore the complete external snapshot of the host,
PostgreSQL, and previous checkout. Do not start the new application on this
state or manually copy files between namespaces. Once the `COMPLETE` marker
exists, there is no runtime path to the old architecture; reverting is
exclusively operational recovery from the complete snapshot.

## Post-completion checks

Confirm:

```bash
docker ps --format '{{.Names}}'
```

For N projects there should be N Auth, PostgREST, and Nginx containers, but only:

```text
supabase-storage-global
supabase-imgproxy-global
```

Also run the active smoke tests described in
[`tests/smoke/README.md`](../../tests/smoke/README.md), check `summary.tsv`, and
retain the report until the change window is formally closed.
