from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def postgres_meta_authorization(passphrase: str) -> str:
    """Derive the private metadata HTTP credential without exposing its cipher key."""
    if not isinstance(passphrase, str) or len(passphrase.encode()) < 16:
        raise RuntimeError("A private metadata transport key of at least 16 bytes is required")
    token = hmac.new(passphrase.encode(), b"postgres-meta-http-auth-v1", hashlib.sha256).hexdigest()
    return "Bearer " + token


def encrypt_postgres_meta_uri(uri: str, passphrase: str) -> str:
    """Produce the OpenSSL/CryptoJS-compatible value expected by postgres-meta."""
    salt = os.urandom(8)
    data = passphrase.encode("utf-8") + salt
    key_iv = b""
    last_hash = b""
    while len(key_iv) < 48:
        last_hash = hashlib.md5(last_hash + data).digest()
        key_iv += last_hash
    key = key_iv[:32]
    iv = key_iv[32:48]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    pad_len = 16 - (len(uri) % 16)
    padded_uri = uri.encode("utf-8") + bytes([pad_len] * pad_len)
    ciphertext = encryptor.update(padded_uri) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("utf-8")
