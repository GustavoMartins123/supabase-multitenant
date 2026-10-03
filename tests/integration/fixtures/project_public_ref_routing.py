from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from hostagent.templates import sync_project_generated_files


ROOT = Path(__file__).resolve().parents[3]
REF = "abcdefghijklmnopqrst"
NAME = "technical_project"
TENANT = "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa"
CONFIG_TOKEN = "a" * 64
GATEWAY_TOKEN = "b" * 64


def prepare(directory: Path) -> None:
    project = directory / "projects" / NAME
    project.mkdir(parents=True)
    (directory / ".env").write_text(
        "SERVER_URL=api.example.test\nSERVER_PROTO=http\nHOST_PROJECT_ROOT=/srv/test\n",
        encoding="utf-8",
    )
    (project / ".env").write_text(
        f"PROJECT_ID={NAME}\nPROJECT_UUID={TENANT}\nPROJECT_PUBLIC_REF={REF}\n"
        f"CONFIG_TOKEN_PROJETO={CONFIG_TOKEN}\nAPI_GATEWAY_TOKEN_PROJETO={GATEWAY_TOKEN}\n"
        f"JWT_SECRET_PROJETO={'c' * 43}\nANON_KEY_PROJETO=header.payload.sig\n"
        "SERVICE_ROLE_KEY_PROJETO=header.payload.sig\n", encoding="utf-8",
    )
    sync_project_generated_files(root=directory, scripts_dir=ROOT / "servidor/generateProject",
                                 project_dir=project, project=NAME)
    (project / "nginx" / f"nginx_{NAME}.conf").chmod(0o644)
    spec = importlib.util.spec_from_file_location("routing_renderer", ROOT / "servidor/traefik/render_dynamic_config.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    dynamic = directory / "dynamic"
    dynamic.mkdir()
    (dynamic / "projects.yml").write_text(renderer.render(directory / ".env", directory / "projects"), encoding="utf-8")
    (dynamic / "middlewares.yml").write_text(
        "http:\n  middlewares:\n    rate-limit:\n      rateLimit:\n        average: 100\n        burst: 100\n"
        "    security-headers:\n      headers:\n        contentTypeNosniff: true\n"
        "    api-security-chain:\n      chain:\n        middlewares: []\n", encoding="utf-8",
    )
    (directory / "traefik.yml").write_text(
        "entryPoints:\n  web:\n    address: ':8080'\nproviders:\n  file:\n    directory: /test/dynamic\n"
        "experimental:\n  localPlugins:\n    supabaseguard:\n      moduleName: github.com/GustavoMartins123/supabaseguard\n"
        "log:\n  level: ERROR\n", encoding="utf-8",
    )
    (directory / "deny-authorizer.conf").write_text(
        "pid /tmp/deny.pid;\nevents {}\nhttp { access_log off;"
        "client_body_temp_path /tmp/client_temp; proxy_temp_path /tmp/proxy_temp;"
        "fastcgi_temp_path /tmp/fastcgi_temp; uwsgi_temp_path /tmp/uwsgi_temp;"
        "scgi_temp_path /tmp/scgi_temp; server { listen 18010;"
        "location = /v1/authorize {"
        f'if ($http_x_project_ref != "{NAME}") {{ return 500; }}'
        f'if ($http_x_project_gateway_token != "{GATEWAY_TOKEN}") {{ return 500; }}'
        "return 403; } } }\n", encoding="utf-8",
    )


def request(path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request("http://router:8080" + path,
                                 headers={"Host": "api.example.test", **(headers or {})})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def verify() -> None:
    deadline = time.monotonic() + 45
    last_response: object = None
    while True:
        try:
            status, body = request(f"/{REF}/config", {"X-Config-Token": CONFIG_TOKEN})
            last_response = (status, body[:200])
            if status == 200:
                break
        except urllib.error.URLError as error:
            last_response = str(error)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Public routing did not become ready: {last_response}")
        time.sleep(1)
    assert json.loads(body) == {"supabase_url": f"http://api.example.test/{REF}"}
    assert request(f"/{REF}/config")[0] == 401
    assert request(f"/{REF}/config", {"X-Config-Token": "invalid"})[0] == 401
    for path in (f"/{NAME}/config", f"/{TENANT}/config", f"/{REF}x/config"):
        assert request(path, {"X-Config-Token": CONFIG_TOKEN})[0] == 404, path
    for service in ("rest", "auth", "storage", "functions"):
        assert request(f"/{REF}/{service}/v1/test", {"X-Project-Ref": REF})[0] == 403, service
    print("PASS: real Traefik/Nginx serve the public reference and reject name, UUID and prefix aliases")
    print("PASS: /config still requires its token; protected services reach the deny-authorizer with fixed technical identity")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]))
    elif sys.argv[1] == "verify":
        verify()
    else:
        raise SystemExit("Expected prepare or verify")
