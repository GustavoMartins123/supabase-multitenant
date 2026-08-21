# Documentation index

This folder contains the technical documentation for `supabase-multitenant`.

The rule is simple: each topic must have one canonical source. `00-architecture.md` presents the overview and points to specialized documents. Operational or implementation details should not be copied across multiple files.

The current architectural state assumes **a host-agent instead of API-side Docker access**, **opaque API keys as public credentials**, and **global multi-tenant Storage/imgproxy**. Documents describing LifecycleProxy, the Docker socket in the Projects API, or per-project Storage/imgproxy must be treated as historical material and corrected, not as supported alternative paths.

## Start here

1. [System architecture](00-architecture.md)
2. [Control plane](architecture/control-plane.md)
3. [Control-plane migrations](architecture/control-plane-migrations.md)
4. [Project lifecycle](architecture/project-lifecycle.md)
5. [Host-agent](architecture/host-agent.md)
6. [Shared Storage, S3, and Storage Vectors](architecture/storage-vectors-lifecycle.md)
7. [Opaque API key operations](12-opaque-api-key-operations.md)
8. [OpenResty/Lua architecture](architecture/openresty-lua.md)
9. [Per-project Supabase Analytics](architecture/supabase-analytics.md)
10. [Multi-tenant Realtime authentication](09-multi-tenant-realtime-authentication.md)

## Installation and configuration

- [HTTPS setup](01-https-setup.md)
- [PostgreSQL connection limit](02-postgresql-connection-limit.md)
- [Supavisor connection limit](03-pooler-connection-limit.md)
- [Realtime connection limit](04-realtime-connection-limit.md)
- [Notification setup](06-notification-setup.md)
- [CRLF setup error](08-crlf-setup-error.md)

## Security

- [Repository disclosure policy](../SECURITY.md)
- [Authelia user management](07-authelia-user-management.md)
- [Global Postgres-Meta hardening](10-postgres-meta-hardening.md)
- [Postgres-Meta secret and connection rotation](11-project-secret-and-connection-rotation.md)
- [Opaque API key operations](12-opaque-api-key-operations.md)
- [Multiple opaque keys specification](specs/opaque-api-keys.md)

## Operations and troubleshooting

- [Common errors](05-common-errors.md)
- [Transitional shared Storage migration](architecture/shared-storage-migration.md)
- The current view of jobs, recovery, rename, backup, restore, and deletion is in [Project lifecycle](architecture/project-lifecycle.md).
- The current view of secrets, identity, settings, and collaboration is in [Control plane](architecture/control-plane.md).
- The schema application order, ledger, and forward-fix procedure are in [Control-plane migrations](architecture/control-plane-migrations.md).
- The physical Docker, lease, timeout, and reauthorization contract is in [Host-agent](architecture/host-agent.md).

## Canonical sources

| Topic | Canonical document |
| --- | --- |
| high-level view and boundaries | `00-architecture.md` |
| Python API, central schema, and authorization | `architecture/control-plane.md` |
| schema versioning, deployment order, and forward-fix | `architecture/control-plane-migrations.md` |
| creation, duplication, rename, rotation, backup, restore, and deletion | `architecture/project-lifecycle.md` |
| physical execution on the host, HMAC, lease, and closed commands | `architecture/host-agent.md` |
| multi-tenant Storage, S3, Vectors, and imgproxy | `architecture/storage-vectors-lifecycle.md` |
| one-way conversion of previous installations | `architecture/shared-storage-migration.md` |
| Lua modules, rewrites, and service-key cache | `architecture/openresty-lua.md` |
| Logflare, Vector, sources, and log access | `architecture/supabase-analytics.md` |
| JWT, tenant UUID, and replication slots | `09-multi-tenant-realtime-authentication.md` |
| safe Postgres-Meta fallback | `10-postgres-meta-hardening.md` |
| envelope encryption and rotation | `11-project-secret-and-connection-rotation.md` |
| opaque public keys, slots, optional expiration, migration, and incidents | `12-opaque-api-key-operations.md` |
| vulnerability disclosure for this project | `../SECURITY.md` |

## Rule for new changes

When a change alters real system behavior:

1. update the topic's canonical document first;
2. in `00-architecture.md`, change only the overview when necessary;
3. keep `README.md` and `LEIAME.md` as onboarding summaries, without creating a second specification;
4. avoid embedding large code snippets that change frequently;
5. prefer explaining contracts, invariants, boundaries, and states;
6. use links to code only as implementation references;
7. keep `project UUID`, `tenant UUID`, and `project ref` clearly separate;
8. do not document the old architecture as a fallback when the migration is one-way and the new runtime rejects it.
