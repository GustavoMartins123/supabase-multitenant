"""Validated npm/JSR dependency and private-registry configuration analysis for Edge Functions."""
from __future__ import annotations

import base64
import ipaddress
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

MAX_ESZIP_BYTES = 32 * 1024 * 1024
MAX_REGISTRIES_PER_PROJECT = 16
MAX_REGISTRY_TOKEN_BYTES = 4096
MAX_REGISTRY_CA_PEM_BYTES = 32768
DEFAULT_ALLOWED_REGISTRIES = frozenset({"registry.npmjs.org", "jsr.io", "npm.jsr.io"})
SOURCE_EXTENSIONS = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"})
NPM_SPEC_RE = re.compile(
    r"^npm:(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*(?:@[^\s?#\"'\\]+)?(?:/[^\s?#\"'\\]*)?$"
)
JSR_SPEC_RE = re.compile(
    r"^jsr:@[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*(?:@[^\s?#\"'\\]+)?(?:/[^\s?#\"'\\]*)?$"
)
NODE_SPEC_RE = re.compile(r"^node:[a-z0-9_./-]+$")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
STATIC_IMPORT_RE = re.compile(
    r"""(?:^|[;\n}])\s*(?:import|export)\s+(?:type\s+)?(?:[^;'"`]*?\bfrom\s+)?(['"])([^'"\n]+)\1""",
    re.MULTILINE,
)
DYNAMIC_IMPORT_RE = re.compile(r"""\bimport\s*\(\s*(['"])([^'"\n]+)\1""")

REGISTRY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
NPM_SCOPE_RE = re.compile(r"^@[a-z0-9][a-z0-9._-]{0,127}$")
PUBLIC_HOSTNAME_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
PRIVATE_HOSTNAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")
PEM_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----\s+([A-Za-z0-9+/=\s]+?)\s+-----END CERTIFICATE-----")


class DependencyPolicyError(ValueError):
    """Raised when a function or registry configuration violates security policy."""


class BundleBuildError(RuntimeError):
    """Raised when offline-safe ESZIP compilation fails."""


def _strip_js_comments(source: str) -> str:
    """Strip JS/TS comments while preserving quoted and template string literals."""
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch in {"'", '"', "`"}:
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                cur = source[i]
                out.append(cur)
                if cur == "\\" and i + 1 < n:
                    out.append(source[i + 1])
                    i += 2
                    continue
                if cur == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                if source[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _validate_relative_import(spec: str, source_name: str) -> None:
    if "?" in spec or "#" in spec or "\0" in spec:
        raise DependencyPolicyError(f"Unsupported query or fragment in local import '{spec}' ({source_name})")
    base_dir = PurePosixPath(source_name).parent
    combined = (base_dir / PurePosixPath(spec)).parts
    depth = 0
    for part in combined:
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                raise DependencyPolicyError(f"Local import '{spec}' in {source_name} escapes function directory")
        else:
            depth += 1


def _validate_specifier(spec: str, source_name: str) -> str | None:
    """Validate an import specifier and return 'npm', 'jsr', or None."""
    if not isinstance(spec, str) or not spec or any(c.isspace() or ord(c) < 32 for c in spec):
        raise DependencyPolicyError(f"Invalid import specifier in {source_name}")
    if spec.startswith("/"):
        raise DependencyPolicyError(f"Absolute path import '{spec}' is not allowed in {source_name}")
    if spec.startswith(("./", "../")):
        _validate_relative_import(spec, source_name)
        return None
    if SCHEME_RE.match(spec):
        lower = spec.lower()
        if lower.startswith("npm:"):
            if not NPM_SPEC_RE.fullmatch(spec) or "/.." in spec or "../" in spec:
                raise DependencyPolicyError(f"Invalid npm specifier '{spec}' in {source_name}")
            return "npm"
        if lower.startswith("jsr:"):
            if not JSR_SPEC_RE.fullmatch(spec) or "/.." in spec or "../" in spec:
                raise DependencyPolicyError(f"Invalid jsr specifier '{spec}' in {source_name}")
            return "jsr"
        if lower.startswith("node:"):
            if not NODE_SPEC_RE.fullmatch(spec):
                raise DependencyPolicyError(f"Invalid node specifier '{spec}' in {source_name}")
            return None
        raise DependencyPolicyError(
            f"Disallowed import scheme '{spec}' in {source_name}; use local files, 'npm:', 'jsr:', or 'node:'"
        )
    return None


def _extract_source_specifiers(source: str) -> list[str]:
    stripped = _strip_js_comments(source)
    specs: list[str] = []
    for match in STATIC_IMPORT_RE.finditer(stripped):
        specs.append(match.group(2))
    for match in DYNAMIC_IMPORT_RE.finditer(stripped):
        specs.append(match.group(2))
    return specs


def inspect_dependencies(files: list[dict]) -> dict[str, object]:
    """Validate deno.json and JS/TS imports and return summarized npm/JSR dependency metadata."""
    npm_specs: set[str] = set()
    jsr_specs: set[str] = set()
    for item in files:
        name = str(item.get("name", ""))
        if item.get("encoding") == "base64":
            continue
        content = str(item.get("content", ""))
        if name == "deno.json":
            try:
                cfg = json.loads(content)
            except json.JSONDecodeError as error:
                raise DependencyPolicyError("Invalid JSON in deno.json") from error
            if not isinstance(cfg, dict) or set(cfg) - {"imports", "scopes"}:
                raise DependencyPolicyError("deno.json supports imports and scopes only")
            imports = cfg.get("imports")
            if imports is not None:
                if not isinstance(imports, dict):
                    raise DependencyPolicyError("deno.json imports must be an object")
                for key, target in imports.items():
                    if not isinstance(key, str) or not key.strip() or not isinstance(target, str):
                        raise DependencyPolicyError("deno.json import entries must map non-empty strings")
                    kind = _validate_specifier(target, "deno.json")
                    if kind == "npm":
                        npm_specs.add(target)
                    elif kind == "jsr":
                        jsr_specs.add(target)
            scopes = cfg.get("scopes")
            if scopes is not None:
                if not isinstance(scopes, dict):
                    raise DependencyPolicyError("deno.json scopes must be an object")
                for scope_key, mapping in scopes.items():
                    if not isinstance(scope_key, str) or not isinstance(mapping, dict):
                        raise DependencyPolicyError("deno.json scopes entries must be objects")
                    for target in mapping.values():
                        if not isinstance(target, str):
                            raise DependencyPolicyError("deno.json scope values must be strings")
                        kind = _validate_specifier(target, "deno.json")
                        if kind == "npm":
                            npm_specs.add(target)
                        elif kind == "jsr":
                            jsr_specs.add(target)
            continue
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in SOURCE_EXTENSIONS:
            for spec in _extract_source_specifiers(content):
                kind = _validate_specifier(spec, name)
                if kind == "npm":
                    npm_specs.add(spec)
                elif kind == "jsr":
                    jsr_specs.add(spec)
    return {
        "npm": sorted(npm_specs),
        "jsr": sorted(jsr_specs),
        "requires_bundle": bool(npm_specs or jsr_specs),
    }


def validate_dependency_policy(files: list[dict]) -> dict[str, object]:
    return inspect_dependencies(files)


def requires_eszip_bundle(files: list[dict]) -> bool:
    return bool(inspect_dependencies(files)["requires_bundle"])


def normalize_ca_pem(raw_pem: str | None) -> str:
    """Validate optional PEM CA certificate chain and return canonical line-separated PEM blocks."""
    if raw_pem is None:
        return ""
    if not isinstance(raw_pem, str) or "\0" in raw_pem:
        raise DependencyPolicyError("Invalid CA certificate PEM payload")
    cleaned = raw_pem.replace("\r\n", "\n").strip()
    if not cleaned:
        return ""
    if len(cleaned.encode("utf-8")) > MAX_REGISTRY_CA_PEM_BYTES:
        raise DependencyPolicyError(f"Custom CA PEM exceeds {MAX_REGISTRY_CA_PEM_BYTES} bytes")
    blocks: list[str] = []
    pos = 0
    for match in PEM_CERT_RE.finditer(cleaned):
        between = cleaned[pos:match.start()].strip()
        if between:
            raise DependencyPolicyError("Custom CA PEM must contain only CERTIFICATE blocks")
        pos = match.end()
        body = "".join(match.group(1).split())
        try:
            der = base64.b64decode(body, validate=True)
        except Exception as err:
            raise DependencyPolicyError("Custom CA PEM contains invalid base64 data") from err
        if len(der) < 32 or der[0] != 0x30:
            raise DependencyPolicyError("Custom CA PEM contains an invalid X.509 DER structure")
        wrapped = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
        blocks.append(f"-----BEGIN CERTIFICATE-----\n{wrapped}\n-----END CERTIFICATE-----")
    if not blocks or cleaned[pos:].strip():
        raise DependencyPolicyError("Custom CA PEM must contain valid -----BEGIN CERTIFICATE----- block(s)")
    return "\n".join(blocks)


def validate_registry_url(raw_url: str, *, allow_private_network: bool = False) -> tuple[str, str, int, str]:
    """Validate an HTTPS package registry URL and return (canonical_url, host, port, path)."""
    if not isinstance(raw_url, str) or any(c.isspace() or ord(c) < 32 for c in raw_url):
        raise DependencyPolicyError("Registry URL contains invalid control or whitespace characters")
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise DependencyPolicyError("Registry URL must use https:// with a valid hostname")
    if parsed.username or parsed.password:
        raise DependencyPolicyError("Registry URL must not embed credentials; provide auth token separately")
    if parsed.query or parsed.fragment:
        raise DependencyPolicyError("Registry URL must not contain query parameters or fragments")
    host = parsed.hostname.strip().lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".invalid")):
        raise DependencyPolicyError(f"Disallowed registry hostname '{host}'")
    try:
        port = parsed.port or 443
    except ValueError as err:
        raise DependencyPolicyError("Invalid port in registry URL") from err
    is_ip_literal = False
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False

    if allow_private_network:
        if port != 443 and not (1024 <= port <= 65535):
            raise DependencyPolicyError("Custom registry port must be 443 or in 1024..65535")
        if not is_ip_literal and not PRIVATE_HOSTNAME_RE.fullmatch(host):
            raise DependencyPolicyError(f"Invalid registry hostname '{host}'")
    else:
        if port != 443:
            raise DependencyPolicyError("Public registries must use standard HTTPS port 443")
        if is_ip_literal or host.endswith((".local", ".internal", ".test")) or not PUBLIC_HOSTNAME_RE.fullmatch(host):
            raise DependencyPolicyError(
                f"Registry host '{host}' must be a public domain (or enable allow_private_network as platform admin)"
            )
    raw_path = parsed.path or "/"
    if not raw_path.startswith("/") or "//" in raw_path or "/../" in raw_path or raw_path.endswith("/.."):
        raise DependencyPolicyError("Registry URL contains an invalid path")
    clean_path = raw_path if raw_path.endswith("/") else f"{raw_path}/"
    if len(clean_path) > 256:
        raise DependencyPolicyError("Registry URL path exceeds 256 characters")
    host_fmt = f"[{host}]" if ":" in host else host
    netloc = f"{host_fmt}:{port}" if port != 443 else host_fmt
    canonical = f"https://{netloc}{clean_path}"
    if len(canonical) > 512:
        raise DependencyPolicyError("Registry URL exceeds 512 characters")
    return canonical, host, port, clean_path


def validate_registry_token(auth_type: str, token: str | None) -> str:
    if auth_type not in {"none", "bearer", "basic"}:
        raise DependencyPolicyError("auth_type must be 'none', 'bearer', or 'basic'")
    if auth_type == "none":
        if token:
            raise DependencyPolicyError("Registry token must be omitted when auth_type is 'none'")
        return ""
    if not isinstance(token, str) or not token:
        raise DependencyPolicyError(f"Registry token is required for auth_type '{auth_type}'")
    if any(ord(c) < 32 or ord(c) == 127 for c in token) or token != token.strip():
        raise DependencyPolicyError("Registry credential cannot contain control characters or leading/trailing whitespace")
    encoded = token.encode("utf-8")
    if len(encoded) > MAX_REGISTRY_TOKEN_BYTES:
        raise DependencyPolicyError(f"Registry credential exceeds {MAX_REGISTRY_TOKEN_BYTES} bytes")
    if auth_type == "bearer" and any(c.isspace() for c in token):
        raise DependencyPolicyError("Bearer token cannot contain spaces")
    if auth_type == "basic" and ":" not in token:
        raise DependencyPolicyError("Basic auth credential must use 'username:password' format")
    return token


def validate_registry_spec(raw: dict, *, require_token_if_auth: bool = True) -> dict[str, object]:
    """Validate and normalize a single registry specification dict."""
    if not isinstance(raw, dict):
        raise DependencyPolicyError("Registry entry must be an object")
    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in {"npm", "jsr"}:
        raise DependencyPolicyError("Registry kind must be 'npm' or 'jsr'")
    scope = str(raw.get("scope") or "").strip().lower()
    if kind == "jsr":
        if scope:
            raise DependencyPolicyError("JSR registries do not accept a per-scope override; leave scope empty")
    elif scope and not NPM_SCOPE_RE.fullmatch(scope):
        raise DependencyPolicyError("npm scope must look like '@org' (lowercase alphanumeric, '.', '_', '-')")
    allow_private = bool(raw.get("allow_private_network", False))
    canonical_url, host, port, clean_path = validate_registry_url(
        str(raw.get("registry_url", "")), allow_private_network=allow_private
    )
    auth_type = str(raw.get("auth_type") or "bearer").strip().lower()
    token_raw = raw.get("token")
    if auth_type == "none":
        token = ""
    elif token_raw is None and not require_token_if_auth:
        token = ""
    else:
        token = validate_registry_token(auth_type, token_raw if isinstance(token_raw, str) else None)
    ca_pem = normalize_ca_pem(raw.get("ca_pem"))
    return {
        "kind": kind,
        "scope": scope,
        "registry_url": canonical_url,
        "host": host,
        "port": port,
        "path": clean_path,
        "auth_type": auth_type,
        "token": token,
        "allow_private_network": allow_private,
        "ca_pem": ca_pem,
    }


def validate_registries_payload(registries: list[dict] | None) -> list[dict[str, object]]:
    """Validate all enabled registries sent to the bundler and enforce slot uniqueness."""
    if not registries:
        return []
    if not isinstance(registries, list) or len(registries) > MAX_REGISTRIES_PER_PROJECT:
        raise DependencyPolicyError(f"Expected at most {MAX_REGISTRIES_PER_PROJECT} active registries")
    seen_slots: set[tuple[str, str]] = set()
    normalized: list[dict[str, object]] = []
    for item in registries:
        clean = validate_registry_spec(item, require_token_if_auth=False)
        if clean["auth_type"] != "none" and not clean["token"]:
            raise DependencyPolicyError(f"Missing credential for authenticated registry '{clean['registry_url']}'")
        slot = (str(clean["kind"]), str(clean["scope"]))
        if slot in seen_slots:
            raise DependencyPolicyError(f"Duplicate active registry slot for {slot[0]} {slot[1] or '(default)'}")
        seen_slots.add(slot)
        normalized.append(clean)
    return normalized
