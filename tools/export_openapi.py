"""Exporta o OpenAPI da Projects API para docs/api/openapi.json.

Uso: python tools/export_openapi.py [--check]
Com --check, apenas compara o artefato commitado com o gerado e falha
se divergirem (usado pelo contrato de estabilidade no CI).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servidor" / "api-internal"))

from cryptography.fernet import Fernet


def _env(name: str, fallback: str) -> None:
    os.environ.setdefault(name, fallback)


_env("DB_DSN", "postgresql://u:p@localhost:5432/db")
_env("HOST_AGENT_HMAC_SECRET", "x" * 32)
_env("PROJECT_SECRETS_MASTER_KEY", Fernet.generate_key().decode())
_env("PG_META_CRYPTO_KEY", Fernet.generate_key().decode())
_env("STUDIO_SERVICE_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
_env("NGINX_HMAC_SECRET", "v" * 32)
_env("STUDIO_GATEWAY_HMAC_SECRET", "u" * 32)
_env("PROJECTS_API_HMAC_SECRET", "t" * 32)
_env("LOGFLARE_PRIVATE_ACCESS_TOKEN", "s" * 16)

TARGET = ROOT / "docs" / "api" / "openapi.json"


def build_schema() -> dict:
    from app.asgi import app

    return app.openapi()


def main() -> int:
    schema = build_schema()
    rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv[1:]:
        if not TARGET.is_file():
            print(f"missing {TARGET}")
            return 1
        current = TARGET.read_text(encoding="utf-8")
        if current != rendered:
            print(f"{TARGET} is out of sync; run python tools/export_openapi.py")
            return 1
        print(f"{TARGET} is in sync")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    paths = len(schema.get("paths", {}))
    print(f"wrote {TARGET} ({paths} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
