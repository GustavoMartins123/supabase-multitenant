from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'posix', 'real POSIX tar and file operations required')
class NamespaceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = Path(self.temp.name)
        self.objects = self.server / 'objects'
        self.source, self.clone, self.restored = [str(uuid.uuid4()) for _ in range(3)]
        directory = self.objects / self.source / 'bucket' / 'foto com espaços.png'
        directory.mkdir(parents=True)
        (directory / 'version').write_bytes(bytes(range(256)) * 1024)
        self.metadata = {
            'user.supabase.content-type': b'image/png',
            'user.supabase.cache-control': b'3600',
            'user.supabase.etag': b'test-etag',
        }
        for key, value in self.metadata.items():
            os.setxattr(directory / 'version', key, value)
        (directory / 'version.json').write_text('{"contentType":"image/png","cacheControl":"3600"}')
        (self.server / '.env').write_text('\n'.join((
            'STORAGE_IMAGE=supabase/storage-api:v1.61.12',
            'STORAGE_DATA_PLANE_PROXY_IMAGE=nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim',
            'STORAGE_BACKEND=file', 'STORAGE_FILE_BACKEND_PATH=/var/lib/storage',
            'STORAGE_INTERNAL_BUCKET=objects', 'STORAGE_TENANT_DB_USER=supabase_storage_admin',
            'STORAGE_TENANT_HOST_REGEXP=^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[.]storage[.]internal$',
            f'STORAGE_RUN_AS_USER={os.getuid()}:{os.getgid()}',
        )))

    def shell(self, script):
        prefix = f'''set -Eeuo pipefail
source "{ROOT}/servidor/generateProject/lib/storage_multitenant.sh"
STORAGE_SERVER_ROOT="$1"
STORAGE_OBJECT_ROOT="$1/objects"
'''
        return subprocess.run(['bash', '-c', prefix + script, 'test', str(self.server)], capture_output=True, text=True)

    def manifest(self, tenant):
        directory = self.objects / tenant
        return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in directory.rglob('*') if p.is_file()}

    def test_clone_and_restore_preserve_object_and_metadata_bytes(self):
        result = self.shell(f'''storage_clone_tenant_namespace {self.source} {self.clone}
tar --xattrs --xattrs-include='user.supabase.*' --no-acls --numeric-owner -czpf "$1/objects.tar.gz" -C "$1/objects/{self.source}" .
storage_extract_namespace_archive {self.restored} "$1/objects.tar.gz"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.manifest(self.source), self.manifest(self.clone))
        self.assertEqual(self.manifest(self.source), self.manifest(self.restored))
        for tenant in (self.clone, self.restored):
            file = next(p for p in (self.objects / tenant).rglob('version'))
            self.assertEqual({key: os.getxattr(file, key) for key in self.metadata}, self.metadata)
        self.assertNotIn('Operation not supported', result.stderr)

    def test_existing_target_and_symlinks_fail_closed(self):
        (self.objects / self.clone).mkdir()
        result = self.shell(f'storage_clone_tenant_namespace {self.source} {self.clone}')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any((self.objects / self.clone).iterdir()))
        (self.objects / self.source / 'outside').symlink_to('/etc/passwd')
        result = self.shell(f'storage_clone_tenant_namespace {self.source} {self.restored}')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.objects / self.restored).exists())

    def test_archive_traversal_is_rejected_before_target_creation(self):
        archive = self.server / 'invalid.tar.gz'
        with tarfile.open(archive, 'w:gz') as handle:
            handle.addfile(tarfile.TarInfo('../escape'))
        result = self.shell(f'storage_extract_namespace_archive {self.restored} "$1/invalid.tar.gz"')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.objects / self.restored).exists())
