# Mandatory security boundary validation

Use disposable Docker containers, never a production DSN. The runners require
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
  It also runs real Authelia session/browser CSRF acceptance as described below.
- `functions-security-live`: obtains the explicit Python/Edge Runtime images and
  checks the real Linux projection/lock contract and real runtime worker
  isolation, including credential changes on the next request.

The local smoke suite still has optional platform/load/DSN tests. A green smoke
run or Compose model validation is not a substitute for these mandatory runners.
The workflows are configured here; a local runner pass is not evidence that the
remote GitHub workflow has run.

## Real Authelia session and browser CSRF

```bash
docker build -t session-browser:local -f tests/integration/fixtures/studio_session_browser.Dockerfile tests/integration/fixtures
docker build -t session-runtime:local -f tests/integration/fixtures/studio_session_runtime.Dockerfile tests/integration/fixtures
python tools/run_studio_session_tests.py \
  --studio-image studio-nginx:latest \
  --authelia-image authelia/authelia:4.39.20 \
  --runtime-image session-runtime:local --browser-image session-browser:local \
  --ui-image ghcr.io/gustavomartins123/multitenant-studio:20290c7-context-v3
```

The runner creates a unique network/volume, generates a synthetic account and CA
with the production configuration tool, and runs the production nginx config,
entrypoint, Lua guards and Authelia HTTPS/authentication proxy. Current Lua source
is merged into the image without masking installed dependencies. Chromium trusts
only this disposable CA using its normal NSS trust database: no certificate bypass
or change to the host trust store. The browser logs in through real Authelia and
proves that its issued Secure/HttpOnly cookie authenticates a JSON mutation; an
HTML form on the same hostname at another port sends that cookie but gets 403.
The legitimate origin still succeeds and an anonymous context gets 401.

The protected test-only mutation probe echoes the actor verified by Authelia; it
does not replace or prove any project/Storage mutation. This closes the real-cookie
CSRF boundary, not the full project permission/lifecycle acceptance below. Private
installation env files are never mounted; cleanup failure is an explicit error.

## Remaining end-to-end acceptance

These boundary runners do **not** complete the full acceptance matrix. Still
required before claiming all P1 security integration is complete:

- Studio/Lua through real Traefik, API/authorizer and REST/GraphQL/Storage/Vectors;
- owner/admin/member/ex-member/disabled permissions with real Storage;
- physical create/duplicate/rename/rotate/restore/delete using the new projection
  contract, both single-node and split-node;
- externally reachable HTTPS directory callback and host-agent execution in both
  supported topologies, including certificate validation and outage/revocation.

Existing synthetic-cookie, mocked-upstream and projection-primitive tests prove
their respective boundaries, not these missing full-stack scenarios. No staging
installation or real user data is changed by the runners above.
