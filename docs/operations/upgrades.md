# Upgrades and rollback

How to move a running installation from one platform version to the next.
The canonical version is `VERSION` at the repository root; what each version is
built against is in [`COMPATIBILITY_MATRIX.md`](../../COMPATIBILITY_MATRIX.md).

This project is alpha and single-maintainer. The procedure below assumes an
operator sitting in front of the host, not an automated pipeline.

## What an upgrade touches

Upgrades are not uniform: three layers move independently and fail differently.

| Layer | What it is | Blast radius | How it is applied |
| --- | --- | --- | --- |
| Control plane | Projects API, host-agent, control-plane schema, Studio gateway | all projects at once | `bash setup.sh` + `bash start.sh` on the host |
| Global data plane | Postgres, Supavisor, Realtime, Storage, imgproxy, Edge Runtime, Postgres-Meta, Analytics, Traefik, Vector | all projects at once | `docker compose ... up -d` from `start.sh` |
| Per-project data plane | that project's Nginx, Auth, PostgREST | one project | `POST /api/projects/{name}/recreate-services` |

Only the third layer can be staged. **Anything in the first two layers is
inherently all-or-nothing on a single host** — the canary strategy below buys
you a rehearsal, not a partial blast radius. Do not describe a control-plane
upgrade to users as "canaried".

## Version numbering

- `VERSION` is `major.minor.patch[-prerelease]`, no build metadata.
- While the project is `-alpha`, minor bumps may break contracts. Say so in
  `CHANGELOG.md` rather than pretending semver guarantees hold.
- The Flutter app in `studio/seletor_de_projetos` carries `+N` build metadata
  on top of the same core version. Nothing else may.
- A release candidate is `X.Y.Z-rc.N`, promoted to `X.Y.Z` only after the
  rollout below completes on a real installation.

Every derived location is enforced by `tools/check-version-parity.py`, which
runs in CI. To change the version:

```bash
# 1. edit VERSION and servidor/api-internal/app/version.py by hand
python tools/export_openapi.py          # regenerates docs/api/openapi.json
python tools/check-version-parity.py --fix
python tools/check-version-parity.py    # must exit 0
```

## Before the tag: release candidate

Do not tag before all of these pass on the RC commit.

1. `python -m pytest tests/smoke -q` — green.
2. CI green on both workflows, including `migrations-live` (real Postgres) and
   the `flutter` job.
3. `python tools/check-version-parity.py` — 0 errors.
4. `python tools/check-env-contract.py --compose` — 0 errors.
5. `COMPATIBILITY_MATRIX.md` updated if any upstream pin moved.
6. `CHANGELOG.md` has a section for the version, with breaking changes first.
7. A **fresh install** from the RC works: clean host, `bash setup.sh`, create a
   project, sign in through Studio, write and read a row through PostgREST.
   A fresh install that fails is a release blocker even if upgrades work — new
   users only ever see this path.
8. An **upgrade** from the previous released version works, using the rollout
   below on a staging installation.

## Rollout

### Stage 0 — restore point and backup

Not optional. The control-plane schema uses forward-fix only; there is no
`downgrade` path (see
[control-plane migrations](../architecture/control-plane-migrations.md)).
A bad migration is recovered from backup, not reverted.

- Take a restore point for every project you are about to touch, or a full
  `backup_project` for the canary at minimum.
- Dump the control-plane database separately — restore points cover project
  data, not the control plane.
- Record the current image digests (`docker compose images`) and the current
  `git rev-parse HEAD`. This is your rollback target.

### Stage 1 — canary (1 project)

Pick the least critical project. Prefer one you own.

1. Upgrade the control plane and global data plane on the host
   (`git checkout <tag>`, `bash setup.sh`, `bash start.sh`).
2. Recreate the canary project's services:
   `POST /api/projects/{canary}/recreate-services` with the services that
   actually changed — not all of them.
3. Run the health gate below.
4. Sit on it for at least one full backup cycle before continuing. Most
   failures in this stack are not immediate: replication slots, certificate
   renewal, and log shipping fail hours later.

### Stage 2 — percentage (25%)

Recreate services for a quarter of the remaining projects, chosen to cover the
shapes you actually run (a project with Storage Vectors, one with Edge
Functions, one with custom capacity profile). Health gate after each batch.

### Stage 3 — all

Remaining projects. Health gate after the batch, then again the next day.

## Health gate

Run this between every stage. **There is no aggregated per-project health
endpoint yet** — that is Fase 3 in the plan. Until it exists, the gate is the
following manual checks; do not skip them on the assumption that green
containers mean a healthy tenant.

| Check | How | Pass condition |
| --- | --- | --- |
| API liveness | `GET /healthz` on the Projects API | `{"ok": true}` |
| Container state | `project_container_state` for the project, or `GET /api/projects/{name}` in Studio | every container `running`, no restart loop |
| Migrations | control-plane migration ledger | applied version matches the release, no partial row |
| Auth | sign in to Studio through Authelia | session issued, no `needs_admin=true` |
| PostgREST | authenticated read through the project's public URL | 200, expected rows |
| Storage | upload and signed-download one object in the project's bucket | both succeed, object is in the right tenant |
| Realtime | subscribe to one channel and write a row | event delivered |
| Supavisor | connect through the pooler port | connection accepted |
| Keys | `GET /api/projects/{name}/keys` | slots present, no key past expiry |
| Logs | Logflare filtered by the project | events arriving after the restart |

Any red check stops the rollout at that stage. Do not proceed to the next
percentage to "see if it is just that one project".

## Rollback

Rollback differs per layer. Decide which layer broke before acting.

**Per-project data plane** — cheapest. Check out the previous tag and rerun
`recreate-services` for that project. The project's data was never touched.

**Global data plane** — check out the previous tag and rerun `bash start.sh`.
Images are pinned in the matrix, so the previous versions are still pullable.
Watch for state written in the new format: Realtime tenants and Storage tenant
rows are shared, and a new version may have rewritten them.

**Control plane** — the expensive one. If the release included a migration:

1. Stop the Projects API and the host-agent so nothing writes.
2. Restore the control-plane database from the Stage 0 dump.
3. Check out the previous tag and rerun `bash setup.sh` + `bash start.sh`.
4. Restore project restore points only for projects whose data actually
   diverged — restoring a project unnecessarily loses writes made since.

If the release included no migration, checking out the previous tag and
restarting is enough; skip the database restore.

**Rotated secrets are not rolled back by any of the above.** If the upgrade
rotated keys or connection secrets, the old values are gone. Roll forward with
a new rotation instead of trying to restore the previous ones.

## After the rollout

1. Tag the release and push the tag.
2. Move the `CHANGELOG.md` section from "Não lançado" to the version.
3. Update `COMPATIBILITY_MATRIX.md` if the rollout revealed a pin that had to
   move.
4. Write down what the health gate caught. The gate is only as good as the
   failures it has already seen.
