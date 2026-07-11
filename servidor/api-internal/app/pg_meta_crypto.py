from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


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

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    pad_len = 16 - (len(uri) % 16)
    padded_uri = uri.encode("utf-8") + bytes([pad_len] * pad_len)
    ciphertext = encryptor.update(padded_uri) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("utf-8")
