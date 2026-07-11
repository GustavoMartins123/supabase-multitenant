"""Leitura de metadados não sensíveis de JWTs emitidas pelo próprio sistema."""

import base64
import json


def get_unverified_jwt_expiry(token: str) -> int | None:
    """Retorna o claim exp sem usá-lo para autenticação ou autorização."""
    try:
        payload_segment = token.split(".", 2)[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(payload_segment + padding).decode("utf-8")
        )
        expiry = payload.get("exp")
        return int(expiry) if expiry is not None else None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None
