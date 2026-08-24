# HTTPS setup

Traefik has a production TLS profile driven by environment variables. The dynamic configuration renderer (`render_dynamic_config.py`) decides between HTTP-only routers and `websecure` routers with automatic HTTP→HTTPS redirect, and fails closed when the declared protocol and the TLS profile disagree or when certificates are missing. Manual edits to `traefik.yml` or to generated routers are no longer part of the procedure.

## Profile variables (`servidor/.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `TRAEFIK_ENABLE_TLS` | `false` | When `true`, every service router moves to `websecure` with a certificate source, and port 80 only answers with a permanent redirect (plus the edge-protection deny routers). |
| `TRAEFIK_TLS_MODE` | `file` | `file` reads `tls.crt`/`tls.key` from `servidor/traefik/certs/traefik/`; `acme` uses Let's Encrypt through the `letsencrypt` resolver. |
| `TRAEFIK_ACME_EMAIL` | placeholder | Required (non-placeholder) when `TRAEFIK_TLS_MODE=acme`. |
| `TRAEFIK_HTTPS_PORT` | `443` | Host port published for `websecure`; also used in the redirect target. |
| `SERVER_PROTO` | filled by setup | Declared platform scheme. If it is `https` while `TRAEFIK_ENABLE_TLS` is not `true`, the renderer raises and no new configuration is written. |

Port `443` is always published by the Traefik compose file; without `TRAEFIK_ENABLE_TLS=true` nothing listens with TLS on it and requests are closed without routes.

## Fail-closed behavior

The watcher container re-renders routes continuously. With `TRAEFIK_ENABLE_TLS=true`:

- `TRAEFIK_TLS_MODE=file` requires `servidor/traefik/certs/traefik/tls.crt` and `tls.key` to exist at render time; otherwise rendering fails, the healthcheck of the watcher goes down, and Traefik keeps serving the last valid configuration;
- `TRAEFIK_TLS_MODE=acme` requires a real `TRAEFIK_ACME_EMAIL`;
- `SERVER_PROTO=https` without `TRAEFIK_ENABLE_TLS=true` aborts rendering with an explicit error instead of silently serving plain HTTP.

## Mode 1 — `file` (self-signed or internal CA, LAN/IP deployments)

1. Generate the pair into `servidor/traefik/certs/traefik/`, including the server IP in SAN:

    ```bash
    mkdir -p servidor/traefik/certs/traefik
    openssl req -x509 -newkey rsa:4096 -sha256 -days 825 -nodes \
      -keyout servidor/traefik/certs/traefik/tls.key \
      -out servidor/traefik/certs/traefik/tls.crt \
      -subj "/CN=supabase-local" \
      -addext "subjectAltName=IP:<SEU_IP>,DNS:seu.dominio.local"
    chmod 600 servidor/traefik/certs/traefik/tls.key
    ```

2. In `servidor/.env`: `TRAEFIK_ENABLE_TLS=true`, `TRAEFIK_TLS_MODE=file`.
3. Recreate Traefik:

    ```bash
    docker compose -f servidor/traefik/docker-compose.yml up -d --force-recreate
    ```

4. Validate: `curl -k https://<SEU_IP>/<project_ref>/rest/v1/` must answer from the project Nginx, and `curl http://<SEU_IP>/<project_ref>/rest/v1/` must return a permanent redirect.

## Mode 2 — `acme` (Let's Encrypt, public domain)

Prerequisites: registered domain pointing to the server, propagated DNS, ports 80 and 443 open, and `acme.json` writable only by the owner:

```bash
chmod 600 servidor/traefik/acme.json
```

Then in `servidor/.env`: `TRAEFIK_ENABLE_TLS=true`, `TRAEFIK_TLS_MODE=acme`, `TRAEFIK_ACME_EMAIL=you@example.com`, and recreate Traefik as above. Certificates are obtained through the HTTP-01 challenge on entrypoint `web` and stored in `/acme.json`.

## Point the Studio at HTTPS

With TLS enabled on the data plane, update `studio/.env` so the management interface targets the same scheme:

```text
SERVER_DOMAIN=https://<server-ip-or-domain>
BACKEND_PROTO=https
```

And recreate Studio:

```bash
docker compose -f studio/docker-compose.yml up -d --force-recreate
```

## Optional transport hardening

- **HSTS**: add `Strict-Transport-Security` to the `customResponseHeaders` of the `security-headers` middleware in `servidor/traefik/middlewares.yml`. Start without `preload` and with a short `max-age` while validating; `preload` makes rollback to HTTP impossible for a year.
- **TLS floor**: a `tls.options.default` block (minimum version, cipher suites) can be added to the dynamic directory; apply it only after confirming that no legacy client needs the relaxed defaults.

## Redirect precedence

The generated `force-https` router uses priority `150` on entrypoint `web`: above the generic catch-all (`100`) so unknown paths are redirected, below the scanner/deny routers (`>= 1900`) so hostile traffic keeps being classified and banned over plain HTTP instead of being bounced with a redirect.
