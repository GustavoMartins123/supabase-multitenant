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

CI has three non-optional security jobs in `ci.yml`:

- `authorization-security-live`: builds the production Studio/OpenResty image,
  obtains PostgreSQL 15 explicitly, then runs API/agent authorization, revocation,
  canonical directory and two-tenant SQL isolation checks.
  It also runs real Authelia session/browser CSRF acceptance as described below.
- `functions-security-live`: obtains the explicit Python/Edge Runtime images and
  checks the real Linux projection/lock contract and real runtime worker
  isolation, including credential changes on the next request.
- The lifecycle CI job (physical matrix entry): builds the production lifecycle dependencies and
  runs the privileged physical script drill described below, including real
  Storage objects, Vectors, FDW SigV4 and Functions projection checks.

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
  --authelia-image authelia/authelia:4.39.20 --redis-image redis:8.2.2-alpine \
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

## Physical script lifecycle, Storage and Vectors

```bash
docker build -t servidor-db:latest servidor/volumes/db
docker build -t servidor-realtime:latest -f servidor/volumes/realtime/Dockerfile servidor
docker build -t servidor-projects-api:latest -f servidor/api-internal/Dockerfile servidor
docker tag servidor-projects-api:latest servidor-control-plane-migrations:latest
docker build -t servidor-key-authorizer:latest -f servidor/key-authorizer/Dockerfile servidor
docker build -t p1-executor:local -f tests/integration/fixtures/p1_executor.Dockerfile tests/integration/fixtures
# Obtain the exact service images listed in the lifecycle CI job first.
python tools/run_p1_lifecycle_tests.py --executor-image p1-executor:local
```

This drill needs an unused canonical Docker namespace throughout execution.
It refuses preexisting production container/network names before creating any
resources; do not run alongside an installation or another physical drill.
There is no installation-path or external-DSN option. Only tracked source from a
narrow allowlist is copied into a uniquely labelled engine-local volume. The
privileged executor uses the socket to run the real lifecycle scripts; none of
the HTTP services receives it. Cleanup checks the exclusive run label again
before removal and never performs global pruning.

The stack uses production-derived Compose services, database initialization,
migrations, authorizer, shared Storage data/control networks, Edge Runtime and
generated tenant gateways. Test-only changes concern logging, resource ownership
and runtime source mounts. Synthetic control-plane rows and opaque-key activation
are seeded with the real activation primitive before invoking the scripts.

The drill checks create, clone with data/new UUID, rename, internal JWT renewal,
backup, restore and **delete-files only**. Real database markers, private Storage
objects and vector data survive clone/rename and are recovered after mutation by
restore. The real FDW import exercises SigV4 through both proxies; valid signed
requests succeed, altered signatures and source credentials sent through the
clone gateway are rejected, including a forged tenant routing header. Every
mutating lifecycle checks the exact 0600 Functions projection against the real
worker. The surviving clone remains usable after file deletion of the other
project. Missing/invalid canonical gateway tokens fail before physical creation.

This is the **privileged script boundary**, not an authorized browser/API/agent
lifecycle. Delete does not exercise database/control-plane/Storage cleanup.
It does not simulate split-node transport or prove the Studio permission matrix.
Local passes and a configured CI job do not prove a remote CI execution.

## Full browser/API/agent acceptance

Build the physical drill images above with the exact executor tag
`codex-p1-executor:local`, plus the end-to-end dependencies listed in the
Lifecycle and authorization CI job (`studio-nginx:latest`, `codex-p1-browser:local`,
Authelia, patched Studio, Traefik and postgres-meta). Missing images are explicit
errors; the runner does not select alternate images or pull implicitly.

```bash
python tools/run_p1_end_to_end_tests.py --executor-image codex-p1-executor:local \
  --topology single --result .tmp-appdata/p1-e2e-single.json
python tools/run_p1_end_to_end_tests.py --executor-image codex-p1-executor:local \
  --topology split --result .tmp-appdata/p1-e2e-split.json
```

Both entries are mandatory CI tests without optional skips. The isolated stack
uses real Authelia logins, Redis sessions, cookies, Chromium certificate trust, production Lua,
Traefik file renderer and gateway plugin, API/authorizer, signed host-agent,
REST/GraphQL, Storage, pgvector and Edge Runtime. No mutation or authorization
handler is mocked. Data markers/objects/vectors are seeded only as test data;
projects, external keys, memberships, step-up and lifecycle are issued through
the real browser/API. Account IDs come from the production Authelia CLI.

The acceptance covers owner/admin/member/global-admin/outsider access,
immediate membership removal and disabled-account denial with existing cookies,
project/header mismatch, scoped external opaque keys and raw service-role JWT
rejection at the public gateway. It creates a private object, vector bucket and
index, follows a real Studio signed URL, and verifies clone with data/new UUID,
rename, internal JWT renewal, backup and restore. Restore is owner-only; full
delete is global-admin plus real step-up. Cleanup verifies project database,
control-plane row, object namespace, Functions projection, Realtime/Supavisor
metadata and two real replication slots; the other tenant stays usable. The
restricted metadata role remains NOREPLICATION; null, arbitrary and
cross-database slot requests and platform_app invocation are rejected.

API outage denies access even after credential warming. API and agent HTTPS
callbacks reject the wrong CA. A queued command is denied after actor revocation
or callback TLS failure, before physical mutation. Mount/environment inventory
checks API/Functions isolation, with read-only minimal Functions projections.

**Topology limits:** split is two disjoint Docker networks joined only by an
HTTPS link, on one Docker engine, not two physical machines or a WAN benchmark.
Production Compose overlays are checked; fixture service wiring is derived from
production and instrumented for disposal. The test-only unauthenticated
`/session-test` page is only a browser origin, never a protected API replacement.
GeoIP, analytics/logging collection and optional services are not acceptance
claims here. Resource fixtures bound Nginx/Erlang worker counts for the local
engine. Auth, Realtime websockets, Meta, logs and snippets are not cross-tenant
end-to-end claims of this particular drill; their separate tests do not imply
universal service coverage. Backup encryption and clean-install/upgrade drills
are also separate release requirements.

## Reproducible container measurements

Add `--benchmark` to either full acceptance command. Measurements start only
**after all validations pass**, against the surviving real tenant. Five workloads
(REST, GraphQL, Storage bucket listing, vector index listing and project listing)
run in the authenticated Chromium session. Each has 10 warmups, then three rounds
of 80 requests at closed-loop concurrency 1, 4 and 8. Body consumption is included
in latency; nearest-rank p50/p95/p99, status/error counts, elapsed time and
throughput are reported. Three idle Docker stats samples and periodic loaded
samples report CPU/memory; exact image IDs and engine CPU/memory are recorded.
Warmup failures, timeouts, missing stats and HTTP errors are explicit failures,
not dropped samples, retries or cached authorization substitutes.

This small synthetic workload measures local overhead, not production capacity
or physical split-node latency. Different concurrency levels are not a before/
after optimization comparison. Raw JSON/log evidence remains local in ignored
`.tmp-appdata`; logs may contain synthetic signed URLs and must not be published.
No installation, host certificate trust, real account or preexisting container
is changed. A configured workflow is not evidence of a remote CI execution.

## Directory scaling microbenchmark

```bash
python tools/run_directory_benchmark.py --studio-image studio-nginx:latest \
  --result .tmp-appdata/p1-directory.json
```

This separate microbenchmark runs the actual snapshot, YAML parser and filesystem
locks in an engine-local tmpfs with 25, 100 and 500 synthetic persisted identities,
five rounds each. It counts real YAML parses and reports median elapsed time. It
does not replace the authenticated HTTP benchmark or measure maximum capacity.

The measured quadratic path reread/parsed the entire identity YAML once per user.
The batch resolver now acquires the identity lock once and indexes a single fresh
document per snapshot. There is no cross-request cache: edits are read again on
the next request, and invalid/missing/duplicate identities fail explicitly rather
than substituting an empty identity document. New identities still use the
canonical Authelia generate/export operation under the same lock. The mandatory
auth runner checks the real batch reader, fresh edits and fail-closed cases;
the full browser drill checks actual CLI provisioning and immediate revocation.

On the local 16-CPU Linux Docker engine, the initial five-round measurement moved
the 500-user median from 4,903 ms / 501 YAML parses to 22 ms / 2 parses. This is a
directory-snapshot result, not a claim of the same speedup for all HTTP requests.
The pre-optimization full HTTP run after the Fernet clock correction completed
3,600 requests with zero errors. Fernet refreshes the canonical wall clock before
reading seconds; future-token rejection and expiry remain strict and are checked
with real Python-issued tokens in OpenResty. Raw evidence remains private/local.

### Session stability validation with Redis

Before Redis, some full drills passed functional acceptance but returned 401
in benchmark warmup while the browser cookie remained present. Those runs failed;
they were not reauthenticated or removed from the evidence. A separate exact-source
Go reproduction exposed mutable session-key ownership in Authelia's memory
provider; it did not alone prove the entire request-level causal chain.

Redis is now the mandatory session backend, not an optional recovery path. The
full drill stops Redis and requires the canonical protected API to return 401
with JSON `authentication required`. It then restarts Redis and Authelia and
requires the original browser session to work without relogin. Unauthenticated
Redis access is denied, its port is unpublished and its only network is the
private session network. Configuration and cutover are documented in
[OpenResty/Lua architecture](../architecture/openresty-lua.md#browser-sessions).

Local Linux Docker validation on 2026-10-03 passed all 15 acceptance categories
in each topology, followed sequentially by the bounded HTTP benchmark:

| Topology | Measured requests | HTTP errors | p50 at concurrency 1, across workloads | Throughput at concurrency 8, across workloads |
| --- | ---: | ---: | --- | --- |
| single | 3,600 | 0 | 44.4–56.8 ms | 22.31–26.83 requests/s |
| split | 3,600 | 0 | 44.8–57.9 ms | 22.66–26.47 requests/s |

Each run also passed all 50 warmup requests. The earlier unexpected session 401
was not reproduced in these two clean runs. Redis used approximately 5 MiB in
the collected load samples, within its 384 MiB container limit. The HTTP results
are not a speedup claim or maximum-capacity estimate; the independently measured
directory improvement remains a 500-user snapshot result. Two earlier Redis
validation attempts failed because the fixture expected the wrong outage status
and then the wrong JSON spelling; those assertions were corrected to match the
canonical denial, without weakening it or adding retries.

Browser/API/agent acceptance passed for these local disposable container topologies.
Split still means disjoint networks on one engine, not a verified physical WAN.
No remote CI run, universal cross-tenant coverage for every optional service,
production deployment or availability guarantee is claimed. Raw evidence remains
private in ignored `.tmp-appdata` files.
