"""Metadados e estado duravel da rotacao das API keys de projeto."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.jwt_metadata import get_unverified_jwt_expiry


class KeyRotationMetadataError(ValueError):
    """As chaves persistidas nao possuem expiracao coerente."""


@dataclass(frozen=True)
class ProjectKeySchedule:
    expires_at: dt.datetime
    rotate_at: dt.datetime


def project_key_schedule(
    anon_key: str,
    service_role: str,
    *,
    lead_days: int,
) -> ProjectKeySchedule:
    """Calcula a agenda usando a expiracao comum das duas API keys.

    Os claims sao apenas metadados de tokens que o proprio sistema emitiu;
    eles nunca sao usados para autenticar ou autorizar uma requisicao.
    """
    if lead_days < 1:
        raise ValueError("lead_days must be positive")

    anon_expiry = get_unverified_jwt_expiry(anon_key)
    service_expiry = get_unverified_jwt_expiry(service_role)
    if anon_expiry is None or service_expiry is None:
        raise KeyRotationMetadataError("JWT exp ausente ou invalido")
    if anon_expiry != service_expiry:
        raise KeyRotationMetadataError(
            "anon_key e service_role possuem expiracoes divergentes"
        )

    try:
        expires_at = dt.datetime.fromtimestamp(anon_expiry, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise KeyRotationMetadataError("JWT exp fora do intervalo suportado") from exc
    rotate_at = expires_at - dt.timedelta(days=lead_days)
    return ProjectKeySchedule(expires_at=expires_at, rotate_at=rotate_at)
