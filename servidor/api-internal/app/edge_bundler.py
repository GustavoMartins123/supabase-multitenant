"""Validated npm/JSR dependency analysis and HTTP RPC client for offline ESZIP bundling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import PurePosixPath
import re
import time

import httpx

MAX_ESZIP_BYTES = 32 * 1024 * 1024
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


class DependencyPolicyError(ValueError):
    """Raised when a function references a disallowed import specifier."""


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


def _bundler_url() -> str:
    url = (os.environ.get("EDGE_BUNDLER_URL") or "http://edge-bundler:18030").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise BundleBuildError("Invalid EDGE_BUNDLER_URL configuration")
    return url


def _sign_bundler_request(raw_body: bytes) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    secret = (os.environ.get("EDGE_BUNDLER_HMAC_SECRET") or "").strip()
    if secret:
        ts = str(int(time.time()))
        mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("ascii") + raw_body, hashlib.sha256).hexdigest()
        headers["X-Edge-Bundler-Timestamp"] = ts
        headers["X-Edge-Bundler-Signature"] = mac
    return headers


async def bundle_function_eszip(files: list[dict]) -> bytes:
    """Delegate ESZIP bundling for validated npm/JSR imports to the isolated edge-bundler service."""
    validate_dependency_policy(files)
    timeout_raw = int(os.environ.get("EDGE_BUNDLER_TIMEOUT_SECONDS", "60") or "60")
    timeout_sec = max(5, min(120, timeout_raw))
    max_raw = int(os.environ.get("EDGE_BUNDLER_MAX_ESZIP_BYTES", str(MAX_ESZIP_BYTES)) or str(MAX_ESZIP_BYTES))
    max_bytes = max(1024, min(MAX_ESZIP_BYTES, max_raw))

    raw_body = json.dumps({"files": files}, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    headers = _sign_bundler_request(raw_body)
    target = f"{_bundler_url()}/bundle"
    try:
        async with httpx.AsyncClient(timeout=float(timeout_sec + 15), trust_env=False) as client:
            response = await client.post(target, content=raw_body, headers=headers)
    except httpx.TimeoutException as error:
        raise BundleBuildError("Edge Function dependency bundling timed out") from error
    except httpx.HTTPError as error:
        raise BundleBuildError("Edge Function dependency bundler service is unavailable") from error

    if response.status_code != 200:
        detail = ""
        kind = ""
        try:
            err_json = response.json()
            if isinstance(err_json, dict):
                detail = str(err_json.get("detail") or "")
                kind = str(err_json.get("kind") or "")
        except ValueError:
            detail = response.text[:300]
        if response.status_code == 422 and kind == "policy":
            raise DependencyPolicyError(detail or "Disallowed Edge Function dependency")
        raise BundleBuildError(detail or f"Edge Function dependency bundling failed (HTTP {response.status_code})")

    try:
        payload = response.json()
        eszip_b64 = payload["eszip_b64"]
        if not isinstance(eszip_b64, str):
            raise ValueError("Missing eszip_b64 string")
        data = base64.b64decode(eszip_b64, validate=True)
    except Exception as error:
        raise BundleBuildError("Invalid response payload from dependency bundler") from error

    if not data.startswith(b"ESZIP") or len(data) == 0 or len(data) > max_bytes:
        raise BundleBuildError("Generated ESZIP bundle failed format or size validation")
    return data
