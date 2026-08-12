"""Pure cryptographic and protocol rules for project opaque API keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Literal


OpaqueKeyKind = Literal["publishable", "secret"]

RANDOM_BYTES = 32
RANDOM_TEXT_LENGTH = 43
CHECKSUM_LENGTH = 8
PREFIX_BY_KIND: dict[OpaqueKeyKind, str] = {
    "publishable": "sb_publishable_",
    "secret": "sb_secret_",
}
ROLE_BY_KIND: dict[OpaqueKeyKind, str] = {
    "publishable": "anon",
    "secret": "service_role",
}
ALLOWED_SERVICES = frozenset(
    {"auth", "rest", "graphql", "realtime", "storage", "functions"}
)
TOKEN_RE = re.compile(
    rf"^(?P<prefix>sb_publishable_|sb_secret_)"
    rf"(?P<random>[A-Za-z0-9_-]{{{RANDOM_TEXT_LENGTH}}})_"
    rf"(?P<checksum>[A-Za-z0-9_-]{{{CHECKSUM_LENGTH}}})$"
)
SLOT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,39}$")
BEARER_RE = re.compile(r"^Bearer ([^ ]+)$", re.IGNORECASE)


class OpaqueKeyError(ValueError):
    """Raised when an opaque key or its request context is non-canonical."""


@dataclass(frozen=True)
class GeneratedOpaqueKey:
    token: str
    digest: bytes
    kind: OpaqueKeyKind
    role: str
    token_hint: str


@dataclass(frozen=True)
class ParsedOpaqueKey:
    digest: bytes
    kind: OpaqueKeyKind
    role: str
    token_hint: str


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _kind_from_prefix(prefix: str) -> OpaqueKeyKind:
    if prefix == PREFIX_BY_KIND["publishable"]:
        return "publishable"
    if prefix == PREFIX_BY_KIND["secret"]:
        return "secret"
    raise OpaqueKeyError("unsupported opaque API key prefix")


def _checksum(project_id: uuid.UUID, prefix: str, random_text: str) -> str:
    material = f"{project_id}|{prefix}{random_text}".encode("ascii")
    return _base64url(hashlib.sha256(material).digest())[:CHECKSUM_LENGTH]


def _hint(prefix: str, random_text: str, checksum: str) -> str:
    return f"{prefix}{random_text[:6]}...{checksum[-4:]}"


def generate_opaque_key(
    project_id: uuid.UUID,
    kind: OpaqueKeyKind,
    *,
    random_bytes: bytes | None = None,
) -> GeneratedOpaqueKey:
    """Generate a project-bound, checksummed token with 256 bits of entropy."""

    try:
        prefix = PREFIX_BY_KIND[kind]
    except KeyError as exc:
        raise OpaqueKeyError("unsupported opaque API key kind") from exc

    entropy = secrets.token_bytes(RANDOM_BYTES) if random_bytes is None else random_bytes
    if len(entropy) != RANDOM_BYTES:
        raise OpaqueKeyError("opaque API key entropy must be exactly 32 bytes")
    random_text = _base64url(entropy)
    if len(random_text) != RANDOM_TEXT_LENGTH:
        raise OpaqueKeyError("opaque API key entropy encoding is not canonical")
    checksum = _checksum(project_id, prefix, random_text)
    token = f"{prefix}{random_text}_{checksum}"
    return GeneratedOpaqueKey(
        token=token,
        digest=hashlib.sha256(token.encode("ascii")).digest(),
        kind=kind,
        role=ROLE_BY_KIND[kind],
        token_hint=_hint(prefix, random_text, checksum),
    )


def parse_opaque_key(project_id: uuid.UUID, token: str) -> ParsedOpaqueKey:
    """Validate syntax and project checksum before producing a lookup digest."""

    if not isinstance(token, str) or not token or len(token) > 96:
        raise OpaqueKeyError("opaque API key has an invalid length")
    match = TOKEN_RE.fullmatch(token)
    if match is None:
        raise OpaqueKeyError("opaque API key format is invalid")

    prefix = match.group("prefix")
    random_text = match.group("random")
    checksum = match.group("checksum")
    expected = _checksum(project_id, prefix, random_text)
    if not hmac.compare_digest(checksum, expected):
        raise OpaqueKeyError("opaque API key checksum is invalid for this project")
    kind = _kind_from_prefix(prefix)
    return ParsedOpaqueKey(
        digest=hashlib.sha256(token.encode("ascii")).digest(),
        kind=kind,
        role=ROLE_BY_KIND[kind],
        token_hint=_hint(prefix, random_text, checksum),
    )


def normalize_slot_name(value: str) -> str:
    if not isinstance(value, str) or not SLOT_NAME_RE.fullmatch(value):
        raise OpaqueKeyError(
            "slot name must match ^[a-z][a-z0-9_-]{2,39}$"
        )
    return value


def validate_allowed_services(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise OpaqueKeyError("at least one allowed service is required")
    if any(not isinstance(value, str) for value in values):
        raise OpaqueKeyError("API key services must be canonical strings")
    if len(set(values)) != len(values):
        raise OpaqueKeyError("duplicate API key services are not allowed")
    unknown = sorted(set(values) - ALLOWED_SERVICES)
    if unknown:
        raise OpaqueKeyError(f"unsupported API key services: {', '.join(unknown)}")
    return tuple(sorted(values))


def should_preserve_authorization(api_key: str, authorization: str | None) -> bool:
    """Return whether an upstream user Bearer token must be preserved.

    Opaque credentials in Authorization are never treated as user JWTs. A
    mismatched opaque credential is ambiguous and therefore rejected.
    """

    value = authorization or ""
    if value != value.strip():
        raise OpaqueKeyError("Authorization contains non-canonical whitespace")
    if not value:
        return False
    match = BEARER_RE.fullmatch(value)
    if match is None:
        raise OpaqueKeyError("Authorization must use one canonical Bearer value")
    bearer = match.group(1)
    if hmac.compare_digest(bearer, api_key):
        return False
    if bearer.startswith("sb_publishable_") or bearer.startswith("sb_secret_"):
        raise OpaqueKeyError("Authorization contains a different opaque API key")
    return True
