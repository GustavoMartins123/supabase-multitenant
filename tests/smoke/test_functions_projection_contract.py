from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FunctionsProjectionContractTest(unittest.TestCase):
    def test_supervisor_mounts_only_credential_projection_readonly(self):
        source = (ROOT / 'servidor/docker-compose.yml').read_text(encoding='utf-8')
        block = source.split('\n  functions:', 1)[1].split('\n  storage:', 1)[0]
        self.assertNotIn('./projects:', block)
        self.assertIn('source: ./.functions-tenants', block)
        self.assertIn('read_only: true', block)
        self.assertIn('create_host_path: false', block)
        self.assertIn('/home/deno/functions:ro,Z', block)

    def test_one_canonical_projection_and_fresh_worker_per_decision(self):
        source = (ROOT / 'servidor/volumes/functions/main/index.ts').read_text(encoding='utf-8')
        self.assertIn("'/home/deno/tenant-config'", source)
        self.assertNotIn('/home/deno/projects', source)
        self.assertNotIn('parseDotenv', source)
        self.assertIn('forceCreate: true', source)
        self.assertIn('parsed.project_ref !== ref', source)

    def test_all_lifecycle_implementations_hold_locks_and_publish_after_success(self):
        for name in ('generate', 'duplicate', 'restore'):
            source = (ROOT / f'servidor/generateProject/lib/{name}_project_impl.sh').read_text(encoding='utf-8')
            self.assertIn('functions_config_lock ', source, name)
            self.assertIn('functions_config_withdraw ', source, name)
            self.assertIn('functions_config_publish ', source, name)
        rotation = (ROOT / 'servidor/generateProject/rotate_project_reference.py').read_text(encoding='utf-8')
        self.assertIn('self.functions("withdraw")', rotation)
        self.assertIn('self.functions("publish")', rotation)
        self.assertIn('functions_config_lock ', (ROOT / 'servidor/generateProject/lib/rename_project_impl.sh').read_text(encoding='utf-8'))
        for name in ('delete_project', 'delete_storage_tenant', 'rotate_key'):
            source = (ROOT / f'servidor/generateProject/{name}.sh').read_text(encoding='utf-8')
            self.assertIn('functions_config_lock ', source, name)
            self.assertIn('functions_config_withdraw ', source, name)
        self.assertIn('functions_config_publish ', (ROOT / 'servidor/generateProject/rotate_key.sh').read_text(encoding='utf-8'))

    def test_projection_and_locks_are_private_and_initialized_in_both_server_topologies(self):
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        for directory in ('.functions-tenants', '.functions-locks'):
            self.assertIn(f'servidor/{directory}/', ignore)
            self.assertIn(directory, (ROOT / 'servidor/host-agent/install.sh').read_text(encoding='utf-8'))
        start = (ROOT / 'start.sh').read_text(encoding='utf-8')
        self.assertGreater(start.index('functions_config.py'), start.index('require_host_agent_installation\n'))
        self.assertLess(start.index('functions_config.py'), start.index('Iniciando a base de dados'))


if __name__ == '__main__':
    unittest.main()
