import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("bash"), "Bash required")
class StorageAdmissionProbeTests(unittest.TestCase):
    def run_probe(self, *, request_status=0, probe_ip="198.51.100.40", duplicate=False):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        project = root / "projects/alpha"
        project.mkdir(parents=True)
        (root / ".env").write_text("ACCESS_ADMISSION_SECRET=" + "c" * 64 + "\n", encoding="utf-8")
        (project / ".env").write_text(
            "PROJECT_PUBLIC_REF="
            + "a" * 20
            + "\nAPI_GATEWAY_TOKEN_PROJETO="
            + "b" * 64
            + "\n"
            + ("PROJECT_PUBLIC_REF=" + "d" * 20 + "\n" if duplicate else ""),
            encoding="utf-8",
        )
        binary = root / "bin"
        binary.mkdir()
        docker = binary / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            + """import os, subprocess, sys
args=sys.argv[1:]
if args[0]=='inspect':
    assert args[-1]=='shared-storage-data-plane'
    assert 'supabase-storage-gateways' in args[2]
    print(os.environ['PROBE_IP'])
elif args[0]=='exec':
    assert args[1]=='supabase-nginx-alpha'
    raise SystemExit(subprocess.run(args[2:]).returncode)
else:
    raise SystemExit(2)
""",
            encoding="utf-8",
        )
        wget = binary / "wget"
        wget.write_text(
            f"#!{sys.executable}\n"
            + """import json, os, pathlib, sys
payload=next(arg.split('=',1)[1] for arg in sys.argv[1:] if arg.startswith('--post-data='))
pathlib.Path(os.environ['PROBE_BODY']).write_text(payload)
print('  X-Gateway-Admission: '+'x'*43, file=sys.stderr)
raise SystemExit(int(os.environ['REQUEST_STATUS']))
""",
            encoding="utf-8",
        )
        for command in (docker, wget):
            command.chmod(0o755)
        script = root / "probe.sh"
        script.write_text(
            f'set -Eeuo pipefail\nsource "{ROOT}/servidor/generateProject/lib/storage_multitenant.sh"\n'
            'STORAGE_SERVER_ROOT="$FIXTURE_ROOT"\nstorage_gateway_admission_ticket alpha /storage/v1/bucket GET\n',
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "FIXTURE_ROOT": str(root),
            "PROBE_IP": probe_ip,
            "PROBE_BODY": str(root / "body.json"),
            "REQUEST_STATUS": str(request_status),
        }
        result = subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=10
        )
        return result, root

    def test_probe_binds_the_real_storage_container_origin(self):
        result, root = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "x" * 43)
        body = json.loads((root / "body.json").read_text())
        self.assertEqual(body["client_ip"], "198.51.100.40")
        self.assertEqual(body["uri"], "/" + "a" * 20 + "/storage/v1/bucket")
        self.assertEqual(body["method"], "GET")

    def test_transport_failure_is_not_a_successful_ticket(self):
        result, _ = self.run_probe(request_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("c" * 64, result.stderr)

    def test_missing_origin_and_duplicate_reference_fail_before_admission(self):
        for kwargs in ({"probe_ip": ""}, {"duplicate": True}):
            with self.subTest(kwargs=kwargs):
                result, root = self.run_probe(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "body.json").exists())


if __name__ == "__main__":
    unittest.main()
