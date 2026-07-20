# Storage Vectors lifecycle

## Ownership

Storage Vectors is part of the project lifecycle. It is not an optional manual
bootstrap performed after project creation.

The implementation is split by responsibility:

- `servidor/volumes/db/create_template.sh`
  - installs and validates pgvector before `_supabase_template` is created;
  - guarantees every database created from the template has pgvector.
- `servidor/generateProject/lib/vector_lifecycle.sh`
  - owns shared validation, SigV4 generation, Storage health checks, wrapper
    cleanup and wrapper reconciliation.
- `servidor/generateProject/operations/setup_vector_bucket_wrapper.sh`
  - owns the idempotent setup of one bucket's S3 Vectors FDW;
  - is called by duplicate/rename reconciliation;
  - represents an operation, not a second project bootstrap path.
- `generate_project.sh`, `duplicate_project.sh` and `rename_project.sh`
  - remain stable public entrypoints used by the Projects API;
  - delegate to implementations under `lib/`.

Tests live under `tests/smoke/`; no test or migration script is generated inside a
project directory.

## Create

A clean Postgres initialization installs pgvector before creating
`_supabase_template`. Project creation then:

1. creates `_supabase_<project>` from the validated template;
2. generates an exclusive SigV4 access/secret pair;
3. renders that pair into the project's `.env` with mode `0600`;
4. starts the tenant Storage API with the pgvector provider;
5. waits for Storage health and calls the real `ListVectorBuckets` endpoint;
6. rolls back containers, tenants, database and files if validation fails.

No wrapper exists yet because wrapper names depend on a vector bucket name.

## Install wrapper from Studio

The upstream Studio uses the fixed endpoint `/api/get-s3-keys`. OpenResty resolves
the tab's project from the URL (`X-Studio-Project-Ref`) and internally routes the
request to:

```text
/api/projects/<project>/storage/s3-keys
```

The Projects API requires project-admin or global-admin access and returns only
the selected project's SigV4 pair with `Cache-Control: no-store`.

When Studio submits its wrapper SQL through postgres-meta, the compatibility
layer replaces the single-node `host.docker.internal` endpoint only for SQL that
contains both `s3_vectors_fdw_handler` and `s3_vectors_fdw_validator`. The final
FDW endpoint is:

```text
http://supabase-storage-<project>:5000/vector
```

Normal SQL queries are not modified.

## Duplicate

A clone never reuses the original project's SigV4 credentials.

- a new pair is generated for the clone;
- copied S3 Vectors FDWs and their Vault secrets are removed from the cloned DB;
- vector data follows the selected copy mode;
- after the cloned Storage is healthy, wrappers are recreated only for buckets
  returned by the clone's real `ListVectorBuckets` response;
- temporary dumps use `mktemp` and are removed by traps;
- failed clones remove their containers, Realtime/Supavisor tenants, database,
  directory and temporary files.

## Rename

Rename preserves the project's SigV4 pair because it is the same tenant. The
project database is renamed and the Storage container DNS name changes. After
the new Storage is healthy, every existing vector-bucket wrapper is reconciled so
its `endpoint_url` points to the new tenant container. Rollback restores the old
name and rebinds wrappers to the old endpoint when necessary.

## Rotate and delete

JWT key rotation does not rotate or erase SigV4 credentials. SigV4 is independent
from `anon` and `service_role` JWTs.

Project deletion already removes the complete project database and project
directory. The pgvector tables, FDWs and Vault secrets are database-owned, so they
are deleted with the database; file-backed Storage data and the project `.env`
are deleted with the project directory.

## Removed compatibility paths

The old root-level scripts below were removed to avoid two competing bootstrap
flows:

```text
servidor/generateProject/enable_vector_storage.sh
servidor/generateProject/setup_vector_bucket_wrapper.sh
```

There is one lifecycle path for create/duplicate/rename and one organized,
idempotent per-bucket operation under `operations/`.
