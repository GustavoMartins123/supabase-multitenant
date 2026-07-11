from __future__ import annotations

import base64
import hashlib
import importlib
import sys
import unittest
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

crypto = importlib.import_module("app.pg_meta_crypto")


def decrypt_for_contract_test(ciphertext: str, passphrase: str) -> str:
    raw = base64.b64decode(ciphertext)
    assert raw.startswith(b"Salted__")
    salt = raw[8:16]
    key_iv = b""
    previous = b""
    while len(key_iv) < 48:
        previous = hashlib.md5(previous + passphrase.encode() + salt).digest()
        key_iv += previous
    decryptor = Cipher(
        algorithms.AES(key_iv[:32]),
        modes.CBC(key_iv[32:48]),
        backend=default_backend(),
    ).decryptor()
    padded = decryptor.update(raw[16:]) + decryptor.finalize()
    return padded[:-padded[-1]].decode()


class PgMetaCryptoTest(unittest.TestCase):
    def test_open_ssl_payload_round_trip_uses_its_own_key(self) -> None:
        uri = "postgresql://supabase_admin:password@db:5432/_supabase_demo"
        transport_key = "pg-meta-crypto-key-is-distinct-and-long-enough"
        encrypted = crypto.encrypt_postgres_meta_uri(uri, transport_key)
        self.assertEqual(decrypt_for_contract_test(encrypted, transport_key), uri)
        try:
            wrong_plaintext = decrypt_for_contract_test(encrypted, "different-key")
        except Exception:
            wrong_plaintext = None
        self.assertNotEqual(wrong_plaintext, uri)


if __name__ == "__main__":
    unittest.main()
