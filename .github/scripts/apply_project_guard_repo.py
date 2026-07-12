from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path}: {old[:80]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


traefik = Path("servidor/traefik/traefik.yml")
replace_once(
    traefik,
    '''experimental:
  plugins:
    fail2ban:
      moduleName: "github.com/tomMoulard/fail2ban"
      version: "v0.8.9"
    geoblock:
''',
    '''experimental:
  localPlugins:
    supabaseguard:
      moduleName: "github.com/GustavoMartins123/supabaseguard"
  plugins:
    geoblock:
''',
)

middlewares = Path("servidor/traefik/middlewares.yml")
replace_once(
    middlewares,
    '''      entryPoints:
        - websecure
''',
    '''      entryPoints:
        - web
''',
)
replace_once(middlewares, '''      tls: {}
''', "")
replace_once(
    middlewares,
    '''    fail2ban-malicious:
      plugin:
        fail2ban:
          rules:
            maxretry: 2
            findtime: "120s"
            bantime: "3600s"
            monitoredStatusCodes: ["400-599"]
    fail2ban-global:
      plugin:
        fail2ban:
          rules:
            maxretry: 3
            findtime: "300s"
            bantime: "7200s"
            monitoredStatusCodes: ["400-599"]
''',
    '''    supabase-guard-malicious:
      plugin:
        supabaseguard:
          profile: malicious
          mode: enforce
          scope: global-malicious
          maxTrackedClients: 50000
          cleanupInterval: 5m
          scannerThreshold: 2
          scannerWindow: 2m
          scannerBanTime: 1h
''',
)
source = middlewares.read_text(encoding="utf-8")
source = source.replace("fail2ban-malicious", "supabase-guard-malicious")
source = source.replace("fail2ban-global", "supabase-guard-malicious")
if "fail2ban" in source or "monitoredStatusCodes" in source:
    raise SystemExit("legacy fail2ban references remain in middlewares.yml")
middlewares.write_text(source, encoding="utf-8")

docker_compose = Path("servidor/traefik/docker-compose.yml")
replace_once(
    docker_compose,
    '''  traefik:
    image: ${TRAEFIK_IMAGE}
''',
    '''  traefik:
    image: ${TRAEFIK_IMAGE}
    working_dir: /
''',
)
replace_once(
    docker_compose,
    '''      - ./middlewares.yml:/etc/traefik/dynamic/middlewares.yml
      - ./plugins-storage:/plugins-storage
''',
    '''      - ./middlewares.yml:/etc/traefik/dynamic/middlewares.yml
      - ./plugins-local:/plugins-local:ro
      - ./plugins-storage:/plugins-storage
''',
)

template = Path("servidor/generateProject/dockercomposetemplate")
replace_once(
    template,
    '''      - "traefik.http.services.supabase-nginx-{{project_id}}.loadbalancer.server.port=8080"
      - "traefik.http.middlewares.nginx-{{project_id}}-stripprefix.stripprefix.prefixes=/{{project_id}}"
''',
    '''      - "traefik.http.services.supabase-nginx-{{project_id}}.loadbalancer.server.port=8080"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.profile=project"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.mode=${TRAEFIK_GUARD_PROJECT_MODE:-observe}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.scope={{project_uuid}}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.maxTrackedClients=${TRAEFIK_GUARD_MAX_TRACKED_CLIENTS:-10000}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.cleanupInterval=${TRAEFIK_GUARD_CLEANUP_INTERVAL:-5m}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.authThreshold=${TRAEFIK_GUARD_AUTH_THRESHOLD:-12}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.authWindow=${TRAEFIK_GUARD_AUTH_WINDOW:-10m}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.authBanTime=${TRAEFIK_GUARD_AUTH_BAN_TIME:-15m}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.scannerThreshold=${TRAEFIK_GUARD_SCANNER_THRESHOLD:-2}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.scannerWindow=${TRAEFIK_GUARD_SCANNER_WINDOW:-2m}"
      - "traefik.http.middlewares.supabase-guard-{{project_id}}.plugin.supabaseguard.scannerBanTime=${TRAEFIK_GUARD_SCANNER_BAN_TIME:-1h}"
      - "traefik.http.middlewares.nginx-{{project_id}}-stripprefix.stripprefix.prefixes=/{{project_id}}"
''',
)
replace_once(
    template,
    '''      - "traefik.http.routers.supabase-nginx-{{project_id}}.middlewares=rate-limit@file,security-headers@file, nginx-{{project_id}}-stripprefix@docker"
''',
    '''      - "traefik.http.routers.supabase-nginx-{{project_id}}.middlewares=rate-limit@file,supabase-guard-{{project_id}}@docker,security-headers@file,nginx-{{project_id}}-stripprefix@docker"
''',
)

env_example = Path("servidor/.env.example")
replace_once(
    env_example,
    '''TRAEFIK_DENY_IMAGE=nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim
TRAEFIK_DENY_CONTAINER_NAME=traefik-deny-service
''',
    '''TRAEFIK_DENY_IMAGE=nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim
TRAEFIK_DENY_CONTAINER_NAME=traefik-deny-service
TRAEFIK_GUARD_PROJECT_MODE=observe
TRAEFIK_GUARD_MAX_TRACKED_CLIENTS=10000
TRAEFIK_GUARD_CLEANUP_INTERVAL=5m
TRAEFIK_GUARD_AUTH_THRESHOLD=12
TRAEFIK_GUARD_AUTH_WINDOW=10m
TRAEFIK_GUARD_AUTH_BAN_TIME=15m
TRAEFIK_GUARD_SCANNER_THRESHOLD=2
TRAEFIK_GUARD_SCANNER_WINDOW=2m
TRAEFIK_GUARD_SCANNER_BAN_TIME=1h
''',
)
