#!/usr/bin/env python3
"""Generate a tenant-scoped capability without exposing the platform secret."""
import argparse
import hashlib
import hmac
import os
from pathlib import Path
import re
import uuid


def project_key(secret, tenant):
    tenant = str(uuid.UUID(tenant))
    if len(secret) < 32:
        raise ValueError("O segredo de templates deve ter ao menos 32 caracteres")
    return hmac.new(
        secret.encode(), ("mailer-url-v1:" + tenant).encode(), hashlib.sha256
    ).hexdigest()


def configure(project_dir, tenant, secret):
    path = Path(project_dir) / ".env"
    text = path.read_text()
    key = project_key(secret, tenant)
    line = "MAILER_TEMPLATE_KEY=" + key
    if re.search(r"^MAILER_TEMPLATE_KEY=", text, flags=re.M):
        text = re.sub(r"^MAILER_TEMPLATE_KEY=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    path.write_text(text)
    path.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("tenant_uuid")
    args = parser.parse_args()
    secret = (
        Path(
            os.getenv(
                "MAILER_TEMPLATE_URL_SECRET_FILE",
                str(
                    args.project_dir.resolve().parents[1] / "secrets/mailer/URL_SECRET"
                ),
            )
        )
        .read_text()
        .strip()
    )
    configure(args.project_dir, args.tenant_uuid, secret)
