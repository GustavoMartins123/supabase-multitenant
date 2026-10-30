import importlib.util
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
for name, path in (
    ("access_policy", ROOT / "servidor/api-internal/app/access_policy.py"),
    ("broadcast_admission", ROOT / "servidor/key-authorizer/admission.py"),
):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


class RealtimeHttpBroadcastTests(unittest.TestCase):
    def test_broadcast_is_admitted_as_realtime_and_requires_a_key(self):
        service, allow_missing, required, parts = module.route(
            "/project/realtime/v1/api/broadcast?probe=1", "project")
        self.assertEqual(service, "realtime")
        self.assertFalse(allow_missing)
        self.assertEqual(required, "")
        self.assertEqual(parts.query, "probe=1")

    def test_route_does_not_expose_other_realtime_api_paths(self):
        for path in ("/api/tenants", "/api/broadcast/extra", "/api/broadcasting"):
            with self.subTest(path=path), self.assertRaises(HTTPException) as caught:
                module.route("/project/realtime/v1" + path, "project")
            self.assertEqual(caught.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            module.route("/other/realtime/v1/api/broadcast", "project")

    def test_gateway_preserves_opaque_authorization_and_fixed_tenant(self):
        template = (ROOT / "servidor/generateProject/nginxtemplate").read_text()
        block = template.split("location = /realtime/v1/api/broadcast {", 1)[1].split(
            "location ^~ /realtime/v1/websocket", 1)[0]
        self.assertIn("auth_request /_internal/opaque-key-authorize;", block)
        self.assertIn("set $opaque_target_service realtime;", block)
        self.assertIn("proxy_pass http://$realtime_upstream/api/broadcast$is_args$args;", block)
        self.assertIn('proxy_set_header Host "{{project_uuid}}.localhost";', block)
        self.assertIn("proxy_set_header apikey $opaque_upstream_apikey;", block)
        self.assertIn("proxy_set_header Authorization $opaque_upstream_authorization;", block)


if __name__ == "__main__":
    unittest.main()
