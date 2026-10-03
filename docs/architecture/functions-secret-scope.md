# Functions: tenant-only credentials

The shared Functions container no longer receives root PostgreSQL password,
cluster DSN, global JWT secret or global anon/service keys. Its only declared
application setting is `VERIFY_JWT`, which must be explicitly true or false.
Production should keep JWT verification enabled.

Every request requires the exact `X-Project-Ref` supplied by its tenant gateway.
There is no query `ref` alias, normalization into a different identity, or
missing-tenant path using a global secret. Configuration is read on every request
instead of authorizing with an mtime cache. Required credentials must be unique,
canonical entries; absent/malformed configuration returns 503. JWT verification
accepts HS256 with that tenant's secret. Function names cannot traverse paths or
invoke the supervisor `main` service.

The worker environment has only that tenant's API URL, anon/service keys, JWT
secret and project ref. `test_functions_tenant_boundary.py` verifies legitimate
calls for two tenants, crossed JWT denial, missing/query identity denial and
supervisor/path rejection in the real Edge Runtime Docker image.

**Remaining SEC-09 work:** the supervisor still mounts the projects directory
read-only to resolve tenant credentials. Replace it with an exact-allowlist
projection or a tenant-scoped credential interface, kept consistent through
create/duplicate/rename/rotate/restore/delete. This must be done as one lifecycle
contract, not by adding a second credential lookup or stale-config path. This
change reduces global-secret exposure but does not complete that remaining
all-tenants filesystem isolation acceptance criterion.
