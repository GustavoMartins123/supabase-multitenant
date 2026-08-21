# Control-plane migrations

The `postgres` database schema — users, projects, jobs, host-agent intents, opaque keys, collaboration, and restore points — belongs to versioned `.sql` files in `servidor/api-internal/app/migrations`.

Starting or restarting the Projects API does not change the schema. The request-serving process only checks the applied version and fails closed when the database is behind the image.

## Boundaries

| Layer | Owner | When it runs |
| --- | --- | --- |
| Cluster objects: internal schemas, `_supabase_storage`, `_supabase_template`, `meta_trap`, `meta_guest`, pgvector | `servidor/volumes/db/create_template.sh` | once, during Postgres initdb |
| Control-plane tables, indexes, constraints, triggers, and seeds | `app/migrations/NNNN_*.sql` | every deployment, through the privileged command |
| `key_authorizer` database identity | `app/control_plane_roles.py`, called by the same command | every deployment |
| Compatibility check | `verify_control_plane_schema()` at API startup | every boot, without writing |

The historical bootstrap no longer creates any control-plane table. A clean installation is identical to an existing migrated installation.

## Ledger

`control_plane_schema_migrations` records, per version: name, SHA-256 file checksum, timestamp, `current_user`, and duration.

The checksum prevents retroactive editing. Changing an already-applied file makes `apply` and boot reject it explicitly because the database would no longer match the repository's description.

## Commands

The command runs inside the Projects API image with the administrative DSN:

```bash
docker compose -f docker-compose-api.yml -f docker-compose.single-node.yml \
  --env-file .env run --rm control-plane-migrations
```

The three modes:

```bash
python -m app.schema_migrations apply    # applies pending migrations and provisions identities
python -m app.schema_migrations status   # lists the ledger against the image files
python -m app.schema_migrations verify   # verifies without changing anything; exits 3 if pending
```

`apply` takes an advisory lock so simultaneous migrators do not conflict, and uses a 30-second `lock_timeout`: if the previous process still holds a table lock, deployment fails with a diagnostic instead of hanging indefinitely.

Each version runs in its own transaction together with its ledger entry. A failed version is fully rolled back and nothing is marked as applied.

## Deployment order

The ephemeral `control-plane-migrations` service performs this step inside Compose:

```text
supabase-db healthy
        │
        ▼
control-plane-migrations  (administrative DSN, applies pending NNNN, provisions key_authorizer)
        │ service_completed_successfully
        ├────────────────► key-authorizer
        └────────────────► projects-api  (verifies the version and serves traffic)
```

`start.sh` waits for the database to become healthy before starting this Compose. `key-authorizer` and `projects-api` start only after the migrator succeeds; if it fails, neither starts.

The host-agent continues to wait for the tables to exist (`--check-schema`), now published by the migrator rather than by API boot.

## Add a migration

1. create `NNNN_short_name.sql` with the next four-digit number, without gaps in the sequence;
2. write idempotent DDL (`IF NOT EXISTS`, `DO $$` with checks in `pg_constraint`/`pg_trigger`) because the same version must work across installations in different states;
3. backfill data **before** tightening `NOT NULL` or adding `CHECK`, and remember that `NULL IN (...)` returns `NULL`;
4. grant privileges for the tables it creates inside the migration itself;
5. exercise both paths with `tests/integration/test_control_plane_migrations_postgres.py`.

Never edit a file already applied in production. Renaming or reordering versions also breaks the ledger.

## Rollback and forward-fix

There is no `downgrade`. Reverting a schema with live data can silently lose information, and the ledger does not describe the inverse of a migration.

The procedure is always to move forward:

1. **Failure during `apply`**: the version was rolled back by the transaction and did not enter the ledger. Fix the file, which has not been applied anywhere yet, and run `apply` again.
2. **An applied version proved incorrect**: write a new version that fixes the state with the same idempotency care. The original file remains intact in history.
3. **Old image against a new database** — a release rollback: boot records `database ahead of this image` and continues serving because the schema is forward-compatible. If the old image needs a column removed by the new version, advance the image rather than reverting the database.
4. **New image against an old database**: boot rejects with the list of missing versions. Run `apply` before starting the API.

Restoring a backup of the `postgres` database remains the only way to move the schema back in time, and it moves the data back with it.

## Installations predating migrations

The first `apply` run on an existing installation applies the three current versions to the schema already created by boot. The creations are no-ops and only missing convergence remains, all in `0001`:

- `jobs.action` and `jobs.updated_at` become `NOT NULL`. Jobs created before the `action` column did not record the operation and receive the `unknown` marker, which belongs to neither an executable action nor the idempotent-action list;
- `jobs` receives the `CHECK` constraints for `progress`, `total_steps`, and `attempt`, which existed only on installations created from scratch.

Before this, the boot calculation of `is_idempotent` failed on an installation with jobs created before the `action` column because `NULL IN (...)` violates the column's `NOT NULL`. The backfill now happens before recalculation.
