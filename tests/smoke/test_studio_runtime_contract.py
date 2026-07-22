from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StudioRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        nginx_start = compose.index("  nginx:\n")
        studio_start = compose.index("\n  studio:\n", nginx_start) + 1
        cls.nginx = compose[nginx_start:studio_start]
        studio_end = compose.index("  # postgres:", studio_start)
        cls.studio = compose[studio_start:studio_end]

    def test_studio_listens_on_the_docker_interface(self) -> None:
        self.assertIn('HOSTNAME: "0.0.0.0"', self.studio)

    def test_studio_healthcheck_matches_the_dashboard_listener(self) -> None:
        self.assertIn("http://localhost:3000/api/platform/profile", self.studio)
        self.assertIn("start_period: 20s", self.studio)
        self.assertIn("timeout: 10s", self.studio)

    def test_gateway_starts_after_the_studio_container_exists(self) -> None:
        self.assertIn("depends_on:", self.nginx)
        self.assertIn("studio:", self.nginx)
        self.assertIn("condition: service_started", self.nginx)

    def test_gateway_proxies_job_api_instead_of_flutter_fallback(self) -> None:
        nginx_conf = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        jobs_start = nginx_conf.index("location ~ ^/api/jobs(/.*)?$")
        jobs_end = nginx_conf.index("location = /api/platform/profile", jobs_start)
        jobs_block = nginx_conf[jobs_start:jobs_end]

        self.assertIn("security/check_authenticated.lua", jobs_block)
        self.assertIn("X-Shared-Token $nginx_shared_token", jobs_block)
        self.assertIn("X-User-Token $auth_user_token", jobs_block)
        self.assertIn("proxy_pass $server_domain/api/jobs$1;", jobs_block)

    def test_api_auth_failure_is_json_while_pages_redirect_to_login(self) -> None:
        nginx_conf = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        handler = (
            ROOT / "studio/nginx/lua/security/authentication_required.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("error_page 401 = @authentication_required;", nginx_conf)
        self.assertIn("location @authentication_required", nginx_conf)
        self.assertIn('uri:sub(1, 5) == "/api/"', handler)
        self.assertIn('uri:sub(1, 15) == "/_internal_api/"', handler)
        self.assertIn("ngx.HTTP_UNAUTHORIZED", handler)
        self.assertIn('content_type = "application/json; charset=utf-8"', handler)
        self.assertIn("ngx.redirect", handler)

    def test_public_origin_uses_the_actual_request_authority(self) -> None:
        nginx_conf = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        self.assertIn('set $studio_public_origin "$scheme://$http_host";', nginx_conf)
        self.assertNotIn('$scheme://$host:9091', nginx_conf)
        self.assertIn("return 301 https://$http_host$request_uri;", nginx_conf)

    def test_flutter_centralizes_json_and_authentication_navigation(self) -> None:
        flutter_lib = ROOT / "studio/seletor_de_projetos/lib"
        dart_sources = {
            path.relative_to(flutter_lib).as_posix(): path.read_text(encoding="utf-8")
            for path in flutter_lib.rglob("*.dart")
        }
        raw_decoders = [
            relative
            for relative, source in dart_sources.items()
            if "jsonDecode(" in source and relative != "data/api_client.dart"
        ]

        self.assertEqual([], raw_decoders)
        self.assertNotIn(":9091", "\n".join(dart_sources.values()))
        self.assertIn("ApiClient.unauthorizedHandler = redirectToLogin", dart_sources["main.dart"])
        self.assertIn("redirectToLogout()", dart_sources["project_list_page.dart"])

    def test_authelia_storage_cli_has_private_runtime_credentials(self) -> None:
        nginx_conf = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        entrypoint = (ROOT / "studio/nginx/docker-entrypoint.sh").read_text(
            encoding="utf-8"
        )
        runtime_tool = (ROOT / "tools/configure_studio_runtime.py").read_text(
            encoding="utf-8"
        )

        for name in {
            "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE",
            "AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE",
        }:
            self.assertIn(name, self.nginx)
            self.assertIn(f"env {name};", nginx_conf)

        self.assertIn("- JWT_SECRET", self.nginx)
        self.assertIn("- STORAGE_ENCRYPTION_KEY", self.nginx)
        self.assertNotIn("- SESSION_SECRET", self.nginx)
        self.assertIn('install -m 400 -o 65534 -g 65534', entrypoint)
        self.assertIn("chmod 644 /config/configuration.runtime.yml", entrypoint)
        self.assertIn("atomic_write(target, rendered, mode=0o644", runtime_tool)


if __name__ == "__main__":
    unittest.main()
