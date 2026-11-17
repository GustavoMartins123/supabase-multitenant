"""Private Studio drafts and content-addressed, project-bound function versions.

Only published pointers are consumed by the runtime publisher. Callers hold
edge_functions.configuration_lock for the entire read/modify/publish operation.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from app import edge_functions

SLUG = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
REVISION = re.compile(r"[0-9a-f]{64}\Z")
SEGMENT = re.compile(r"[A-Za-z0-9_@][A-Za-z0-9_@.\-]{0,99}\Z")
MAX_FILES = 64
MAX_BYTES = 1_000_000
MAX_FUNCTIONS = 128
MAX_FILES_CEILING = edge_functions.QUOTA_SPECS["max_files"]["max"]
MAX_BYTES_CEILING = edge_functions.QUOTA_SPECS["max_bytes"]["max"]
MAX_FUNCTIONS_CEILING = edge_functions.QUOTA_SPECS["max_functions"]["max"]
RESERVED_SLUGS = edge_functions.RESERVED_SLUGS


def function_name(value: str) -> str:
    if not SLUG.fullmatch(value) or value in RESERVED_SLUGS:
        raise ValueError("Invalid function name")
    return value


def validate_files(files: list[dict], *, max_files: int = MAX_FILES, max_bytes: int = MAX_BYTES) -> list[dict[str, str]]:
    if not isinstance(files, list) or not 1 <= len(files) <= max_files:
        raise ValueError(f"A function requires 1 to {max_files} files")
    result, names, size = [], set(), 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"name", "content"}:
            raise ValueError("Invalid function file")
        name, content = item["name"], item["content"]
        if (not isinstance(name, str) or len(name) > 240 or len(name.split("/")) > 8
                or any(not SEGMENT.fullmatch(part) for part in name.split("/"))
                or not isinstance(content, str) or "\0" in content or name in names):
            raise ValueError("File paths must be unique, relative and contain no traversal or hidden segments")
        names.add(name)
        size += len(content.encode("utf-8")) + len(name)
        result.append({"name": name, "content": content})
    if "index.ts" not in names:
        raise ValueError("The function entrypoint must be index.ts")
    if size > max_bytes:
        raise ValueError(f"Function files exceed the {max_bytes} byte limit")
    if any(any(name.startswith(other + "/") for other in names) for name in names):
        raise ValueError("A file cannot also be a directory")
    for item in result:
        if item["name"] == "deno.json":
            config = json.loads(item["content"])
            if not isinstance(config, dict) or set(config) - {"imports", "scopes"}:
                raise ValueError("deno.json supports imports and scopes only")
    return sorted(result, key=lambda item: item["name"])


def directory(root: Path, name: str, identity: str) -> Path:
    edge_functions.project_name(name)
    return edge_functions.private_directory(root / ".functions-studio" / edge_functions.project_uuid(identity))


def regular_bytes(path: Path, limit: int) -> bytes:
    if any(parent.is_symlink() for parent in path.parents):
        raise RuntimeError("Refusing symlinked function storage")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise RuntimeError("Invalid function storage file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("Function storage exceeds limit")
    return data


def encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def atomic_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise RuntimeError("Refusing symlinked function storage")
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_state(state: dict, name: str, identity: str) -> dict:
    if (not isinstance(state, dict) or set(state) != {"project", "uuid", "functions"}
            or state["project"] != name or state["uuid"] != identity
            or not isinstance(state["functions"], dict) or len(state["functions"]) > MAX_FUNCTIONS_CEILING * 2):
        raise RuntimeError("Function storage project identity mismatch")
    for slug, item in state["functions"].items():
        function_name(slug)
        if (not isinstance(item, dict) or set(item) != {"draft", "published"}
                or (item["draft"] is None and item["published"] is not None)
                or (item["draft"] is not None and
                    (not isinstance(item["draft"], str) or not REVISION.fullmatch(item["draft"])))
                or (item["published"] is not None and
                    (not isinstance(item["published"], str) or not REVISION.fullmatch(item["published"])))):
            raise RuntimeError("Invalid function revision pointers")
    if sum(item["draft"] is not None for item in state["functions"].values()) > MAX_FUNCTIONS_CEILING:
        raise RuntimeError("Too many saved functions")
    return state


def read_state(root: Path, name: str, identity: str) -> dict:
    path = directory(root, name, identity) / "state.json"
    try:
        state = json.loads(regular_bytes(path, 128_000))
    except FileNotFoundError:
        return {"project": name, "uuid": identity, "functions": {}}
    return validate_state(state, name, identity)


def load(root: Path, name: str, identity: str) -> dict:
    recover_publication(root, name, identity)
    return read_state(root, name, identity)


def finish_publication(root: Path, name: str, identity: str) -> None:
    path = directory(root, name, identity) / "publication.json"
    path.unlink(missing_ok=True)
    edge_functions.sync_directory(path.parent)


def begin_publication(root: Path, previous: dict, proposed: dict, context: dict, *, action: str = "publish") -> None:
    # A durable intent bridges the two atomic files. A process killed after
    # runtime activation can be recovered without publishing any later draft.
    atomic_json(directory(root, previous["project"], previous["uuid"]) / "publication.json", {
        "previous": previous, "proposed": proposed, "runtime_revision": context["revision"], "action": action,
    })


def validate_transition(root: Path, previous: dict, proposed: dict, action: str) -> None:
    before, after = previous["functions"], proposed["functions"]
    changes = [slug for slug in set(before) | set(after) if before.get(slug) != after.get(slug)]
    if len(changes) != 1:
        raise RuntimeError("Function operation must change exactly one function")
    slug = changes[0]
    old, new = before.get(slug), after.get(slug)
    if action == "publish":
        valid = old and new and old["draft"] is not None and old["draft"] == new["draft"] and new["published"] == new["draft"]
    else:
        legacy = legacy_functions(root, previous["project"])
        if action == "unpublish":
            valid = new and new["draft"] is not None and new["published"] is None and (
                old and old["draft"] == new["draft"] or not old and slug in legacy and
                version(previous["project"], previous["uuid"], slug, legacy[slug])[0] == new["draft"])
        elif action == "delete":
            valid = (old or slug in legacy) and (
                new == {"draft": None, "published": None} if slug in legacy else new is None)
        else:
            valid = False
    if not valid:
        raise RuntimeError("Invalid function publication transition")


def recover_publication(root: Path, name: str, identity: str) -> None:
    path = directory(root, name, identity) / "publication.json"
    try:
        data = regular_bytes(path, 300_000)
    except FileNotFoundError:
        return
    except (OSError, RuntimeError):
        edge_functions.withdraw(root, name)
        raise
    try:
        intent = json.loads(data)
        if (not isinstance(intent, dict) or set(intent) not in ({"previous", "proposed", "runtime_revision"},
                {"previous", "proposed", "runtime_revision", "action"})
                or not isinstance(intent["runtime_revision"], str) or not REVISION.fullmatch(intent["runtime_revision"])):
            raise RuntimeError("Invalid function publication intent")
        previous = validate_state(intent["previous"], name, identity)
        proposed = validate_state(intent["proposed"], name, identity)
        validate_transition(root, previous, proposed, intent.get("action", "publish"))
        current = read_state(root, name, identity)
        if current != previous and current != proposed:
            raise RuntimeError("Function state changed during interrupted publication")
        context = edge_functions.read_context(root, name, identity)
        if context and context["revision"] == intent["runtime_revision"]:
            files = published_files(root, name, identity, state=proposed)
            expected = edge_functions.context_value(
                name, identity, context["jwt_secret"], context["env"], files, context.get("network_allowlist"),
                secrets=context.get("secrets"), public_functions=context.get("public_functions"),
                limits=context.get("limits"))
            if expected != context:
                raise RuntimeError("Publication context does not match saved versions")
            edge_functions.verify_generation(root, context, files)
            recovered = proposed
        else:
            # Activation never completed (or an ordinary failure rolled back).
            recovered = previous
        if current != recovered:
            atomic_json(directory(root, name, identity) / "state.json", recovered)
        finish_publication(root, name, identity)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, UnicodeError):
        edge_functions.withdraw(root, name)
        raise


def version(name: str, identity: str, slug: str, files: list[dict],
            *, max_files: int = MAX_FILES_CEILING, max_bytes: int = MAX_BYTES_CEILING) -> tuple[str, dict]:
    value = {
        "project": name,
        "uuid": identity,
        "function": function_name(slug),
        "files": validate_files(files, max_files=max_files, max_bytes=max_bytes),
    }
    return hashlib.sha256(encoded(value)).hexdigest(), value


def store_version(root: Path, name: str, identity: str, slug: str, files: list[dict],
                  *, max_files: int = MAX_FILES_CEILING, max_bytes: int = MAX_BYTES_CEILING) -> str:
    revision, value = version(name, identity, slug, files, max_files=max_files, max_bytes=max_bytes)
    versions = edge_functions.private_directory(directory(root, name, identity) / "versions" / slug)
    path = versions / (revision + ".json")
    try:
        existing = regular_bytes(path, MAX_BYTES_CEILING * 6 + 65536)
    except FileNotFoundError:
        atomic_json(path, value)
        path.chmod(0o400)
    else:
        if existing != encoded(value):
            raise RuntimeError("Immutable function version was altered")
    return revision


def read_version(root: Path, state: dict, slug: str, revision: str) -> list[dict]:
    function_name(slug)
    if not REVISION.fullmatch(revision):
        raise RuntimeError("Invalid function revision")
    path = directory(root, state["project"], state["uuid"]) / "versions" / slug / (revision + ".json")
    value = json.loads(regular_bytes(path, MAX_BYTES_CEILING * 6 + 65536))
    expected, canonical = version(state["project"], state["uuid"], slug, value["files"])
    if expected != revision or value != canonical:
        raise RuntimeError("Immutable function version integrity check failed")
    return canonical["files"]


def legacy_functions(root: Path, name: str) -> dict[str, list[dict]]:
    # Shared supervisor directories are never tenant publication sources.
    edge_functions.project_name(name)
    return {}


def item(root: Path, state: dict, slug: str, legacy: dict) -> dict | None:
    pointers = state["functions"].get(slug)
    if pointers:
        if pointers["draft"] is None:
            return None
        files = read_version(root, state, slug, pointers["draft"])
        return {"name": slug, "revision": pointers["draft"], "published_revision": pointers["published"], "files": files}
    if slug in legacy:
        revision, _ = version(state["project"], state["uuid"], slug, legacy[slug])
        return {"name": slug, "revision": revision, "published_revision": revision, "files": legacy[slug]}
    return None


def function_names(state: dict, legacy: dict) -> list[str]:
    return sorted(slug for slug in set(legacy) | set(state["functions"])
                  if state["functions"].get(slug, {}).get("draft", "legacy") is not None)


def published_files(root: Path, name: str, identity: str, *, state: dict | None = None) -> dict[str, bytes]:
    state = load(root, name, identity) if state is None else state
    functions = legacy_functions(root, name)
    for slug, pointers in state["functions"].items():
        if pointers["published"]:
            functions[slug] = read_version(root, state, slug, pointers["published"])
        else:
            # Explicit draft/unpublish/delete state masks files from the old layout.
            functions.pop(slug, None)
    if len(functions) > MAX_FUNCTIONS_CEILING:
        raise RuntimeError("Too many published functions")
    return {slug + "/" + file["name"]: file["content"].encode()
            for slug, files in functions.items() for file in files}


DEFAULT_ORPHAN_RETENTION_SECONDS = 3600


def list_versions(root: Path, state: dict, slug: str) -> list[dict]:
    function_name(slug)
    versions_dir = directory(root, state["project"], state["uuid"]) / "versions" / slug
    if any(parent.is_symlink() for parent in (versions_dir, *versions_dir.parents)):
        raise RuntimeError("Refusing symlinked version history directory")
    if versions_dir.is_symlink():
        raise RuntimeError("Refusing symlinked version history directory")
    if not versions_dir.exists():
        return []
    pointers = state["functions"].get(slug)
    entries: list[dict] = []
    for entry in sorted(versions_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Invalid entry in function versions directory")
        revision = entry.stem
        if entry.suffix != ".json" or not REVISION.fullmatch(revision):
            continue
        files = read_version(root, state, slug, revision)
        entries.append({
            "revision": revision,
            "created_at": datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).isoformat(),
            "file_count": len(files),
            "total_bytes": sum(len(f["content"].encode("utf-8")) for f in files),
            "is_draft": bool(pointers and pointers.get("draft") == revision),
            "is_published": bool(pointers and pointers.get("published") == revision),
        })
    entries.sort(key=lambda item: (item["created_at"], item["is_published"], item["is_draft"], item["revision"]), reverse=True)
    return entries


def purge_orphan_versions(
    root: Path, state: dict, *,
    min_age_seconds: int = DEFAULT_ORPHAN_RETENTION_SECONDS,
    now: float | None = None,
) -> dict[str, int]:
    if min_age_seconds < 0:
        raise ValueError("min_age_seconds must be non-negative")
    versions_root = directory(root, state["project"], state["uuid"]) / "versions"
    if any(parent.is_symlink() for parent in (versions_root, *versions_root.parents)):
        raise RuntimeError("Refusing symlinked versions root")
    if versions_root.is_symlink():
        raise RuntimeError("Refusing symlinked versions root")
    if not versions_root.exists():
        return {"removed_count": 0, "reclaimed_bytes": 0, "kept_count": 0}
    current_time = time.time() if now is None else float(now)
    removed_count = 0
    reclaimed_bytes = 0
    kept_count = 0
    for fn_dir in sorted(versions_root.iterdir()):
        if fn_dir.name.startswith("."):
            continue
        fn_info = fn_dir.lstat()
        if stat.S_ISLNK(fn_info.st_mode) or not stat.S_ISDIR(fn_info.st_mode):
            raise RuntimeError("Invalid entry inside versions root")
        slug = function_name(fn_dir.name)
        pointers = state["functions"].get(slug) or {}
        referenced = {rev for rev in (pointers.get("draft"), pointers.get("published")) if rev}
        for entry in sorted(fn_dir.iterdir()):
            if entry.name.startswith("."):
                continue
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise RuntimeError("Invalid file inside function version directory")
            if entry.suffix != ".json" or not REVISION.fullmatch(entry.stem):
                continue
            age = max(0.0, current_time - info.st_mtime)
            if entry.stem in referenced or age < min_age_seconds:
                kept_count += 1
                continue
            entry.chmod(0o600)
            entry.unlink()
            removed_count += 1
            reclaimed_bytes += info.st_size
        remaining = [p for p in fn_dir.iterdir() if not p.name.startswith(".")]
        if not remaining and slug not in state["functions"]:
            fn_dir.rmdir()
    edge_functions.sync_directory(versions_root)
    return {"removed_count": removed_count, "reclaimed_bytes": reclaimed_bytes, "kept_count": kept_count}


EDGE_FUNCTION_TEMPLATES: tuple[dict, ...] = (
    {
        "id": "hello-world",
        "name": "Hello World JSON",
        "category": "starter",
        "description": "Basic authenticated HTTP handler returning structured JSON.",
        "recommended_verify_jwt": True,
        "recommended_secrets": [],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "Deno.serve(async (req: Request) => {\n"
                    "  const { name = 'world' } = await req.json().catch(() => ({}));\n"
                    "  return Response.json({\n"
                    "    message: `Hello, ${name}!`,\n"
                    "    method: req.method,\n"
                    "    timestamp: new Date().toISOString(),\n"
                    "  });\n"
                    "});\n"
                ),
            },
        ],
    },
    {
        "id": "webhook-hmac",
        "name": "Signed Public Webhook",
        "category": "webhooks",
        "description": "Public webhook endpoint (verify_jwt=false) with constant-time HMAC-SHA256 verification using a project secret.",
        "recommended_verify_jwt": False,
        "recommended_secrets": ["WEBHOOK_SECRET"],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "const encoder = new TextEncoder();\n\n"
                    "function timingSafeEqual(a: string, b: string): boolean {\n"
                    "  if (a.length !== b.length || a.length === 0) return false;\n"
                    "  let diff = 0;\n"
                    "  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);\n"
                    "  return diff === 0;\n"
                    "}\n\n"
                    "Deno.serve(async (req: Request) => {\n"
                    "  const secret = Deno.env.get('WEBHOOK_SECRET') ?? '';\n"
                    "  if (!secret) {\n"
                    "    return Response.json({ error: 'WEBHOOK_SECRET not configured' }, { status: 500 });\n"
                    "  }\n"
                    "  const rawBody = await req.text();\n"
                    "  const sig = (req.headers.get('x-webhook-signature') ?? '').toLowerCase();\n"
                    "  const key = await crypto.subtle.importKey(\n"
                    "    'raw',\n"
                    "    encoder.encode(secret),\n"
                    "    { name: 'HMAC', hash: 'SHA-256' },\n"
                    "    false,\n"
                    "    ['sign'],\n"
                    "  );\n"
                    "  const digest = await crypto.subtle.sign('HMAC', key, encoder.encode(rawBody));\n"
                    "  const expected = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');\n"
                    "  if (!timingSafeEqual(sig, expected)) {\n"
                    "    return Response.json({ error: 'Invalid signature' }, { status: 401 });\n"
                    "  }\n"
                    "  const payload = JSON.parse(rawBody || '{}');\n"
                    "  console.log('Webhook accepted', typeof payload);\n"
                    "  return Response.json({ accepted: true });\n"
                    "});\n"
                ),
            },
        ],
    },
    {
        "id": "project-rest",
        "name": "Project REST & Auth Query",
        "category": "database",
        "description": "Queries the project's own PostgREST API using runtime environment keys and incoming caller JWT.",
        "recommended_verify_jwt": True,
        "recommended_secrets": [],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "Deno.serve(async (req: Request) => {\n"
                    "  const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? '';\n"
                    "  const anonKey = Deno.env.get('SUPABASE_ANON_KEY') ?? '';\n"
                    "  const authHeader = req.headers.get('authorization') ?? '';\n"
                    "  const response = await fetch(`${supabaseUrl}/rest/v1/`, {\n"
                    "    headers: {\n"
                    "      apikey: anonKey,\n"
                    "      ...(authHeader ? { Authorization: authHeader } : {}),\n"
                    "    },\n"
                    "  });\n"
                    "  return Response.json({\n"
                    "    upstreamStatus: response.status,\n"
                    "    ok: response.ok,\n"
                    "  });\n"
                    "});\n"
                ),
            },
        ],
    },
    {
        "id": "streaming-sse",
        "name": "Streaming SSE + Background Task",
        "category": "streaming",
        "description": "Server-Sent Events response with CORS headers and EdgeRuntime.waitUntil background flush.",
        "recommended_verify_jwt": True,
        "recommended_secrets": [],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "const corsHeaders = {\n"
                    "  'Access-Control-Allow-Origin': '*',\n"
                    "  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',\n"
                    "};\n\n"
                    "Deno.serve((req: Request) => {\n"
                    "  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });\n"
                    "  const encoder = new TextEncoder();\n"
                    "  const stream = new ReadableStream({\n"
                    "    async start(controller) {\n"
                    "      for (let i = 1; i <= 3; i++) {\n"
                    "        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ step: i })}\\n\\n`));\n"
                    "        await new Promise((r) => setTimeout(r, 100));\n"
                    "      }\n"
                    "      controller.close();\n"
                    "    },\n"
                    "  });\n"
                    "  EdgeRuntime.waitUntil(Promise.resolve().then(() => console.log('SSE stream initialized')));\n"
                    "  return new Response(stream, {\n"
                    "    headers: {\n"
                    "      ...corsHeaders,\n"
                    "      'Content-Type': 'text/event-stream',\n"
                    "      'Cache-Control': 'no-cache',\n"
                    "    },\n"
                    "  });\n"
                    "});\n"
                ),
            },
        ],
    },
    {
        "id": "websocket-echo",
        "name": "WebSocket Upgrade Handler",
        "category": "realtime",
        "description": "Handles bidirectional WebSocket connections over /functions/v1/<slug>.",
        "recommended_verify_jwt": True,
        "recommended_secrets": [],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "Deno.serve((req: Request) => {\n"
                    "  if (req.headers.get('upgrade')?.toLowerCase() !== 'websocket') {\n"
                    "    return Response.json({ message: 'Upgrade: websocket required' }, { status: 426 });\n"
                    "  }\n"
                    "  const { socket, response } = Deno.upgradeWebSocket(req);\n"
                    "  socket.onopen = () => socket.send(JSON.stringify({ type: 'connected' }));\n"
                    "  socket.onmessage = (event) => {\n"
                    "    socket.send(JSON.stringify({ type: 'echo', data: event.data }));\n"
                    "  };\n"
                    "  return response;\n"
                    "});\n"
                ),
            },
        ],
    },
    {
        "id": "scheduled-cron",
        "name": "Scheduled Maintenance Task",
        "category": "schedules",
        "description": "Idempotent job handler triggered by Edge Function Cron Schedules or manual POST.",
        "recommended_verify_jwt": True,
        "recommended_secrets": [],
        "files": [
            {
                "name": "index.ts",
                "content": (
                    "Deno.serve(async (req: Request) => {\n"
                    "  const scheduleId = req.headers.get('x-edge-schedule-id') ?? 'manual';\n"
                    "  const payload = await req.json().catch(() => ({}));\n"
                    "  console.log('Scheduled job started', scheduleId);\n"
                    "  return Response.json({\n"
                    "    ok: true,\n"
                    "    scheduleId,\n"
                    "    executedAt: new Date().toISOString(),\n"
                    "    payload,\n"
                    "  });\n"
                    "});\n"
                ),
            },
        ],
    },
)


def list_templates() -> list[dict]:
    """Return a copy of curated Edge Function starter templates."""
    return copy.deepcopy(list(EDGE_FUNCTION_TEMPLATES))


def compute_version_diff(
    slug: str,
    from_revision: str,
    from_files: list[dict],
    to_revision: str,
    to_files: list[dict],
    *,
    max_diff_lines: int = 2000,
) -> dict:
    """Compute a per-file unified diff between two immutable revisions."""
    from_map = {item["name"]: item for item in from_files}
    to_map = {item["name"]: item for item in to_files}
    summary = {
        "files_added": 0,
        "files_removed": 0,
        "files_modified": 0,
        "files_unchanged": 0,
        "lines_added": 0,
        "lines_removed": 0,
        "truncated": False,
    }
    file_diffs: list[dict] = []
    emitted_lines = 0
    for name in sorted(set(from_map) | set(to_map)):
        left = from_map.get(name)
        right = to_map.get(name)
        is_binary = (left is not None and left.get("encoding") == "base64") or (
            right is not None and right.get("encoding") == "base64"
        )
        if left is None and right is not None:
            status = "added"
            summary["files_added"] += 1
        elif right is None and left is not None:
            status = "removed"
            summary["files_removed"] += 1
        elif left == right:
            status = "unchanged"
            summary["files_unchanged"] += 1
        else:
            status = "modified"
            summary["files_modified"] += 1

        hunks: list[str] = []
        file_added = 0
        file_removed = 0
        if is_binary:
            if status != "unchanged":
                left_hash = hashlib.sha256((left["content"] if left else "").encode("utf-8")).hexdigest()[:12]
                right_hash = hashlib.sha256((right["content"] if right else "").encode("utf-8")).hexdigest()[:12]
                hunks.append(f"@@ binary wasm file ({left_hash} -> {right_hash}) @@")
        elif status != "unchanged":
            left_lines = (left["content"] if left else "").splitlines()
            right_lines = (right["content"] if right else "").splitlines()
            diff_iter = difflib.unified_diff(
                left_lines,
                right_lines,
                fromfile=f"a/{name}" if left is not None else "/dev/null",
                tofile=f"b/{name}" if right is not None else "/dev/null",
                lineterm="",
                n=3,
            )
            for line in diff_iter:
                if line.startswith("+") and not line.startswith("+++"):
                    file_added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    file_removed += 1
                if emitted_lines < max_diff_lines:
                    hunks.append(line)
                    emitted_lines += 1
                else:
                    summary["truncated"] = True
        summary["lines_added"] += file_added
        summary["lines_removed"] += file_removed
        file_diffs.append({
            "name": name,
            "status": status,
            "binary": is_binary,
            "lines_added": file_added,
            "lines_removed": file_removed,
            "hunks": hunks,
        })
    return {
        "name": slug,
        "from_revision": from_revision,
        "to_revision": to_revision,
        "summary": summary,
        "files": file_diffs,
    }


def compute_quota_status(
    root: Path,
    state: dict,
    legacy: dict,
    *,
    quotas: dict[str, int],
    secrets_count: int,
    secrets_total_bytes: int,
    recent_429_count: int = 0,
) -> dict:
    """Compute current resource utilization and near-limit saturation indicators."""
    names = function_names(state, legacy)
    published_count = 0
    largest_bytes = 0
    largest_name: str | None = None
    total_bytes_all = 0
    for slug in names:
        fn = item(root, state, slug, legacy)
        if not fn:
            continue
        if fn.get("published_revision"):
            published_count += 1
        fn_bytes = sum(len(f["content"].encode("utf-8")) + len(f["name"]) for f in fn["files"])
        total_bytes_all += fn_bytes
        if fn_bytes >= largest_bytes:
            largest_bytes = fn_bytes
            largest_name = slug

    def _pct(used: int, cap: int) -> int:
        return round((used * 100) / cap) if cap > 0 else 0

    usage = {
        "functions_count": len(names),
        "published_count": published_count,
        "total_draft_bytes": total_bytes_all,
        "largest_function_bytes": largest_bytes,
        "largest_function_name": largest_name,
        "secrets_count": secrets_count,
        "secrets_total_bytes": secrets_total_bytes,
        "recent_429_count": recent_429_count,
    }
    utilization_pct = {
        "functions": _pct(len(names), quotas["max_functions"]),
        "largest_bundle_bytes": _pct(largest_bytes, quotas["max_bytes"]),
        "secrets": _pct(secrets_count, quotas["max_secrets"]),
        "secrets_bytes": _pct(secrets_total_bytes, quotas["max_secrets_total_bytes"]),
    }
    threshold = quotas["alert_threshold_pct"]
    near_limits: list[dict] = []
    checks = (
        ("functions", "functions_count", "Functions count", len(names), quotas["max_functions"]),
        ("largest_bundle_bytes", "max_bytes", "Largest function bundle", largest_bytes, quotas["max_bytes"]),
        ("secrets", "secrets_count", "Secrets count", secrets_count, quotas["max_secrets"]),
        ("secrets_bytes", "secrets_total_bytes", "Secrets total size", secrets_total_bytes, quotas["max_secrets_total_bytes"]),
    )
    for metric_key, code, label, used, cap in checks:
        pct = utilization_pct[metric_key]
        if pct >= threshold:
            near_limits.append({
                "kind": "near_limit",
                "metric": code,
                "severity": "critical" if pct >= 100 else "warn",
                "used": used,
                "limit": cap,
                "utilization_pct": pct,
                "message": f"{label} at {pct}% of quota ({used}/{cap})",
            })
    if recent_429_count > 0:
        near_limits.append({
            "kind": "concurrency_429",
            "metric": "max_concurrent_project",
            "severity": "critical" if recent_429_count >= 5 else "warn",
            "used": recent_429_count,
            "limit": quotas["max_concurrent_project"],
            "utilization_pct": 100,
            "message": f"{recent_429_count} concurrency saturation response(s) (HTTP 429) detected",
        })
    return {"usage": usage, "utilization_pct": utilization_pct, "active_alerts": near_limits}
