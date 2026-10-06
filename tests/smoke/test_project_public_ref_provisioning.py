from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/host-agent"))
from hostagent import templates, host_agent_protocol as protocol  # noqa: E402
from hostagent.agent import HostAgent  # noqa: E402

REF = "abcdefghijklmnopqrst"
TENANT = "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa"
NAME = "technical_project"
SCRIPTS = ROOT / "servidor/generateProject"
spec = importlib.util.spec_from_file_location("public_ref_traefik", ROOT / "servidor/traefik/render_dynamic_config.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class PublicRefRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "projects" / NAME
        self.project.mkdir(parents=True)
        (self.root / ".env").write_text(
            'SERVER_URL=api.example.test\nSERVER_PROTO=https\nHOST_PROJECT_ROOT="/srv/project root"\n',
            encoding="utf-8",
        )
        self.env_text = (
            f"PROJECT_ID={NAME}\nPROJECT_UUID={TENANT}\nPROJECT_PUBLIC_REF={REF}\n"
            f"API_GATEWAY_TOKEN_PROJETO={'b' * 64}\n"
            f"JWT_SECRET_PROJETO={'c' * 43}\nANON_KEY_PROJETO=header.payload.sig\n"
            "SERVICE_ROLE_KEY_PROJETO=header.payload.sig\n"
        )
        (self.project / ".env").write_text(self.env_text, encoding="utf-8")

    def test_recreate_uses_public_paths_and_preserves_internal_resources(self) -> None:
        templates.sync_project_generated_files(
            root=self.root, scripts_dir=SCRIPTS, project_dir=self.project, project=NAME,
        )
        nginx = (self.project / "nginx" / f"nginx_{NAME}.conf").read_text(encoding="utf-8")
        compose = (self.project / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn('location = /config', nginx)
        self.assertIn(f'X-Forwarded-Prefix "/{REF}/storage/v1"', nginx)
        self.assertIn(f"X-Original-URI /{REF}$request_uri", nginx)
        self.assertIn(f"/{REF}/storage/v1/upload/resumable/", nginx)
        self.assertNotIn(f"/{NAME}/", nginx)
        self.assertIn(f"supabase-auth-{NAME}:9999", nginx)
        self.assertIn(f'X-Project-Ref "{NAME}"', nginx)
        self.assertIn(f"container_name: supabase-nginx-{NAME}", compose)
        self.assertIn(f"${{AUTH_DB_USER}}.{NAME}", compose)

    def test_recreate_refuses_missing_or_invalid_public_reference(self) -> None:
        for bad in ("", "short", NAME, REF.upper(), "a" * 19 + "á"):
            (self.project / ".env").write_text(
                self.env_text.replace(f"PROJECT_PUBLIC_REF={REF}\n", f"PROJECT_PUBLIC_REF={bad}\n"),
                encoding="utf-8",
            )
            with self.subTest(ref=bad), self.assertRaises(RuntimeError):
                templates.sync_project_generated_files(
                    root=self.root, scripts_dir=SCRIPTS, project_dir=self.project, project=NAME,
                )
            self.assertFalse((self.project / "docker-compose.yml").exists())

    def test_env_render_replaces_derived_urls_without_restoring_backup_identity(self) -> None:
        replacements = templates._build_replacements(self.root, self.project, NAME)
        replacements.update(
            s3_protocol_credential_id=TENANT, s3_protocol_access_key_id="d" * 32,
            s3_protocol_access_key_secret="e" * 64,
        )
        old_env = self.root / "backup.env"
        old_env.write_text(
            "PROJECT_PUBLIC_REF=" + "z" * 20 + "\nSITE_URL=https://api.example.test/old_name/verify-success.html\n"
            "ADDITIONAL_REDIRECT_URLS=https://api.example.test/old_name/verify-success.html\n"
            "API_EXTERNAL_URL=https://api.example.test/old_name/auth/v1\nDISABLE_SIGNUP=true\n",
            encoding="utf-8",
        )
        for script in ("render_project_env.py", "render_migrated_project_env.py"):
            output = self.root / f"{script}.env"
            args = [str(SCRIPTS / script), str(SCRIPTS / ".envtemplate")]
            args += [str(old_env), str(output)]
            result = subprocess.run([sys.executable, *args], input=json.dumps(replacements),
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = renderer.read_env(output)
            self.assertEqual(values["PROJECT_PUBLIC_REF"], REF)
            self.assertEqual(values["PROJECT_ID"], NAME)
            self.assertEqual(values["POSTGRES_DATABASE"], "_supabase_" + NAME)
            self.assertEqual(values["API_EXTERNAL_URL"], f"https://api.example.test/{REF}/auth/v1")
            self.assertEqual(values["SITE_URL"], f"https://api.example.test/{REF}/verify-success.html")
            self.assertEqual(values["DISABLE_SIGNUP"], "true")

    def test_env_render_preserves_custom_application_redirects(self) -> None:
        replacements = templates._build_replacements(self.root, self.project, NAME)
        replacements.update(s3_protocol_credential_id=TENANT, s3_protocol_access_key_id="d" * 32,
                            s3_protocol_access_key_secret="e" * 64)
        old_env = self.root / "custom.env"
        old_env.write_text(
            "API_EXTERNAL_URL=https://old.example.test/old_name/auth/v1\n"
            "SITE_URL=https://app.example.test/welcome\n"
            "ADDITIONAL_REDIRECT_URLS=https://old.example.test/old_name/verify-success.html,"
            "https://app.example.test/callback,myapp://callback\n", encoding="utf-8",
        )
        for script in ("render_project_env.py", "render_migrated_project_env.py"):
            output = self.root / f"custom-{script}.env"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / script), str(SCRIPTS / ".envtemplate"), str(old_env), str(output)],
                input=json.dumps(replacements), text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            values = renderer.read_env(output)
            self.assertEqual(values["SITE_URL"], "https://app.example.test/welcome")
            self.assertEqual(values["ADDITIONAL_REDIRECT_URLS"],
                             f"https://api.example.test/{REF}/verify-success.html,"
                             "https://app.example.test/callback,myapp://callback")

    def test_env_render_rejects_ambiguous_old_auth_url_before_writing(self) -> None:
        old_env = self.root / "invalid.env"
        for old_auth in ("", "relative/auth/v1", "https://old.example.test/wrong"):
            old_env.write_text(f"SITE_URL=https://app.example.test\nAPI_EXTERNAL_URL={old_auth}\n", encoding="utf-8")
            for script in ("render_project_env.py", "render_migrated_project_env.py"):
                output = self.root / f"invalid-{script}.env"
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / script), str(SCRIPTS / ".envtemplate"), str(old_env), str(output)],
                    input=json.dumps({"project_public_url": f"https://api.example.test/{REF}"}),
                    text=True, capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("API_EXTERNAL_URL", result.stderr)
                self.assertFalse(output.exists())

    def test_traefik_exposes_only_ref_and_keeps_technical_upstream(self) -> None:
        (self.root / ".env").write_text("SERVER_PROTO=http\nACCESS_ADMISSION_SECRET=" + "a" * 64 + "\nACCESS_TRUSTED_PROXY_CIDRS=\n", encoding="utf-8")
        model = yaml.safe_load(renderer.render(self.root / ".env", self.root / "projects"))
        http = model["http"]
        self.assertEqual(http["routers"][f"project-{NAME}"]["rule"],
                         f"Path(`/{REF}`) || PathPrefix(`/{REF}/`)")
        self.assertEqual(http["middlewares"][f"project-strip-{NAME}"]["stripPrefix"]["prefixes"], ["/" + REF])
        self.assertEqual(http["services"][f"project-{NAME}"]["loadBalancer"]["servers"],
                         [{"url": f"http://supabase-nginx-{NAME}:8080"}])
        self.assertEqual(http["middlewares"][f"project-guard-{NAME}"]["plugin"]["supabaseguard"]["scope"], TENANT)

    def test_traefik_refuses_missing_noncanonical_or_duplicate_ref(self) -> None:
        (self.root / ".env").write_text("SERVER_PROTO=http\nACCESS_ADMISSION_SECRET=" + "a" * 64 + "\nACCESS_TRUSTED_PROXY_CIDRS=\n", encoding="utf-8")
        for replacement in ("", "PROJECT_PUBLIC_REF=bad\n", f'PROJECT_PUBLIC_REF="{REF}"\n',
                            f"PROJECT_PUBLIC_REF={REF}\nPROJECT_PUBLIC_REF={REF}\n"):
            (self.project / ".env").write_text(
                self.env_text.replace(f"PROJECT_PUBLIC_REF={REF}\n", replacement), encoding="utf-8",
            )
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                renderer.render(self.root / ".env", self.root / "projects")
        (self.project / ".env").write_text(self.env_text, encoding="utf-8")
        other = self.root / "projects/another_project"
        other.mkdir()
        (other / ".env").write_text(self.env_text.replace(NAME, "another_project"), encoding="utf-8")
        with self.assertRaises(ValueError):
            renderer.render(self.root / ".env", self.root / "projects")

    def test_watcher_withdraws_previous_routes_when_canonical_config_fails(self) -> None:
        (self.root / ".env").write_text("SERVER_PROTO=http\nACCESS_ADMISSION_SECRET=" + "a" * 64 + "\nACCESS_TRUSTED_PROXY_CIDRS=\n", encoding="utf-8")
        middlewares = self.root / "middlewares.yml"
        middlewares.write_text("http:\n  middlewares: {}\n", encoding="utf-8")
        output = self.root / "dynamic/projects.yml"
        command = [sys.executable, str(ROOT / "servidor/traefik/render_dynamic_config.py"),
                   "--root-env", str(self.root / ".env"), "--projects-dir", str(self.root / "projects"),
                   "--middlewares-file", str(middlewares), "--output", str(output)]
        subprocess.run(command, check=True, capture_output=True)
        self.assertIn(REF, output.read_text(encoding="utf-8"))
        (self.project / ".env").write_text(self.env_text.replace(f"PROJECT_PUBLIC_REF={REF}\n", ""), encoding="utf-8")
        failed = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("Configuracao de rotas retirada", failed.stderr)
        self.assertEqual(yaml.safe_load(output.read_text(encoding="utf-8"))["http"]["routers"], {})


class ProvisioningIntentTest(unittest.TestCase):
    def test_protocol_requires_signed_public_reference(self) -> None:
        payloads = {
            "create_project": {"tenant_uuid": TENANT, "recover_stale": False, "stale_tenant_uuids": []},
            "duplicate_project": {"tenant_uuid": TENANT, "original_name": "source_project",
                                  "original_uuid": TENANT, "original_tenant_uuid": TENANT, "copy_mode": "schema-only"},
        }
        for command, payload in payloads.items():
            self.assertIn("invalid_public_ref", protocol.validate_command_args(command, NAME, payload))
            self.assertEqual(protocol.validate_command_args(command, NAME, {**payload, "public_ref": REF}), [])
            for invalid in (NAME, REF.upper(), REF + "\n", "a" * 19 + "á"):
                self.assertIn("invalid_public_ref", protocol.validate_command_args(command, NAME, {**payload, "public_ref": invalid}))

    @unittest.skipIf(os.name == "nt", "requires POSIX bash")
    def test_shell_public_ref_reader_does_not_normalize_or_invent_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            for content, valid in ((f"PROJECT_PUBLIC_REF={REF}\n", True), ("", False),
                                   (f'PROJECT_PUBLIC_REF="{REF}"\n', False),
                                   (f"PROJECT_PUBLIC_REF={REF}\nPROJECT_PUBLIC_REF={REF}\n", False),
                                   ("PROJECT_PUBLIC_REF=" + "a" * 19 + "á\n", False)):
                path.write_text(content, encoding="utf-8")
                result = subprocess.run(
                    ["bash", "-c", 'source "$1"; project_public_ref_read "$2"', "bash",
                     str(SCRIPTS / "lib/project_public_ref.sh"), str(path)], text=True, capture_output=True,
                )
                self.assertEqual(result.returncode == 0, valid)
                if valid:
                    self.assertEqual(result.stdout, REF)


class AgentPublicRefAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    def record(self, command: str, args: dict) -> dict:
        record = {"id": uuid.uuid4(), "project_uuid": uuid.uuid4(), "requested_by": None,
                  "issued_at": int(time.time()), "timeout_seconds": 60}
        record["signature"] = protocol.command_signature(
            "s" * 64, command_id=str(record["id"]), command=command, project=NAME,
            project_uuid=str(record["project_uuid"]), requested_by=None, args=args,
            issued_at=record["issued_at"], timeout_seconds=60,
        )
        return record

    async def test_agent_denies_signed_reference_not_owned_by_canonical_project(self) -> None:
        agent = HostAgent(SimpleNamespace(hmac_secret="s" * 64))
        args = {"public_ref": REF, "tenant_uuid": TENANT, "recover_stale": False, "stale_tenant_uuids": []}
        record = self.record("create_project", args)
        canonical = {"project_id": record["project_uuid"], "public_ref": "z" * 20}
        with patch("hostagent.agent.db.load_authorization_context", AsyncMock(return_value=canonical)):
            denial = await agent._revalidate(record, "create_project", NAME, args)
        self.assertEqual(denial[0], "authorization_denied:public_ref_mismatch")

    async def test_agent_denies_recreate_from_stale_physical_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / NAME
            project.mkdir(parents=True)
            (project / ".env").write_text(f"PROJECT_PUBLIC_REF={REF}\n", encoding="utf-8")
            agent = HostAgent(SimpleNamespace(hmac_secret="s" * 64, projects_root=projects))
            args = {"services": ["nginx"]}
            record = self.record("recreate_services", args)
            canonical = {"project_id": record["project_uuid"], "public_ref": "z" * 20}
            with patch("hostagent.agent.db.load_authorization_context", AsyncMock(return_value=canonical)):
                denial = await agent._revalidate(record, "recreate_services", NAME, args)
            self.assertEqual(denial[0], "authorization_denied:public_ref_mismatch")


if __name__ == "__main__":
    unittest.main()
