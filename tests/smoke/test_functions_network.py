from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/generateProject'))
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))
from functions_network import ensure_network_hosts_file, network_hosts
from app.pg_meta_crypto import postgres_meta_authorization


class FunctionsNetworkTests(unittest.TestCase):
    def test_supervisor_dns_map_is_private_regular_and_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts'
            ensure_network_hosts_file(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text(path.read_text() + '1.1.1.1 approved.example.com\n')
            before = path.read_bytes()
            ensure_network_hosts_file(path)
            self.assertEqual(path.read_bytes(), before)
            path.unlink()
            path.symlink_to(Path(directory) / 'outside')
            with self.assertRaises(ValueError):
                ensure_network_hosts_file(path)

    def test_external_destinations_require_explicit_ports_and_have_a_canonical_order(self):
        self.assertEqual(network_hosts('api.stripe.com:443,api.openai.com:443,api.stripe.com:443'),
                         ['api.openai.com:443', 'api.stripe.com:443'])
        self.assertEqual(network_hosts(''), [])

    def test_wildcards_private_destinations_and_url_controls_are_denied(self):
        for value in ['*:443', 'example.com', 'https://example.com:443', 'example.com:0', 'example.com:65536',
                      'postgres-meta-global:8080', 'localhost:8080', 'api.local:443', 'api.internal:443',
                      '127.0.0.1:80', '10.0.0.1:80', '169.254.169.254:80', '172.20.1.2:8080',
                      '192.168.1.1:443', '[::1]:80', '[fe80::1]:443', 'user@example.com:443',
                      'example.com:443/path', 'example.com:443?x=1', 'example.com:443#x', 'example.com:0443']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                network_hosts(value)

    def test_metadata_http_credential_is_domain_separated_and_rejects_weak_keys(self):
        key = 'synthetic-private-transport-key-' + 'x' * 32
        credential = postgres_meta_authorization(key)
        self.assertTrue(credential.startswith('Bearer '))
        self.assertNotIn(key, credential)
        self.assertEqual(credential, postgres_meta_authorization(key))
        self.assertNotEqual(credential, postgres_meta_authorization(key + 'changed'))
        for value in ['', 'SAMPLE_KEY', 'pass']:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                postgres_meta_authorization(value)
