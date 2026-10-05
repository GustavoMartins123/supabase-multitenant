import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    shutil.which("bash") and shutil.which("flock"), "Linux Bash and flock required"
)
class GeoIPUpdaterTests(unittest.TestCase):
    def run_update(self, *, validator=0, download=0, asset=True):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        data = root / "data with spaces"
        data.mkdir()
        database = data / "GeoLite2-Country.mmdb"
        database.write_bytes(b"original-database")
        backup = root / "backups"
        binary = root / "bin"
        binary.mkdir()
        curl = binary / "curl"
        curl.write_text(
            f"#!{sys.executable}\n"
            + """import json, os, pathlib, sys
args=sys.argv[1:]
if '--output' in args:
    if int(os.environ['DOWNLOAD_STATUS']):
        raise SystemExit(int(os.environ['DOWNLOAD_STATUS']))
    pathlib.Path(args[args.index('--output')+1]).write_bytes(b'validated-download')
else:
    print(json.dumps({'assets': [{'name':'GeoLite2-Country.mmdb','browser_download_url':
        'https://github.com/P3TERX/GeoLite.mmdb/releases/download/test/GeoLite2-Country.mmdb'}]
        if os.environ['HAS_ASSET']=='1' else []}))
""",
            encoding="utf-8",
        )
        docker = binary / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            + """import json, os, pathlib, sys
pathlib.Path(os.environ['DOCKER_ARGS']).write_text(json.dumps(sys.argv[1:]))
raise SystemExit(int(os.environ['VALIDATOR_STATUS']))
""",
            encoding="utf-8",
        )
        for command in (curl, docker):
            command.chmod(0o755)
        script = root / "update_geoip.sh"
        source = (ROOT / "servidor/traefik/update_geoip.sh.example").read_text(encoding="utf-8")
        script.write_text(
            source.replace("__MMDB_PATH__", str(database)).replace("__BACKUP_DIR__", str(backup)),
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "VALIDATOR_STATUS": str(validator),
            "DOWNLOAD_STATUS": str(download),
            "HAS_ASSET": "1" if asset else "0",
            "DOCKER_ARGS": str(root / "docker-args.json"),
        }
        result = subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=15
        )
        self.assertEqual(list(data.glob(".update.*")), [data / ".update.lock"])
        return result, root, database, backup

    def test_validated_download_atomically_replaces_and_backs_up(self):
        result, root, database, backup = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(database.read_bytes(), b"validated-download")
        self.assertEqual([p.read_bytes() for p in backup.glob("*.mmdb")], [b"original-database"])
        args = json.loads((root / "docker-args.json").read_text())
        self.assertIn("--no-build", args)
        self.assertIn("geoip-api", args)
        self.assertTrue(args[-1].startswith("/data/.update."))

    def test_validation_failure_preserves_installed_database(self):
        result, _, database, backup = self.run_update(validator=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(database.read_bytes(), b"original-database")
        self.assertEqual(list(backup.glob("*.mmdb")), [])

    def test_download_and_asset_failure_never_run_validator(self):
        for kwargs in ({"download": 22}, {"asset": False}):
            with self.subTest(kwargs=kwargs):
                result, root, database, _ = self.run_update(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "docker-args.json").exists())
                self.assertEqual(database.read_bytes(), b"original-database")


if __name__ == "__main__":
    unittest.main()
