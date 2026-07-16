"""Configuracao validada da API interna.

Falhas de configuracao sao detectadas na importacao, antes de a aplicacao
aceitar trafego.
"""

import hmac
import os
import pathlib
import urllib.parse

from cryptography.fernet import Fernet

from app.project_secrets import ProjectSecretError, ProjectSecretManager


BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

DB_DSN = os.getenv("DB_DSN")
HOST_AGENT_HMAC_SECRET = os.getenv("HOST_AGENT_HMAC_SECRET")
PROJECT_SECRETS_MASTER_KEY = os.getenv("PROJECT_SECRETS_MASTER_KEY")
PROJECT_SECRETS_MASTER_KEY_ID = os.getenv(
    "PROJECT_SECRETS_MASTER_KEY_ID", "project-secrets-master-v1"
)
PROJECT_SECRETS_PREVIOUS_MASTER_KEYS = tuple(
    key.strip()
    for key in os.getenv("PROJECT_SECRETS_PREVIOUS_MASTER_KEYS", "").split(",")
    if key.strip()
)
PG_META_CRYPTO_KEY = os.getenv("PG_META_CRYPTO_KEY")
STUDIO_SERVICE_KEY_ENCRYPTION_KEY = os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY")
NGINX_SHARED_TOKEN = os.getenv("NGINX_SHARED_TOKEN")
NGINX_HMAC_SECRET = os.getenv("NGINX_HMAC_SECRET")
LOGFLARE_PRIVATE_ACCESS_TOKEN = os.getenv("LOGFLARE_PRIVATE_ACCESS_TOKEN")
ANALYTICS_INTERNAL_URL = os.getenv(
    "ANALYTICS_INTERNAL_URL", "http://analytics:4000"
).rstrip("/")
USER_TOKEN_MAX_CLOCK_SKEW_SECONDS = int(
    os.getenv("USER_TOKEN_MAX_CLOCK_SKEW_SECONDS", "30")
)
KEY_EXPIRY_WARNING_DAYS = max(1, int(os.getenv("KEY_EXPIRY_WARNING_DAYS", "14")))
SUPAVISOR_INTERNAL_URL = os.getenv(
    "SUPAVISOR_INTERNAL_URL", "http://supabase-pooler:4000"
).rstrip("/")
REALTIME_INTERNAL_URL = os.getenv(
    "REALTIME_INTERNAL_URL", "http://realtime-dev.supabase-realtime:4000"
).rstrip("/")
STUDIO_CACHE_INVALIDATION_URL = os.getenv(
    "STUDIO_CACHE_INVALIDATION_URL", "https://nginx:443"
).rstrip("/")
STUDIO_CACHE_INVALIDATION_VERIFY_TLS = os.getenv(
    "STUDIO_CACHE_INVALIDATION_VERIFY_TLS", "false"
).strip().lower() in {"1", "true", "yes", "on"}
PG_META_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv("PG_META_ALLOWED_HOSTS", "postgres-meta-global").split(",")
    if host.strip()
}


def _validate_pg_meta_internal_url(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(raw_url.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("Invalid PG_META_INTERNAL_URL: scheme must be http or https")
    if not parsed.hostname:
        raise RuntimeError("Invalid PG_META_INTERNAL_URL: missing hostname")
    if parsed.username or parsed.password:
        raise RuntimeError("Invalid PG_META_INTERNAL_URL: userinfo is not allowed")
    if parsed.path not in {"", "/"}:
        raise RuntimeError("Invalid PG_META_INTERNAL_URL: path is not allowed")
    if parsed.query or parsed.fragment or parsed.params:
        raise RuntimeError(
            "Invalid PG_META_INTERNAL_URL: query, params and fragment are not allowed"
        )
    if parsed.hostname.lower() not in PG_META_ALLOWED_HOSTS:
        raise RuntimeError(
            "Invalid PG_META_INTERNAL_URL: hostname is not in PG_META_ALLOWED_HOSTS"
        )
    return urllib.parse.urlunparse(parsed)


PG_META_INTERNAL_URL = _validate_pg_meta_internal_url(
    os.getenv("PG_META_INTERNAL_URL", "http://postgres-meta-global:8080")
)

for key_name, key_value in {
    "DB_DSN": DB_DSN,
    "PROJECT_SECRETS_MASTER_KEY": PROJECT_SECRETS_MASTER_KEY,
    "PG_META_CRYPTO_KEY": PG_META_CRYPTO_KEY,
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": STUDIO_SERVICE_KEY_ENCRYPTION_KEY,
    "NGINX_SHARED_TOKEN": NGINX_SHARED_TOKEN,
    "NGINX_HMAC_SECRET": NGINX_HMAC_SECRET,
    "LOGFLARE_PRIVATE_ACCESS_TOKEN": LOGFLARE_PRIVATE_ACCESS_TOKEN,
    "HOST_AGENT_HMAC_SECRET": HOST_AGENT_HMAC_SECRET,
}.items():
    if not key_value:
        raise RuntimeError(f"Missing {key_name} environment variable")

try:
    project_secret_manager = ProjectSecretManager(
        PROJECT_SECRETS_MASTER_KEY,
        wrapping_key_id=PROJECT_SECRETS_MASTER_KEY_ID,
        previous_master_keys=PROJECT_SECRETS_PREVIOUS_MASTER_KEYS,
    )
    service_key_transport_fernet = Fernet(STUDIO_SERVICE_KEY_ENCRYPTION_KEY.encode())
except (ProjectSecretError, ValueError) as exc:
    raise RuntimeError(
        "Invalid project-secret or Studio service-key encryption key. "
        "Use Fernet.generate_key()."
    ) from exc

for key_name, key_value in {
    "PG_META_CRYPTO_KEY": PG_META_CRYPTO_KEY,
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": STUDIO_SERVICE_KEY_ENCRYPTION_KEY,
}.items():
    if hmac.compare_digest(key_value, PROJECT_SECRETS_MASTER_KEY):
        raise RuntimeError(f"{key_name} must be distinct from PROJECT_SECRETS_MASTER_KEY")
