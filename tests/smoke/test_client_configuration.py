import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))
from app.opaque_keys import generate_application_ref, APPLICATION_REF_PATTERN


def migration_tool():
    spec = importlib.util.spec_from_file_location('client_config_migration', ROOT / 'tools/migrate_client_configuration.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplicationReferenceTest(unittest.TestCase):
    def test_random_reference_is_independent_of_project_and_slot_uuid(self):
        refs = {generate_application_ref() for _ in range(100)}
        self.assertEqual(len(refs), 100)
        self.assertTrue(all(APPLICATION_REF_PATTERN.fullmatch(ref) for ref in refs))

    def test_reference_validation_does_not_normalize(self):
        for value in ('', 'a'*19, 'A'*20, 'a'*20+'\n', '1'*20, 'é'*20):
            self.assertIsNone(APPLICATION_REF_PATTERN.fullmatch(value))

    def test_obsolete_environment_value_is_removed_without_touching_other_bytes(self):
        tool = migration_tool()
        original = b'PROJECT_ID=select\r\nCONFIG_TOKEN_PROJETO=' + b'a'*64 + b'\r\nPRIVATE_SECRET=preserved\r\n'
        self.assertEqual(tool.stripped_environment(original), b'PROJECT_ID=select\r\nPRIVATE_SECRET=preserved\r\n')
        for value in (b'CONFIG_TOKEN_PROJETO=bad\n', b' CONFIG_TOKEN_PROJETO='+b'a'*64+b'\n',
                      b'CONFIG_TOKEN_PROJETO='+b'a'*64+b'\nCONFIG_TOKEN_PROJETO='+b'b'*64+b'\n'):
            with self.assertRaises(RuntimeError):
                tool.stripped_environment(value)

    def test_failed_regeneration_rolls_back_every_original_file(self):
        tool = migration_tool()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'installation'
            directory = root / 'projects' / 'select'
            (directory / 'nginx').mkdir(parents=True)
            env = directory / '.env'
            env.write_text('PROJECT_ID=select\nPROJECT_UUID=11111111-1111-4111-8111-111111111111\n'
                'PROJECT_PUBLIC_REF=abcdefghijklmnopqrst\nCONFIG_TOKEN_PROJETO='+'a'*64+'\nPRIVATE_SECRET=preserved\n')
            files = [env, directory/'Dockerfile', directory/'docker-compose.yml', directory/'nginx/nginx_select.conf']
            for file in files[1:]:
                file.write_text('original '+file.name)
            original = {file: file.read_bytes() for file in files}
            project = {'name':'select','tenant_uuid':'11111111-1111-4111-8111-111111111111','public_ref':'abcdefghijklmnopqrst'}
            def fail(**kwargs):
                self.assertNotIn(b'CONFIG_TOKEN_PROJETO', env.read_bytes())
                files[1].write_text('partial update')
                raise RuntimeError('Forced render failure')
            with patch.object(tool, 'require_stopped'), patch.object(tool, 'sync_project_generated_files', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'Forced render failure'):
                    tool.migrate(root, [project], backup_dir=Path(temporary)/'private-backup', apply=True)
            self.assertEqual({file:file.read_bytes() for file in files}, original)

    def test_public_discovery_never_proxies_the_control_plane(self):
        source = (ROOT / 'servidor/client-configuration/app.py').read_text()
        self.assertIn("request.method != 'GET'", source)
        self.assertIn("request.method == 'OPTIONS'", source)
        self.assertIn('client_configuration_reader', source)
        self.assertNotIn('PROJECT_SECRETS_MASTER_KEY', source)
        self.assertNotIn('internal_hmac', source)
        self.assertNotIn('client_configuration_router', (ROOT/'servidor/api-internal/app/asgi.py').read_text())
        nginx = (ROOT / 'studio/nginx/nginx.conf').read_text()
        section = nginx[nginx.index('location ^~ /config/'):nginx.index('location = /api/security/step-up')]
        self.assertIn('return 404', section)
        self.assertNotIn('proxy_pass', section)
        compose = (ROOT/'servidor/docker-compose-api.yml').read_text()
        section = compose[compose.index('  client-configuration:'):compose.index('  key-authorizer:')]
        self.assertIn('networks: [client-configuration-data]', section)
        self.assertNotIn('PROJECT_SECRETS_MASTER_KEY', section)
        self.assertNotIn('volumes:', section)


if __name__ == '__main__':
    unittest.main()
