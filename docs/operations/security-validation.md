# Mandatory security boundary validation

Use disposable Docker containers, never a production DSN. Both runners require
explicit, already-present Linux images and fail if required checks are skipped.
They create random container names/ports and remove their containers and database
volumes, including on test failure. They do not mount installation env files or
internal reports.

```bash
python tools/run_auth_security_tests.py \
  --postgres-image servidor-db:latest --postgres-user supabase_admin \
  --studio-image studio-nginx:latest

python tools/run_functions_security_tests.py \
  --lifecycle-image servidor-projects-api:latest \
  --edge-image supabase/edge-runtime:v1.74.2
```

The SQL runner creates its own cluster: tenant isolation tests revoke cluster
PUBLIC grants, so accepting an external DSN would be unsafe. PostgreSQL readiness
is proven over TCP, not initdb's temporary Unix-socket server. The directory
fixture uses the production Lua/YAML/lock/sequence/HMAC code; Authelia's ID-export
subprocess is mocked and its sync destination acknowledges fixture snapshots.

CI has two non-optional jobs in `ci.yml`:

- `authorization-security-live`: builds the production Studio/OpenResty image,
  obtains PostgreSQL 15 explicitly, then runs API/agent authorization, revocation,
  canonical directory and two-tenant SQL isolation checks.
- `functions-security-live`: obtains the explicit Python/Edge Runtime images and
  checks the real Linux projection/lock contract and real runtime worker
  isolation, including credential changes on the next request.

The local smoke suite still has optional platform/load/DSN tests. A green smoke
run or Compose model validation is not a substitute for these mandatory runners.
The workflows are configured here; a local runner pass is not evidence that the
remote GitHub workflow has run.

## Remaining end-to-end acceptance

These boundary runners do **not** complete the full acceptance matrix. Still
required before claiming all P1 security integration is complete:

- real Authelia login/cookie and browser CSRF tests across same-site ports;
- Studio/Lua through real Traefik, API/authorizer and REST/GraphQL/Storage/Vectors;
- owner/admin/member/ex-member/disabled permissions with real Storage;
- physical create/duplicate/rename/rotate/restore/delete using the new projection
  contract, both single-node and split-node;
- externally reachable HTTPS directory callback and host-agent execution in both
  supported topologies, including certificate validation and outage/revocation.

Existing synthetic-cookie, mocked-upstream and projection-primitive tests prove
their respective boundaries, not these missing full-stack scenarios. No staging
installation or real user data is changed by the runners above.
