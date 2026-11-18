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
from urllib.parse import unquote

from policy import (
    BundleBuildError,
    DEFAULT_ALLOWED_REGISTRIES,
    DependencyPolicyError,
    MAX_ESZIP_BYTES,
    MAX_FILES,
    validate_dependency_policy,
    validate_registries_payload,
)

MAX_REQUEST_BYTES = 10 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 6 * 1024 * 1024
MAX_HMAC_SKEW_SECONDS = 60
REGISTRY_HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
PRIVATE_REGISTRY_HOST_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
_ESZIP_FILE_URI_RE = re.compile(rb"file://[^\x00-\x20\x7f\"'<>\\]*")
_THIS_NET_V4 = ipaddress.ip_network("0.0.0.0/8")
_NAT64_NET_V6 = ipaddress.ip_network("64:ff9b::/96")
_PROC_NET_ROUTE = Path("/proc/net/route")
_PROC_NET_FIB_TRIE = Path("/proc/net/fib_trie")
_PROC_NET_IF_INET6 = Path("/proc/net/if_inet6")

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


def allowed_private_registry_hosts() -> frozenset[str]:
    raw = (os.environ.get("EDGE_BUNDLER_PRIVATE_REGISTRY_HOSTS") or "").strip()
    if not raw:
        return frozenset()
    hosts: set[str] = set()
    for part in raw.split(","):
        host = part.strip().lower().rstrip(".")
        if not host:
            continue
        if host == "localhost" or host.endswith((".localhost", ".invalid")) or not PRIVATE_REGISTRY_HOST_RE.fullmatch(host):
            raise BundleBuildError(f"Invalid private package registry hostname configured: {host}")
        hosts.add(host)
    return frozenset(hosts)


def _is_public_global_ip(raw_ip: str) -> bool:
    return _is_allowed_ip(raw_ip, allow_private=False)


def _decode_proc_hex_ipv4(hex_str: str) -> ipaddress.IPv4Address:
    return ipaddress.IPv4Address(socket.ntohl(int(hex_str, 16)))


def _is_container_environment() -> bool:
    if Path("/.dockerenv").exists():
        return True
    with suppress(OSError):
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
        return "docker" in cgroup or "containerd" in cgroup
    return False


def _blocked_local_interface_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [_THIS_NET_V4, _NAT64_NET_V6]
    in_container = _is_container_environment()
    if _PROC_NET_ROUTE.is_file():
        with suppress(OSError, ValueError):
            for line in _PROC_NET_ROUTE.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
                cols = line.split()
                if len(cols) < 8:
                    continue
                iface, dest_hex, gw_hex, _flags, _ref, _use, _metric, mask_hex = cols[:8]
                # Reject container bridge/gateway routes and host docker/bridge subnets even when allow_private=True.
                if not (in_container or iface.startswith(("docker", "br-", "veth"))):
                    continue
                if gw_hex != "00000000":
                    gw_ip = _decode_proc_hex_ipv4(gw_hex)
                    if not gw_ip.is_unspecified:
                        nets.append(ipaddress.ip_network(f"{gw_ip}/32", strict=False))
                elif mask_hex != "00000000":
                    dest_ip = _decode_proc_hex_ipv4(dest_hex)
                    mask_ip = _decode_proc_hex_ipv4(mask_hex)
                    prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_ip}").prefixlen
                    if prefix > 0:
                        net = ipaddress.ip_network(f"{dest_ip}/{prefix}", strict=False)
                        if not net.is_loopback:
                            nets.append(net)
    if _PROC_NET_FIB_TRIE.is_file():
        with suppress(OSError, ValueError):
            current_ip: str | None = None
            for line in _PROC_NET_FIB_TRIE.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped.startswith("|-- "):
                    candidate = stripped[4:].strip()
                    with suppress(ValueError):
                        ipaddress.IPv4Address(candidate)
                        current_ip = candidate
                        continue
                if current_ip and "/32 host LOCAL" in stripped:
                    addr = ipaddress.IPv4Address(current_ip)
                    if not addr.is_loopback:
                        nets.append(ipaddress.ip_network(f"{addr}/32", strict=False))
                current_ip = None
    if _PROC_NET_IF_INET6.is_file():
        with suppress(OSError, ValueError):
            for line in _PROC_NET_IF_INET6.read_text(encoding="utf-8", errors="ignore").splitlines():
                cols = line.split()
                if not cols:
                    continue
                addr6 = ipaddress.IPv6Address(bytes.fromhex(cols[0]))
                if not addr6.is_loopback and not addr6.is_link_local:
                    nets.append(ipaddress.ip_network(f"{addr6}/128", strict=False))
    extra = (os.environ.get("EDGE_BUNDLER_BLOCKED_CIDRS") or "").strip()
    if extra:
        for cidr in extra.split(","):
            raw_cidr = cidr.strip()
            if raw_cidr:
                with suppress(ValueError):
                    nets.append(ipaddress.ip_network(raw_cidr, strict=False))
    return nets


def _is_allowed_ip(raw_ip: str, *, allow_private: bool = False) -> bool:
    addr = ipaddress.ip_address(raw_ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr.is_link_local or addr.is_multicast or addr.is_unspecified:
        return False
    if addr.is_loopback:
        return allow_private and os.environ.get("EDGE_BUNDLER_ALLOW_LOOPBACK_FOR_TESTS") == "1"
    for blocked in _blocked_local_interface_networks():
        if addr.version == blocked.version and addr in blocked:
            return False
    if allow_private and addr.is_private:
        return True
    return bool(addr.is_global and not addr.is_private and not addr.is_reserved)


class _RegistryConnectProxy:
    """Ephemeral localhost HTTPS CONNECT proxy restricted to explicitly approved registry endpoints."""

    def __init__(self, endpoints: frozenset[str] | dict[tuple[str, int], bool]):
        if isinstance(endpoints, frozenset):
            self._endpoints: dict[tuple[str, int], bool] = {(host.lower(), 443): False for host in endpoints}
        else:
            self._endpoints = {(host.lower(), int(port)): bool(priv) for (host, port), priv in endpoints.items()}
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
            host = host.strip("[]").lower().rstrip(".")
            if not port_str.isdigit():
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            port_num = int(port_str)
            if (host, port_num) not in self._endpoints:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            allow_private = self._endpoints[(host, port_num)]
            infos = socket.getaddrinfo(host, port_num, type=socket.SOCK_STREAM)
            ips = list(dict.fromkeys(str(info[4][0]) for info in infos))
            if not ips or not all(_is_allowed_ip(ip, allow_private=allow_private) for ip in ips):
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            ordered_ips = sorted(ips, key=lambda raw: 0 if ":" not in raw else 1)
            last_err: OSError | None = None
            for candidate_ip in ordered_ips:
                try:
                    upstream = socket.create_connection((candidate_ip, port_num), timeout=15.0)
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


def _redact_credentials(text: str, normalized_regs: list[dict[str, object]]) -> str:
    masked = text
    for reg in normalized_regs:
        tok = str(reg.get("token") or "")
        if not tok:
            continue
        masked = masked.replace(tok, "[REDACTED]")
        if reg.get("auth_type") == "basic":
            b64 = base64.b64encode(tok.encode("utf-8")).decode("ascii")
            masked = masked.replace(b64, "[REDACTED]")
    return masked


def _prepare_registry_runtime(
    root_path: Path,
    home_dir: Path,
    normalized_regs: list[dict[str, object]],
) -> tuple[dict[tuple[str, int], bool], dict[str, str], bool]:
    endpoints: dict[tuple[str, int], bool] = {
        (host, 443): False for host in allowed_registries()
    }
    env_extra: dict[str, str] = {}
    for host in allowed_private_registry_hosts():
        endpoints[(host, 443)] = True

    npmrc_lines: list[str] = []
    jsr_auth_tokens: list[str] = []
    custom_cas: list[str] = []

    for reg in normalized_regs:
        host = str(reg["host"])
        port = int(str(reg["port"]))
        allow_priv = bool(reg["allow_private_network"])
        endpoints[(host, port)] = endpoints.get((host, port), False) or allow_priv
        ca_pem = str(reg.get("ca_pem") or "")
        if ca_pem and ca_pem not in custom_cas:
            custom_cas.append(ca_pem)

        url = str(reg["registry_url"])
        path = str(reg["path"])
        host_fmt = f"[{host}]" if ":" in host else host
        netloc = f"{host_fmt}:{port}" if port != 443 else host_fmt
        auth_type = str(reg["auth_type"])
        tok = str(reg.get("token") or "")

        if reg["kind"] == "npm":
            scope = str(reg.get("scope") or "")
            npmrc_lines.append(f"{scope}:registry={url}" if scope else f"registry={url}")
            if auth_type == "bearer" and tok:
                npmrc_lines.append(f"//{netloc}{path}:_authToken={tok}")
                if path != "/":
                    npmrc_lines.append(f"//{netloc}/:_authToken={tok}")
            elif auth_type == "basic" and tok:
                b64 = base64.b64encode(tok.encode("utf-8")).decode("ascii")
                npmrc_lines.append(f"//{netloc}{path}:_auth={b64}")
                if path != "/":
                    npmrc_lines.append(f"//{netloc}/:_auth={b64}")
        else:
            trimmed_jsr = url.rstrip("/")
            if trimmed_jsr != "https://jsr.io":
                env_extra["JSR_URL"] = trimmed_jsr
            if auth_type in {"bearer", "basic"} and tok:
                jsr_auth_tokens.append(f"{tok}@{netloc}")

    if npmrc_lines:
        npmrc_path = home_dir / ".npmrc"
        npmrc_path.write_text("\n".join(npmrc_lines) + "\n", encoding="utf-8")
        with suppress(OSError):
            os.chmod(npmrc_path, 0o600)
    if jsr_auth_tokens:
        env_extra["DENO_AUTH_TOKENS"] = ";".join(jsr_auth_tokens)
    if custom_cas:
        bundle_parts: list[str] = []
        if SYSTEM_CA_BUNDLE.is_file():
            bundle_parts.append(SYSTEM_CA_BUNDLE.read_text(encoding="utf-8", errors="replace").rstrip())
        bundle_parts.extend(custom_cas)
        ca_file = root_path / "ca-bundle.crt"
        ca_file.write_text("\n".join(part for part in bundle_parts if part) + "\n", encoding="utf-8")
        with suppress(OSError):
            os.chmod(ca_file, 0o600)
        env_extra["DENO_TLS_CA_STORE"] = "system"
        env_extra["SSL_CERT_FILE"] = str(ca_file)

    isolate_cache = bool(normalized_regs)
    return endpoints, env_extra, isolate_cache


def _validate_eszip_bundle(
    data: bytes,
    src_dir: Path,
    creds_root: Path,
    normalized_regs: list[dict[str, object]],
) -> None:
    if not data.startswith(b"ESZIP") or len(data) == 0 or len(data) > MAX_ESZIP_BYTES:
        raise BundleBuildError("Generated ESZIP bundle failed format or size validation")

    resolved_src = src_dir.resolve()
    creds_bytes = str(creds_root.resolve()).encode("utf-8", errors="ignore")
    if creds_bytes and creds_bytes in data:
        raise DependencyPolicyError("Generated ESZIP references bundler credential storage")

    for match in _ESZIP_FILE_URI_RE.finditer(data):
        raw_uri = match.group(0).decode("utf-8", errors="replace")
        raw_path = raw_uri[len("file://") :]
        if raw_path.startswith("localhost/"):
            raw_path = raw_path[len("localhost") :]
        uri_path_raw = raw_path.split("?", 1)[0].split("#", 1)[0]
        decoded = uri_path_raw
        for _ in range(3):
            next_val = unquote(decoded)
            if next_val == decoded:
                break
            decoded = next_val
        if "\x00" in decoded or "\\" in decoded or ".." in PurePosixPath(decoded).parts:
            raise DependencyPolicyError("Generated ESZIP references an unsafe file:// path")
        if os.name != "nt" and decoded.startswith("/") and ":\\" not in decoded:
            candidate = Path(os.path.normpath(decoded))
            try:
                candidate.resolve().relative_to(resolved_src)
            except ValueError as err:
                raise DependencyPolicyError(
                    "Generated ESZIP references a file outside the function source directory"
                ) from err
        else:
            raise DependencyPolicyError("Generated ESZIP contains an invalid file:// URI")

    for reg in normalized_regs:
        tok = str(reg.get("token") or "")
        if len(tok) >= 6:
            tok_bytes = tok.encode("utf-8", errors="ignore")
            if tok_bytes in data:
                raise DependencyPolicyError("Generated ESZIP contains private registry credential material")
            if reg.get("auth_type") == "basic":
                b64_bytes = base64.b64encode(tok_bytes)
                if len(b64_bytes) >= 6 and b64_bytes in data:
                    raise DependencyPolicyError("Generated ESZIP contains private registry credential material")


def compile_function_eszip(files: list[dict], registries: list[dict] | None = None) -> bytes:
    """Validate dependencies and registries and compile files into an offline-ready ESZIP binary."""
    validate_dependency_policy(files)
    normalized_regs = validate_registries_payload(registries)
    bundler_bin = find_bundler_bin()
    if not bundler_bin:
        raise BundleBuildError("Edge Function dependency bundler binary is unavailable")
    timeout_raw = int(os.environ.get("EDGE_BUNDLER_TIMEOUT_SECONDS", "60") or "60")
    timeout_sec = max(5, min(120, timeout_raw))
    shared_cache_dir = Path(
        os.environ.get("EDGE_FUNCTIONS_BUNDLER_CACHE_DIR")
        or (Path(tempfile.gettempdir()) / "edge-functions-bundler-cache")
    )
    shared_cache_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(shared_cache_dir, 0o700)

    with _BUNDLE_SEM:
        # Keep untrusted function source files in an isolated TemporaryDirectory
        # separate from credentials (.npmrc, custom CA bundle), DENO_DIR, and output ESZIP.
        with (
            tempfile.TemporaryDirectory(prefix="edge-bundle-src-") as temp_src_root,
            tempfile.TemporaryDirectory(prefix="edge-bundle-creds-") as temp_creds_root,
        ):
            src_root = Path(temp_src_root)
            creds_root = Path(temp_creds_root)
            with suppress(OSError):
                os.chmod(src_root, 0o700)
                os.chmod(creds_root, 0o700)
            src_dir = src_root / "src"
            home_dir = creds_root / "home"
            src_dir.mkdir(parents=True)
            home_dir.mkdir(parents=True)
            has_wasm = _write_temp_function_tree(src_dir, files)
            endpoints, reg_env, isolate_cache = _prepare_registry_runtime(creds_root, home_dir, normalized_regs)
            deno_cache = (creds_root / "deno") if isolate_cache else shared_cache_dir
            deno_cache.mkdir(parents=True, exist_ok=True)
            out_path = creds_root / "bundle.eszip"
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
            if isolate_cache:
                command.append("--disable-module-cache")
            if has_wasm:
                command.extend(["--static", str(src_dir / "**" / "*.wasm")])
            with _RegistryConnectProxy(endpoints) as proxy_url:
                env = {
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": str(home_dir),
                    "DENO_DIR": str(deno_cache),
                    "HTTPS_PROXY": proxy_url,
                    "https_proxy": proxy_url,
                    "HTTP_PROXY": "http://127.0.0.1:0",
                    "http_proxy": "http://127.0.0.1:0",
                    "NO_PROXY": "",
                    "no_proxy": "",
                    **reg_env,
                }
                try:
                    proc = subprocess.run(
                        command,
                        cwd=str(src_dir),
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
                    raw_err = _redact_credentials(raw_err, normalized_regs)
                    lines = [ln.strip() for ln in raw_err.splitlines() if ln.strip()]
                    summary = " | ".join(lines)[:400] if lines else "Unknown bundler failure"
                    raise BundleBuildError(f"Failed to bundle Edge Function dependencies: {summary}")
                data = out_path.read_bytes()
            _validate_eszip_bundle(data, src_dir, creds_root, normalized_regs)
    return data


def _verify_hmac(raw_body: bytes, timestamp_hdr: str, signature_hdr: str, secret: str) -> bool:
    if not secret:
        return False
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
        if status >= 400:
            self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/healthz":
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
        if not secret:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "Edge Function bundler is not configured"})
            return
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
        registries = body.get("registries") if isinstance(body, dict) else None
        if not isinstance(files, list):
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "files array is required"})
            return
        if registries is not None and not isinstance(registries, list):
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "registries must be an array when provided"})
            return
        try:
            eszip = compile_function_eszip(files, registries=registries)
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
