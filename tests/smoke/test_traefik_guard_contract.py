from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TraefikGuardContractTests(unittest.TestCase):
    def test_local_plugin_replaces_legacy_fail2ban(self) -> None:
        static = (ROOT / "servidor/traefik/traefik.yml").read_text(encoding="utf-8")
        dynamic = (ROOT / "servidor/traefik/middlewares.yml").read_text(encoding="utf-8")

        self.assertIn("localPlugins:", static)
        self.assertIn("github.com/GustavoMartins123/supabaseguard", static)
        self.assertNotIn("github.com/tomMoulard/fail2ban", static)
        self.assertNotIn("monitoredStatusCodes", dynamic)
        self.assertNotIn("fail2ban-global", dynamic)
        self.assertNotIn("fail2ban-malicious", dynamic)

    def test_plugin_is_mounted_from_expected_local_path(self) -> None:
        compose = (ROOT / "servidor/traefik/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("working_dir: /", compose)
        self.assertIn("./plugins-local:/plugins-local:ro", compose)

    def test_project_router_has_uuid_scoped_guard_before_strip_prefix(self) -> None:
        renderer = (
            ROOT / "servidor/traefik/render_dynamic_config.py"
        ).read_text(encoding="utf-8")
        template = (
            ROOT / "servidor/generateProject/dockercomposetemplate"
        ).read_text(encoding="utf-8")

        self.assertIn('"          profile: project"', renderer)
        self.assertIn('f"          scope: {yaml_quote(project_uuid)}"', renderer)
        self.assertIn('f"        - project-guard-{project_id}"', renderer)
        self.assertIn('f"        - project-strip-{project_id}"', renderer)
        self.assertNotIn("traefik.", template)
        self.assertNotIn("labels:", template)

    def test_project_defaults_are_declared(self) -> None:
        env_example = (ROOT / "servidor/.env.example").read_text(encoding="utf-8")
        for key in (
            "TRAEFIK_GUARD_PROJECT_MODE",
            "TRAEFIK_GUARD_MAX_TRACKED_CLIENTS",
            "TRAEFIK_GUARD_CLEANUP_INTERVAL",
            "TRAEFIK_GUARD_AUTH_THRESHOLD",
            "TRAEFIK_GUARD_AUTH_WINDOW",
            "TRAEFIK_GUARD_AUTH_BAN_TIME",
            "TRAEFIK_GUARD_SCANNER_THRESHOLD",
            "TRAEFIK_GUARD_SCANNER_WINDOW",
            "TRAEFIK_GUARD_SCANNER_BAN_TIME",
        ):
            self.assertIn(f"{key}=", env_example)

    def test_malicious_router_uses_existing_web_entrypoint(self) -> None:
        dynamic = (ROOT / "servidor/traefik/middlewares.yml").read_text(encoding="utf-8")
        self.assertNotIn("websecure", dynamic)
        self.assertNotIn("tls: {}", dynamic)


if __name__ == "__main__":
    unittest.main()
