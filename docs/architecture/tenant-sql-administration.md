# Tenant SQL administration

Studio SQL and Postgres-Meta always connect as `tenant_meta_<tenant UUID without dashes>`.
The database name is a routing address, not the security identity. Credentials are
HMAC-SHA256 derived from the backend-only Meta master password using the domain
`tenant-meta-v1:<UUID>`. Rotation requires privileged reprovisioning of tenant roles.
Neither the master password nor tenant SQL credentials are returned to the browser.

The role has no memberships, SUPERUSER, CREATEROLE, CREATEDB, or replication rights.
It owns non-extension application objects in `public`, can create application schemas,
and has tenant-local DML on Auth/Storage. BYPASSRLS supports administrative DML but
does not grant any access to another database. Auth/Storage schema ownership and
cluster DDL stay with the privileged lifecycle scripts, not arbitrary Studio SQL.
Application SECURITY DEFINER routines are reassigned to the tenant identity.

Privileged migration applies the identity to existing tenants and removes default
PUBLIC CONNECT from cluster databases, with explicit control-plane service grants.
Missing tenant identity/database fails the migration; no shared SQL identity is used
as a compatibility path. Creation, duplication, and restore provision the same SQL
contract before succeeding. Rename preserves the UUID role and database grants.
Legacy backups restored directly outside these lifecycle scripts must be reprovisioned
before SQL administration is enabled.

`platform_meta_admin` remains a server-only identity for bounded cluster lifecycle
primitives. It is never used for browser-supplied SQL or selected by a query parameter.

Validation on a disposable Docker PostgreSQL cluster:

```powershell
$env:TENANT_SQL_TEST_ADMIN_DSN='postgresql://supabase_admin:<test password>@127.0.0.1:55439/postgres'
python -m unittest discover -s tests/integration -p test_tenant_sql_isolation.py -v
```

The tests verify tenant DDL/DML, security-definer ownership, cross-database connections
and grants, shared-role impersonation/modification, cross-tenant session termination,
server program execution, rename, and slug reuse. Never run these tests on production:
their provisioning assertions intentionally harden PUBLIC grants in the disposable cluster.
