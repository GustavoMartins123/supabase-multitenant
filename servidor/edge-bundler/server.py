"""Isolated SSRF-filtered HTTP service that compiles Edge Functions to offline ESZIP bundles."""
from __future__ import annotations

import base64
from contextlib import suppress
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

from policy import (
    BundleBuildError,
    DEFAULT_ALLOWED_REGISTRIES,
    DependencyPolicyError,
    MAX_ESZIP_BYTES,
    validate_dependency_policy,
)

MAX_REQUEST_BYTES = 10 * 1024 * 1024
MAX_FILES = 32
MAX_TOTAL_SOURCE_BYTES = 6 * 1024 * 1024
MAX_HMAC_SKEW_SECONDS = 60
REGISTRY_HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")

try:
    _CONCURRENCY = max(1, min(4, int(os.environ.get("EDGE_BUNDLER_CONCURRENCY", "2") or "2")))
except ValueError:
    _CONCURRENCY = 2
_BUNDLE_SEM = threading.BoundedSemaphore(_CONCURRENCY)


def find_bundler_bin() -> str | None:
    configured = (os.environ.get("EDGE_FUNCTIONS_BUNDLER_BIN") or "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    return shutil.which("edge-runtime")


def allowed_registries() -> frozenset[str]:
    raw = (os.environ.get("EDGE_BUNDLER_ALLOWED_REGISTRIES") or "").strip()
    if not raw:
        return DEFAULT_ALLOWED_REGISTRIES
    hosts: set[str] = set()
    for part in raw.split(","):
        host = part.strip().lower()
        if not host:
            continue
        if (
            host == "localhost"
            or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid"))
            or not REGISTRY_HOST_RE.fullmatch(host)
        ):
            raise BundleBuildError(f"Invalid package registry hostname configured: {host}")
        hosts.add(host)
    return frozenset(hosts or DEFAULT_ALLOWED_REGISTRIES)


def _is_public_global_ip(raw_ip: str) -> bool:
    addr = ipaddress.ip_address(raw_ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return bool(
        addr.is_global
        and not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_multicast
        and not addr.is_reserved
        and not addr.is_unspecified
    )


class _RegistryConnectProxy:
    """Ephemeral localhost HTTPS CONNECT proxy restricted to public-IP approved registries."""

    def __init__(self, registries: frozenset[str]):
        self._registries = registries
        self._server: socket.socket | None = None
        self._stop = False
        self._thread: threading.Thread | None = None
        self.port = 0

    def __enter__(self) -> str:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(64)
        srv.settimeout(0.2)
        self._server = srv
        self.port = int(srv.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *args) -> None:
        self._stop = True
        if self._server is not None:
            with suppress(OSError):
                self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        assert self._server is not None
        while not self._stop:
            try:
                client, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            client.settimeout(10.0)
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 8192:
                chunk = client.recv(4096)
                if not chunk:
                    return
                buf += chunk
            head = buf.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
            parts = head.split(" ", 2)
            if len(parts) != 3 or parts[0].upper() != "CONNECT" or ":" not in parts[1]:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            host, port_str = parts[1].rsplit(":", 1)
            host = host.strip("[]").lower()
            if not port_str.isdigit() or int(port_str) != 443 or host not in self._registries:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            ips = list(dict.fromkeys(info[4][0] for info in infos))
            if not ips or not all(_is_public_global_ip(ip) for ip in ips):
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            ordered_ips = sorted(ips, key=lambda raw: 0 if ":" not in raw else 1)
            last_err: OSError | None = None
            for candidate_ip in ordered_ips:
                try:
                    upstream = socket.create_connection((candidate_ip, 443), timeout=15.0)
                    break
                except OSError as err:
                    last_err = err
            if upstream is None:
                raise last_err or OSError("Unable to connect to upstream registry")
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client.setblocking(False)
            upstream.setblocking(False)
            sockets = [client, upstream]
            while not self._stop:
                readable, _, _ = select.select(sockets, [], [], 30.0)
                if not readable:
                    break
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    peer = upstream if sock is client else client
                    peer.sendall(data)
        except Exception:
            with suppress(OSError):
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        finally:
            if upstream is not None:
                with suppress(OSError):
                    upstream.close()
            with suppress(OSError):
                client.close()


def _write_temp_function_tree(src_dir: Path, files: list[dict]) -> bool:
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise DependencyPolicyError(f"Expected 1 to {MAX_FILES} function files")
    has_wasm = False
    has_entrypoint = False
    total_bytes = 0
    seen_names: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise DependencyPolicyError("Invalid file entry payload")
        raw_name = str(entry.get("name", ""))
        rel = PurePosixPath(raw_name)
        if not raw_name or rel.is_absolute() or ".." in rel.parts or any(p in {"", "."} for p in rel.parts):
            raise DependencyPolicyError(f"Unsafe relative file path: {raw_name}")
        norm = rel.as_posix()
        if norm in seen_names or norm.lower().endswith(".eszip"):
            raise DependencyPolicyError(f"Duplicate or reserved filename: {norm}")
        seen_names.add(norm)
        if norm == "index.ts":
            has_entrypoint = True
        dest = src_dir / norm
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = entry.get("content")
        if not isinstance(content, str):
            raise DependencyPolicyError(f"File content must be a string: {norm}")
        if entry.get("encoding") == "base64":
            try:
                raw_bytes = base64.b64decode(content, validate=True)
            except Exception as err:
                raise DependencyPolicyError(f"Invalid base64 payload for {norm}") from err
            total_bytes += len(raw_bytes)
            has_wasm = True
            dest.write_bytes(raw_bytes)
        else:
            raw_bytes = content.encode("utf-8")
            total_bytes += len(raw_bytes)
            if rel.suffix.lower() == ".wasm":
                has_wasm = True
            dest.write_bytes(raw_bytes)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise DependencyPolicyError("Combined function files exceed maximum bundler limit")
    if not has_entrypoint:
        raise DependencyPolicyError("Function bundle must contain index.ts")
    return has_wasm


def compile_function_eszip(files: list[dict]) -> bytes:
    """Validate dependencies and compile files into an offline-ready ESZIP binary."""
    validate_dependency_policy(files)
    bundler_bin = find_bundler_bin()
    if not bundler_bin:
        raise BundleBuildError("Edge Function dependency bundler binary is unavailable")
    timeout_raw = int(os.environ.get("EDGE_BUNDLER_TIMEOUT_SECONDS", "60") or "60")
    timeout_sec = max(5, min(120, timeout_raw))
    cache_dir = Path(
        os.environ.get("EDGE_FUNCTIONS_BUNDLER_CACHE_DIR")
        or (Path(tempfile.gettempdir()) / "edge-functions-bundler-cache")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(cache_dir, 0o700)
    registries = allowed_registries()

    with _BUNDLE_SEM:
        with tempfile.TemporaryDirectory(prefix="edge-bundle-") as temp_root:
            root_path = Path(temp_root)
            src_dir = root_path / "src"
            home_dir = root_path / "home"
            src_dir.mkdir(parents=True)
            home_dir.mkdir(parents=True)
            has_wasm = _write_temp_function_tree(src_dir, files)
            out_path = root_path / "bundle.eszip"
            command = [
                bundler_bin,
                "bundle",
                "--entrypoint",
                str(src_dir / "index.ts"),
                "--output",
                str(out_path),
                "--timeout",
                str(timeout_sec),
            ]
            if has_wasm:
                command.extend(["--static", str(src_dir / "**" / "*.wasm")])
            with _RegistryConnectProxy(registries) as proxy_url:
                env = {
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": str(home_dir),
                    "DENO_DIR": str(cache_dir),
                    "HTTPS_PROXY": proxy_url,
                    "https_proxy": proxy_url,
                    "HTTP_PROXY": "http://127.0.0.1:0",
                    "http_proxy": "http://127.0.0.1:0",
                    "NO_PROXY": "",
                    "no_proxy": "",
                }
                try:
                    proc = subprocess.run(
                        command,
                        cwd=str(root_path),
                        env=env,
                        capture_output=True,
                        timeout=timeout_sec + 5,
                        check=False,
                    )
                except subprocess.TimeoutExpired as error:
                    raise BundleBuildError("Dependency bundling timed out") from error
                if proc.returncode != 0 or not out_path.is_file():
                    raw_err = (proc.stderr or proc.stdout).decode("utf-8", errors="replace").strip()
                    raw_err = raw_err.replace(f"file://{src_dir}/", "").replace(f"{src_dir}/", "")
                    lines = [ln.strip() for ln in raw_err.splitlines() if ln.strip()]
                    summary = " | ".join(lines)[:400] if lines else "Unknown bundler failure"
                    raise BundleBuildError(f"Failed to bundle Edge Function dependencies: {summary}")
                data = out_path.read_bytes()
    if not data.startswith(b"ESZIP") or len(data) > MAX_ESZIP_BYTES:
        raise BundleBuildError("Generated ESZIP bundle failed format or size validation")
    return data


def _verify_hmac(raw_body: bytes, timestamp_hdr: str, signature_hdr: str, secret: str) -> bool:
    if not secret:
        return True
    if not timestamp_hdr or not signature_hdr:
        return False
    try:
        ts = int(timestamp_hdr.strip())
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > MAX_HMAC_SKEW_SECONDS:
        return False
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("ascii") + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature_hdr.strip().lower())


class BundlerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            if find_bundler_bin():
                self._send_json(HTTPStatus.OK, {"status": "ok"})
            else:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unavailable"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/bundle":
            self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"detail": "application/json required"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"detail": "Payload size out of bounds"})
            return
        raw_body = self.rfile.read(length)
        if len(raw_body) != length:
            self._send_json(HTTPStatus.BAD_REQUEST, {"detail": "Incomplete request body"})
            return
        secret = (os.environ.get("EDGE_BUNDLER_HMAC_SECRET") or "").strip()
        if not _verify_hmac(
            raw_body,
            self.headers.get("X-Edge-Bundler-Timestamp") or "",
            self.headers.get("X-Edge-Bundler-Signature") or "",
            secret,
        ):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"detail": "Invalid bundler signature"})
            return
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"detail": "Invalid UTF-8 JSON body"})
            return
        files = body.get("files") if isinstance(body, dict) else None
        if not isinstance(files, list):
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "files array is required"})
            return
        try:
            eszip = compile_function_eszip(files)
        except DependencyPolicyError as err:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(err), "kind": "policy"})
            return
        except BundleBuildError as err:
            status = HTTPStatus.GATEWAY_TIMEOUT if "timed out" in str(err).lower() else HTTPStatus.UNPROCESSABLE_ENTITY
            self._send_json(status, {"detail": str(err), "kind": "bundle"})
            return
        self._send_json(
            HTTPStatus.OK,
            {"eszip_b64": base64.b64encode(eszip).decode("ascii"), "size": len(eszip)},
        )


def main() -> None:
    port = int(os.environ.get("EDGE_BUNDLER_PORT", "18030") or "18030")
    server = ThreadingHTTPServer(("0.0.0.0", port), BundlerHandler)
    print(f"edge-bundler listening on :{port}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
