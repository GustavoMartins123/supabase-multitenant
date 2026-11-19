"""Contract and unit checks for SEC-08/09/11/12/14 parity with IDR hardening."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "servidor"
STUDIO = ROOT / "studio"
API_ROOT = SERVER / "api-internal"
HOST_AGENT_ROOT = SERVER / "host-agent"


class Phase1SecuritySyncTest(unittest.TestCase):
    def test_sec08_optional_jwt_secret_rotation_and_storage_3_networks(self) -> None:
        storage_lib = (SERVER / "generateProject/lib/storage_multitenant.sh").read_text(encoding="utf-8")
        self.assertIn('[[ "$attached_count" == "3" ]]', storage_lib)
        self.assertIn("grep -Fxq 'supabase-imgproxy-internal'", storage_lib)
        self.assertIn("jwtSecret: .[2]", storage_lib)

        rotate_sh = (SERVER / "generateProject/rotate_key.sh").read_text(encoding="utf-8")
        self.assertIn('ROTATE_JWT_SECRET="${ROTATE_JWT_SECRET:-false}"', rotate_sh)
        self.assertIn("--rotate-jwt-secret", rotate_sh)
        self.assertIn("realtime_patch_tenant_jwt_secret", rotate_sh)
        self.assertIn('SERVICES_TO_RECREATE=(auth rest nginx)', rotate_sh)

        if str(API_ROOT) not in sys.path:
            sys.path.insert(0, str(API_ROOT))
        from app.host_agent_protocol import validate_command_args

        self.assertEqual(validate_command_args("rotate_keys", "demo", {"trigger": "manual"}), [])
        self.assertEqual(
            validate_command_args("rotate_keys", "demo", {"trigger": "manual", "rotate_jwt_secret": True}),
            [],
        )
        self.assertIn(
            "automatic_jwt_secret_rotation_not_allowed",
            validate_command_args("rotate_keys", "demo", {"trigger": "automatic", "rotate_jwt_secret": True}),
        )

    def test_sec09_host_agent_logs_fail_closed_when_unlabeled(self) -> None:
        commands = (HOST_AGENT_ROOT / "hostagent/commands.py").read_text(encoding="utf-8")
        self.assertIn("if owner != project:", commands)
        self.assertNotIn("if owner is not None and owner != project:", commands)

    def test_sec11_pg_hba_script_generates_strict_cidrs_and_rejects_catchall(self) -> None:
        hba_static = (SERVER / "volumes/db/pg_hba.conf").read_text(encoding="utf-8")
        self.assertIn("0.0.0.0/0               reject", hba_static)
        self.assertIn("::/0                    reject", hba_static)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = pathlib.Path(tmp) / "pg_hba.conf"
            proc = subprocess.run(
                ["bash", str(SERVER / "volumes/db/configure-pg-hba.sh")],
                env={
                    "PATH": "/usr/bin:/bin",
                    "PG_HBA_OUTPUT_PATH": str(out_path),
                    "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                    "PG_HBA_ALLOWED_CIDRS": "172.51.2.0/28,0.0.0.0/0,::/0",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rendered = out_path.read_text(encoding="utf-8")
            self.assertIn("172.50.0.0/16", rendered)
            self.assertIn("172.51.2.0/28", rendered)
            self.assertIn("0.0.0.0/0               reject", rendered)
            self.assertIn("::/0                    reject", rendered)
            self.assertNotIn("0.0.0.0/0               scram-sha-256", rendered)

    def test_sec11_edge_functions_and_project_network_isolation(self) -> None:
        compose = (SERVER / "docker-compose.yml").read_text(encoding="utf-8")
        fn_block = compose.split("\n  functions:", 1)[1].split("\n  storage:", 1)[0]
        self.assertIn("/tmp:rw,noexec,nosuid,size=128m", fn_block)
        self.assertIn("- functions-gateways", fn_block)
        self.assertIn("- functions-db", fn_block)
        self.assertIn("- project-egress", fn_block)
        self.assertNotIn("- rede-supabase", fn_block)
        self.assertIn('com.docker.network.bridge.enable_icc: "false"', compose)

        index_ts = (SERVER / "volumes/functions/main/index.ts").read_text(encoding="utf-8")
        self.assertIn("x-edge-gateway-token", index_ts)
        self.assertIn("canonical.edge_gateway_token", index_ts)

        proj_compose = (SERVER / "generateProject/dockercomposetemplate").read_text(encoding="utf-8")
        nginx_block = proj_compose.split("  nginx:\n", 1)[1].split("\n  auth:\n", 1)[0]
        auth_block = proj_compose.split("\n  auth:\n", 1)[1].split("\n  rest:\n", 1)[0]
        rest_block = proj_compose.split("\n  rest:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        for net in ("rede-supabase", "storage-gateways", "functions-gateways", "project-internal"):
            self.assertIn(f"- {net}", nginx_block)
        self.assertNotIn("- rede-supabase", auth_block)
        self.assertIn("- project-internal", auth_block)
        self.assertIn("- project-egress", auth_block)
        self.assertIn("condition: service_healthy", auth_block)
        self.assertNotIn("- rede-supabase", rest_block)
        self.assertNotIn("- project-egress", rest_block)
        self.assertIn("- project-internal", rest_block)
        self.assertIn("condition: service_healthy", rest_block)

        nginx_tpl = (SERVER / "generateProject/nginxtemplate").read_text(encoding="utf-8")
        self.assertIn('proxy_set_header X-Edge-Gateway-Token "${API_GATEWAY_TOKEN_PROJETO}";', nginx_tpl)
        self.assertIn("allow ${PROJECT_INTERNAL_SUBNET};", nginx_tpl)
        self.assertIn('default "template-service:18020";', nginx_tpl)
        self.assertIn("proxy_pass $stream_template_service_upstream;", nginx_tpl)
        self.assertNotIn("proxy_pass template-service:18020;", nginx_tpl)

        spec = importlib.util.spec_from_file_location(
            "allocate_project_subnet", SERVER / "generateProject/allocate_project_subnet.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = pathlib.Path(tmp)
            a = mod.allocate_project_internal_subnet("proj_alpha", pdir, inspect_docker=False)
            (pdir / "proj_alpha").mkdir()
            (pdir / "proj_alpha/.env").write_text(f"PROJECT_INTERNAL_SUBNET={a}\n", encoding="utf-8")
            b = mod.allocate_project_internal_subnet("proj_beta", pdir, inspect_docker=False)
            self.assertNotEqual(a, b)
            self.assertEqual(mod.allocate_project_internal_subnet("proj_alpha", pdir, inspect_docker=False), a)

    def test_sec12_sec14_headers_password_auth_fernet_hmac_and_ai_reader(self) -> None:
        sec_headers = (STUDIO / "nginx/lua/snippets/security_headers.conf").read_text(encoding="utf-8")
        self.assertIn("Strict-Transport-Security $hsts_header always;", sec_headers)
        self.assertIn('X-Content-Type-Options "nosniff" always;', sec_headers)
        self.assertIn('Content-Security-Policy "frame-ancestors \'self\';" always;', sec_headers)

        nginx_conf = (STUDIO / "nginx/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("include /usr/local/openresty/lualib/snippets/security_headers.conf;", nginx_conf)
        change_pwd_block = nginx_conf.split("location = /auth/api/change-password {", 1)[1].split("}", 1)[0]
        self.assertNotIn("auth_request off;", change_pwd_block)

        fernet_lua = (STUDIO / "nginx/lua/resty/fernet.lua").read_text(encoding="utf-8")
        self.assertLess(fernet_lua.index("secure_compare.equals(mac_a, mac_b)"), fernet_lua.index("issued_time"))

        hmac_lua = (STUDIO / "nginx/lua/security/internal_hmac.lua").read_text(encoding="utf-8")
        self.assertIn("nonce_cache:safe_add(", hmac_lua)
        self.assertIn("ngx.HTTP_SERVICE_UNAVAILABLE", hmac_lua)

        insights = (API_ROOT / "app/routers/project_insights.py").read_text(encoding="utf-8")
        self.assertIn("p.provolatile AS volatility", insights)
        self.assertIn("meta_conn.transaction(readonly=True)", insights)


if __name__ == "__main__":
    unittest.main()
