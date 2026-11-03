"""Private Studio drafts and content-addressed, project-bound function versions.

Only published pointers are consumed by the runtime publisher. Callers hold
edge_functions.configuration_lock for the entire read/modify/publish operation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from app import edge_functions

SLUG = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
REVISION = re.compile(r"[0-9a-f]{64}\Z")
SEGMENT = re.compile(r"[A-Za-z0-9_@][A-Za-z0-9_@.\-]{0,99}\Z")
MAX_FILES = 64
MAX_BYTES = 1_000_000
MAX_FUNCTIONS = 128


def function_name(value: str) -> str:
    if not SLUG.fullmatch(value) or value == "main":
        raise ValueError("Invalid function name")
    return value


def validate_files(files: list[dict]) -> list[dict[str, str]]:
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("A function requires 1 to 64 text files")
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
    if size > MAX_BYTES:
        raise ValueError("Function files exceed the 1 MB limit")
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
            or not isinstance(state["functions"], dict) or len(state["functions"]) > MAX_FUNCTIONS):
        raise RuntimeError("Function storage project identity mismatch")
    for slug, item in state["functions"].items():
        function_name(slug)
        if (not isinstance(item, dict) or set(item) != {"draft", "published"}
                or not isinstance(item["draft"], str) or not REVISION.fullmatch(item["draft"])
                or (item["published"] is not None and
                    (not isinstance(item["published"], str) or not REVISION.fullmatch(item["published"])))):
            raise RuntimeError("Invalid function revision pointers")
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


def begin_publication(root: Path, previous: dict, proposed: dict, context: dict) -> None:
    # A durable intent bridges the two atomic files. A process killed after
    # runtime activation can be recovered without publishing any later draft.
    atomic_json(directory(root, previous["project"], previous["uuid"]) / "publication.json", {
        "previous": previous, "proposed": proposed, "runtime_revision": context["revision"],
    })


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
        if (not isinstance(intent, dict) or set(intent) != {"previous", "proposed", "runtime_revision"}
                or not isinstance(intent["runtime_revision"], str) or not REVISION.fullmatch(intent["runtime_revision"])):
            raise RuntimeError("Invalid function publication intent")
        previous = validate_state(intent["previous"], name, identity)
        proposed = validate_state(intent["proposed"], name, identity)
        if set(previous["functions"]) != set(proposed["functions"]):
            raise RuntimeError("Publication intent changed function names")
        changes = [slug for slug in previous["functions"] if previous["functions"][slug] != proposed["functions"][slug]]
        if (len(changes) != 1 or any(previous["functions"][slug]["draft"] != proposed["functions"][slug]["draft"] for slug in previous["functions"])
                or proposed["functions"][changes[0]]["published"] != proposed["functions"][changes[0]]["draft"]):
            raise RuntimeError("Publication intent must activate one saved draft")
        current = read_state(root, name, identity)
        if current != previous and current != proposed:
            raise RuntimeError("Function state changed during interrupted publication")
        context = edge_functions.read_context(root, name, identity)
        if context and context["revision"] == intent["runtime_revision"]:
            files = published_files(root, name, identity, state=proposed)
            expected = edge_functions.context_value(name, identity, context["jwt_secret"], context["env"], files, context.get("network_allowlist"))
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


def version(name: str, identity: str, slug: str, files: list[dict]) -> tuple[str, dict]:
    value = {"project": name, "uuid": identity, "function": function_name(slug), "files": validate_files(files)}
    return hashlib.sha256(encoded(value)).hexdigest(), value


def store_version(root: Path, name: str, identity: str, slug: str, files: list[dict]) -> str:
    revision, value = version(name, identity, slug, files)
    versions = edge_functions.private_directory(directory(root, name, identity) / "versions" / slug)
    path = versions / (revision + ".json")
    try:
        existing = regular_bytes(path, MAX_BYTES * 6 + 65536)
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
    value = json.loads(regular_bytes(path, MAX_BYTES * 6 + 65536))
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
        files = read_version(root, state, slug, pointers["draft"])
        return {"name": slug, "revision": pointers["draft"], "published_revision": pointers["published"], "files": files}
    if slug in legacy:
        revision, _ = version(state["project"], state["uuid"], slug, legacy[slug])
        return {"name": slug, "revision": revision, "published_revision": revision, "files": legacy[slug]}
    return None


def published_files(root: Path, name: str, identity: str, *, state: dict | None = None) -> dict[str, bytes]:
    state = load(root, name, identity) if state is None else state
    functions = legacy_functions(root, name)
    for slug, pointers in state["functions"].items():
        if pointers["published"]:
            functions[slug] = read_version(root, state, slug, pointers["published"])
    if len(functions) > MAX_FUNCTIONS:
        raise RuntimeError("Too many published functions")
    return {slug + "/" + file["name"]: file["content"].encode()
            for slug, files in functions.items() for file in files}
