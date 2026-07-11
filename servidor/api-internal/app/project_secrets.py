from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


FORMAT_VERSION = "v2"
ALGORITHM = "aes-256-gcm"


class ProjectSecretError(ValueError):
    """Raised when an encrypted project secret cannot be verified or opened."""


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ProjectSecretError("ciphertext is not valid base64url") from exc


@dataclass(frozen=True)
class ProjectKeyEnvelope:
    key_id: str
    wrapped_dek: str
    wrapping_key_id: str
    algorithm: str = ALGORITHM


class ProjectSecretManager:
    """Envelope encryption for project-scoped persistent secrets.

    The master key only wraps per-project data-encryption keys (DEKs). Each
    individual secret is AES-GCM encrypted with that project's random DEK and
    cryptographically bound to its project id and column name.
    """

    def __init__(
        self,
        master_key: str,
        *,
        wrapping_key_id: str,
        previous_master_keys: tuple[str, ...] = (),
    ) -> None:
        if not master_key:
            raise ProjectSecretError("missing project secrets master key")
        try:
            primary = Fernet(master_key.encode("ascii"))
            all_keys = [primary, *(
                Fernet(key.encode("ascii")) for key in previous_master_keys if key
            )]
        except (UnicodeEncodeError, ValueError) as exc:
            raise ProjectSecretError("invalid project secrets master key") from exc

        self._primary = primary
        self._keyring = MultiFernet(all_keys)
        self.wrapping_key_id = wrapping_key_id

    @staticmethod
    def _aad(project_id: uuid.UUID | str, purpose: str) -> bytes:
        return f"project-secret-v2:{project_id}:{purpose}".encode("utf-8")

    def create_envelope(self) -> tuple[ProjectKeyEnvelope, bytes]:
        dek = AESGCM.generate_key(bit_length=256)
        envelope = ProjectKeyEnvelope(
            key_id=str(uuid.uuid4()),
            wrapped_dek=self._primary.encrypt(dek).decode("ascii"),
            wrapping_key_id=self.wrapping_key_id,
        )
        return envelope, dek

    def unwrap_dek(self, envelope: ProjectKeyEnvelope) -> bytes:
        if envelope.algorithm != ALGORITHM:
            raise ProjectSecretError("unsupported project secret algorithm")
        try:
            dek = self._keyring.decrypt(envelope.wrapped_dek.encode("ascii"))
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ProjectSecretError("unable to unwrap project data key") from exc
        if len(dek) != 32:
            raise ProjectSecretError("invalid project data key length")
        return dek

    def rewrap_dek(self, dek: bytes) -> str:
        if len(dek) != 32:
            raise ProjectSecretError("invalid project data key length")
        return self._primary.encrypt(dek).decode("ascii")

    def encrypt(
        self,
        *,
        project_id: uuid.UUID | str,
        purpose: str,
        key_id: str,
        dek: bytes,
        plaintext: str,
    ) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(dek).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._aad(project_id, purpose),
        )
        return f"{FORMAT_VERSION}.{key_id}.{_base64url_encode(nonce + ciphertext)}"

    def decrypt(
        self,
        *,
        project_id: uuid.UUID | str,
        purpose: str,
        key_id: str,
        dek: bytes,
        ciphertext: str,
    ) -> str:
        parts = ciphertext.split(".", 2)
        if len(parts) != 3 or parts[0] != FORMAT_VERSION or parts[1] != key_id:
            raise ProjectSecretError("project secret envelope does not match key")
        raw = _base64url_decode(parts[2])
        if len(raw) <= 12:
            raise ProjectSecretError("project secret ciphertext is too short")
        try:
            plaintext = AESGCM(dek).decrypt(
                raw[:12],
                raw[12:],
                self._aad(project_id, purpose),
            )
            return plaintext.decode("utf-8")
        except Exception as exc:  # InvalidTag and invalid UTF-8 are both failures.
            raise ProjectSecretError("project secret authentication failed") from exc

    @staticmethod
    def is_v2(ciphertext: str | None) -> bool:
        return bool(ciphertext and ciphertext.startswith(f"{FORMAT_VERSION}."))
