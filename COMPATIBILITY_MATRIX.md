# Compatibility matrix

Which upstream versions each release of `supabase-multitenant` is built and
tested against. One row per moving part; the platform row is the canonical
`VERSION` at the repository root and is enforced by
`tools/check-version-parity.py`.

> This project is an **unofficial** self-hosted distribution. It is not
> affiliated with, sponsored by, or endorsed by Supabase. Version pins here
> describe what this repository builds, not what upstream supports.

## Current release

| Component | Pinned version | Where the pin lives |
| --- | --- | --- |
| **Plataforma** | `0.13.0-alpha` | `VERSION` |
| Projects API (runtime) | `0.13.0-alpha` | `servidor/api-internal/app/version.py` |
| OpenAPI document | `0.13.0-alpha` | `docs/api/openapi.json` (`info.version`) |
| Dart client | `0.13.0-alpha` | `studio/projects_api_client/pubspec.yaml` |
| Studio app (Flutter) | `0.13.0-alpha+1` | `studio/seletor_de_projetos/pubspec.yaml` |

## Upstream Supabase components

| Component | Pinned version | Where the pin lives | Patched here |
| --- | --- | --- | --- |
| Supabase Studio | commit `20290c71bdc48bef1720bfe7d292f3b9e6154f7d` | `studio/.env.example` (`SUPABASE_STUDIO_COMMIT`), `studio/studio-slug/Dockerfile` | yes — `studio/studio-slug/studio-project-context.patch` |
| Postgres (projects) | `supabase/postgres:15.14.1.142` | `servidor/volumes/db/Dockerfile` | no |
| Realtime | `v2.112.3` | `servidor/volumes/realtime/Dockerfile` (`REALTIME_VER`) | yes — 3 `.ex` + 1 `.exs` |
| Realtime `pg_delta` | commit `d706336a6772318e92db419eda5a5ea51123510e` | `servidor/volumes/realtime/Dockerfile` (`PG_DELTA_COMMIT`) | no |
| Storage API | `supabase/storage-api:v1.61.12` | `servidor/.env.example` (`STORAGE_IMAGE`) | no — official image, unpatched by design |
| imgproxy | `darthsim/imgproxy:v4.0.11` | `servidor/.env.example` (`IMGPROXY_IMAGE`) | no |
| Supavisor | `supabase/supavisor:2.9.7` | `servidor/docker-compose.yml` | no |
| Edge Runtime | `supabase/edge-runtime:v1.74.2` | `servidor/docker-compose.yml` | no |
| Postgres-Meta | `supabase/postgres-meta:v0.96.1` | `servidor/docker-compose-api.yml` | no |
| Logflare / Analytics | `v1.47.1` | `servidor/volumes/analytics/Dockerfile` (`LOGFLARE_VER`) | yes — 2 `.ex` + 1 `.exs` |

## Infrastructure components

| Component | Pinned version | Where the pin lives |
| --- | --- | --- |
| Traefik | `traefik:v3.7.6` | `servidor/traefik/docker-compose.yml` |
| Vector | `timberio/vector:0.53.0-alpine` | `servidor/docker-compose.yml` |
| OpenResty (Studio gateway) | `openresty/openresty:1.31.1.1-1-bookworm-fat` | `studio/Dockerfile` |
| Nginx (data-plane proxy) | `nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim` | `servidor/.env.example` (`STORAGE_DATA_PLANE_PROXY_IMAGE`), `servidor/traefik/docker-compose.yml` |
| Authelia | `authelia/authelia:4.39.20` | `studio/docker-compose.yml` |
| Postgres (control plane) | `postgres:16.13-alpine3.23` | `studio/postgres/Dockerfile` |
| Python (API image) | `python:3.12.13-slim` | `servidor/api-internal/Dockerfile` |
| Elixir / OTP (Realtime) | `1.18` / `27.3` on `bookworm-20250929-slim` | `servidor/volumes/realtime/Dockerfile` |
| Elixir / OTP (Analytics) | `1.19.5` / `27.3.4.6` on `trixie-20260112-slim` | `servidor/volumes/analytics/Dockerfile` |

## Toolchain used to produce release artifacts

| Tool | Version | Used for |
| --- | --- | --- |
| Python | `3.12` | API, host-agent, `tools/`, CI |
| Flutter / Dart SDK | `stable`, Dart `>=3.4.0 <4.0.0` | `studio/seletor_de_projetos` |
| openapi-generator | `7.12.0` | `tools/generate_dart_client.sh` |
| gitleaks | `8.28.0` | secret scanning in CI |
| Lua | `5.4` (`luac -p`) | OpenResty syntax gate |

## Patched upstream surface

A patched file is a rebase liability: bumping the upstream version above can
silently drop or conflict with these. Any bump must re-apply and re-test them.

| File | Upstream project | Purpose |
| --- | --- | --- |
| `studio/studio-slug/studio-project-context.patch` | Supabase Studio | per-tab project context |
| `servidor/volumes/realtime/replication_connection.ex` | Realtime | multi-tenant replication slots |
| `servidor/volumes/realtime/metrics_controller.ex` | Realtime | per-tenant metrics exposure |
| `servidor/volumes/realtime/router.ex` | Realtime | tenant routing |
| `servidor/volumes/realtime/tenant_controller_test.exs` | Realtime | test retargeted to the patched behavior |
| `servidor/volumes/analytics/dialect_translation.ex` | Logflare | SQL dialect translation |
| `servidor/volumes/analytics/sql.ex` | Logflare | query building |
| `servidor/volumes/analytics/translation_smoke.exs` | Logflare | smoke over the translation patch |

The Studio patch is applied with `git apply --check` before `git apply`
(`studio/studio-slug/Dockerfile:34-35`), so an upstream commit that invalidates
it fails the build instead of producing a silently unpatched image. The Elixir
files are `COPY`-overwrites and have **no such guard** — they overwrite
whatever upstream ships, so a bump can silently revert upstream fixes or drop
new call sites. Treat them as the highest-risk part of any bump.

## Update procedure

1. Change `VERSION` at the root.
2. Change `servidor/api-internal/app/version.py` to match.
3. Run `python tools/export_openapi.py` to regenerate `docs/api/openapi.json`.
4. Run `python tools/check-version-parity.py --fix` to propagate to the Dart
   client, the Flutter pubspec, the generator script, and this file.
5. Run `python tools/check-version-parity.py` (no flag) to confirm it is clean.
6. Update this matrix's upstream rows if any pin moved.
7. Follow [docs/operations/upgrades.md](docs/operations/upgrades.md) to roll out.
