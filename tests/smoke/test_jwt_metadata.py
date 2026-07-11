import base64
import json
import sys
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2] / "servidor" / "api-internal"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.jwt_metadata import get_unverified_jwt_expiry


def encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class JwtMetadataTest(unittest.TestCase):
    def test_reads_expiry_without_exposing_other_claims(self):
        token = f"{encode({'alg': 'HS256'})}.{encode({'exp': 123456, 'role': 'anon'})}.sig"
        self.assertEqual(get_unverified_jwt_expiry(token), 123456)

    def test_invalid_or_missing_expiry_returns_none(self):
        self.assertIsNone(get_unverified_jwt_expiry("invalid"))
        token = f"{encode({'alg': 'HS256'})}.{encode({'role': 'anon'})}.sig"
        self.assertIsNone(get_unverified_jwt_expiry(token))


if __name__ == "__main__":
    unittest.main()
