#!/usr/bin/env python3
"""Synchronize existing tenant project configurations with current templates, changing only what changed.

`docker-compose.yml` and `.env` are updated surgically key by key (environment variables, networks,
Traefik routing labels, and internal upstreams), so per-project customizations such as auth hooks or
extra networks are preserved. Template-derived files (`nginx_<slug>.conf`, `Dockerfile`, and optional
`keys.conf.template` / `pooler.stream-template`) are traced back to the committed template version
they originated from: a pure template version is updated to the current template, a customized file
receives only the template delta through a three-way merge, and an unmergeable file leaves its whole
project untouched and reported as `NEEDS_REVIEW`. Nothing is modified without a mode-0600 backup,
and `--dry-run` (the default) previews every planned change first.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECTS_DIR = REPO_ROOT / "servidor" / "projects"
DEFAULT_SERVER_ENV = REPO_ROOT / "servidor" / ".env"
DEFAULT_TEMPLATES_DIR = REPO_ROOT / "servidor" / "generateProject"

PROJECT_SLUG_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
ENV_LINE_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
REDUNDANT_ENV_FILES = frozenset({"../../.env", ".env", "./.env"})
TARGET_SERVICES = ("nginx", "auth", "rest")

REQUIRED_NGINX_ENV: tuple[tuple[str, str], ...] = (
    ("ANON_KEY_PROJETO", "${ANON_KEY_PROJETO}"),
    ("SERVICE_ROLE_KEY_PROJETO", "${SERVICE_ROLE_KEY_PROJETO}"),
    ("API_GATEWAY_TOKEN_PROJETO", "${API_GATEWAY_TOKEN_PROJETO}"),
)
SEC11_NGINX_ENV: tuple[tuple[str, str], ...] = REQUIRED_NGINX_ENV + (
    ("PROJECT_GATEWAYS_SUBNET", "${PROJECT_GATEWAYS_SUBNET:-172.54.0.0/23}"),
    ("PROJECT_INTERNAL_SUBNET", "${PROJECT_INTERNAL_SUBNET:?defina PROJECT_INTERNAL_SUBNET no .env do projeto}"),
    ("POOLER_PROXY_PORT_SESSION", "${POOLER_PROXY_PORT_SESSION}"),
    ("POOLER_PROXY_PORT_TRANSACTION", "${POOLER_PROXY_PORT_TRANSACTION}"),
)
RETIRED_SEC11_NGINX_ENV: tuple[str, ...] = ("POSTGRES_POOLER",)

CANONICAL_PROJECT_NETWORKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project-gateways", ("    external: true", "    name: supabase-project-gateways")),
    ("storage-gateways", ("    external: true", "    name: supabase-storage-gateways")),
    ("functions-gateways", ("    external: true", "    name: supabase-functions-gateways")),
    ("project-egress", ("    external: true", "    name: supabase-project-egress")),
    (
        "project-internal",
        (
            "    name: supabase-internal-{slug}",
            "    driver: bridge",
            "    internal: true",
            "    ipam:",
            "      config:",
            "        - subnet: ${PROJECT_INTERNAL_SUBNET:?defina PROJECT_INTERNAL_SUBNET no .env do projeto}",
        ),
    ),
)

TEMPLATE_FILES = (
    "dockercomposetemplate",
    "nginxtemplate",
    "Dockerfile",
    "keys.conf.template",
    "pooler.stream-template",
)
REQUIRED_NGINX_SYNC_TEMPLATES = ("nginxtemplate", "Dockerfile")
OPTIONAL_SYNC_TEMPLATES = ("keys.conf.template", "pooler.stream-template")
COMPOSE_BLOCKING = frozenset({"conflict", "no-history"})
NEEDS_REVIEW = frozenset({"conflict", "no-history", "missing-data"})
FORCEABLE = frozenset({"conflict", "no-history"})


def _load_subnet_allocator(templates_dir: Path) -> ModuleType:
    helper_path = templates_dir / "allocate_project_subnet.py"
    if not helper_path.is_file():
        helper_path = DEFAULT_TEMPLATES_DIR / "allocate_project_subnet.py"
    spec = importlib.util.spec_from_file_location("allocate_project_subnet", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load subnet allocator from {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_env_file(path: Path, *, allow_unreadable: bool = False) -> tuple[dict[str, str], bool]:
    """Parse KEY=VALUE pairs without shell evaluation or printing secrets."""
    if not path.exists():
        return {}, True
    try:
        raw = path.read_text(encoding="utf-8")
    except PermissionError:
        if allow_unreadable:
            return {}, False
        raise
    values: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key, val = match.group(1), match.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]
        values[key] = val
    return values, True


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _subblock_end(lines: list[str], start: int, limit: int, parent_indent: int) -> int:
    """Return exclusive end index of a YAML child block, excluding trailing blanks/comments."""
    end = start
    idx = start
    while idx < limit:
        line = lines[idx]
        if _is_blank_or_comment(line):
            idx += 1
            continue
        if _line_indent(line) <= parent_indent:
            break
        end = idx + 1
        idx += 1
    return end


def _service_bounds(lines: list[str], service_name: str) -> tuple[int, int, int] | None:
    """Return `(header_idx, exclusive_end_idx, service_indent)` for `services.<service_name>`."""
    services_idx = next(
        (i for i, line in enumerate(lines) if re.match(r"^services:\s*(?:#.*)?$", line)),
        None,
    )
    if services_idx is None:
        return None
    services_end = len(lines)
    for i in range(services_idx + 1, len(lines)):
        if not _is_blank_or_comment(lines[i]) and _line_indent(lines[i]) == 0:
            services_end = i
            break

    child_indent = next(
        (
            _line_indent(lines[i])
            for i in range(services_idx + 1, services_end)
            if not _is_blank_or_comment(lines[i])
        ),
        None,
    )
    if child_indent is None:
        return None

    header_re = re.compile(rf"^{' ' * child_indent}{re.escape(service_name)}:\s*(?:#.*)?$")
    for i in range(services_idx + 1, services_end):
        if header_re.match(lines[i]):
            svc_end = _subblock_end(lines, i + 1, services_end, child_indent)
            return i, svc_end, child_indent
    return None


def _service_prop_indent(lines: list[str], svc_idx: int, svc_end: int, svc_indent: int) -> int:
    return next(
        (
            _line_indent(lines[i])
            for i in range(svc_idx + 1, svc_end)
            if not _is_blank_or_comment(lines[i])
        ),
        svc_indent + 2,
    )


def _extract_env_file_item_path(item_lines: list[str]) -> str | None:
    if not item_lines:
        return None
    first = item_lines[0].strip()
    if not first.startswith("-"):
        return None
    rest = first[1:].strip()
    if rest.startswith("path:"):
        return rest[5:].strip().strip("'\"")
    if rest and ":" not in rest:
        return rest.strip("'\"")
    if not rest:
        for sub in item_lines[1:]:
            stripped = sub.strip()
            if stripped.startswith("path:"):
                return stripped[5:].strip().strip("'\"")
    return None


def _strip_redundant_env_files(lines: list[str], service_name: str) -> list[str]:
    """Remove redundant master/project `env_file` entries (`../../.env`, `.env`) from a service block."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, svc_indent = bounds
    prop_indent = _service_prop_indent(lines, svc_idx, svc_end, svc_indent)
    env_file_re = re.compile(rf"^{' ' * prop_indent}env_file:[ \t]*(.*?)\r?\n?$")

    idx = next(
        (i for i in range(svc_idx + 1, svc_end) if env_file_re.match(lines[i])),
        None,
    )
    if idx is None:
        return lines

    match = env_file_re.match(lines[idx])
    assert match is not None
    inline_val = match.group(1).strip()
    if inline_val and not inline_val.startswith("#"):
        if inline_val.startswith("[") and inline_val.endswith("]"):
            items = [item.strip() for item in inline_val[1:-1].split(",") if item.strip()]
            kept = [item for item in items if item.strip("'\"") not in REDUNDANT_ENV_FILES]
            if not kept:
                return lines[:idx] + lines[idx + 1 :]
            return lines[:idx] + [f"{' ' * prop_indent}env_file: [{', '.join(kept)}]\n"] + lines[idx + 1 :]
        if inline_val.strip("'\"") in REDUNDANT_ENV_FILES:
            return lines[:idx] + lines[idx + 1 :]
        return lines

    block_end = idx + 1
    scan = idx + 1
    while scan < svc_end:
        line = lines[scan]
        if _is_blank_or_comment(line):
            scan += 1
            continue
        indent = _line_indent(line)
        if indent < prop_indent or (indent == prop_indent and not line.lstrip(" ").startswith("-")):
            break
        block_end = scan + 1
        scan += 1
    item_indent = next(
        (
            _line_indent(lines[i])
            for i in range(idx + 1, block_end)
            if not _is_blank_or_comment(lines[i]) and lines[i].lstrip(" ").startswith("-")
        ),
        None,
    )
    if item_indent is None:
        return lines

    kept_block_lines: list[str] = []
    cur = idx + 1
    while cur < block_end:
        line = lines[cur]
        if _is_blank_or_comment(line) or not (
            _line_indent(line) == item_indent and line.lstrip(" ").startswith("-")
        ):
            kept_block_lines.append(line)
            cur += 1
            continue
        item_end = _subblock_end(lines, cur + 1, block_end, item_indent)
        item_slice = lines[cur:item_end]
        if _extract_env_file_item_path(item_slice) not in REDUNDANT_ENV_FILES:
            kept_block_lines.extend(item_slice)
        cur = item_end

    has_remaining_item = any(
        not _is_blank_or_comment(line) and line.lstrip(" ").startswith("-")
        for line in kept_block_lines
    )
    if not has_remaining_item:
        return lines[:idx] + lines[block_end:]
    return lines[: idx + 1] + kept_block_lines + lines[block_end:]


def _find_environment_block(
    lines: list[str], svc_idx: int, svc_end: int, prop_indent: int
) -> tuple[int, int, str] | None:
    env_re = re.compile(rf"^{' ' * prop_indent}environment:[ \t]*(.*?)\r?\n?$")
    for i in range(svc_idx + 1, svc_end):
        match = env_re.match(lines[i])
        if match:
            end = _subblock_end(lines, i + 1, svc_end, prop_indent)
            return i, end, match.group(1).strip()
    return None


def _ensure_service_env_vars(
    lines: list[str], service_name: str, pairs: tuple[tuple[str, str], ...]
) -> list[str]:
    """Ensure required KEY: VALUE pairs exist inside `<service>.environment` without touching other keys."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, svc_indent = bounds
    prop_indent = _service_prop_indent(lines, svc_idx, svc_end, svc_indent)
    env_block = _find_environment_block(lines, svc_idx, svc_end, prop_indent)

    if env_block is None:
        anchor_re = re.compile(
            rf"^{' ' * prop_indent}(?:volumes|networks|labels|ports|healthcheck|command|depends_on):"
        )
        insert_idx = next(
            (i for i in range(svc_idx + 1, svc_end) if anchor_re.match(lines[i])),
            svc_end,
        )
        entry_indent = " " * (prop_indent + 2)
        updated = list(lines)
        if insert_idx > 0 and not updated[insert_idx - 1].endswith("\n"):
            updated[insert_idx - 1] += "\n"
        added = [f"{' ' * prop_indent}environment:\n"] + [
            f"{entry_indent}{key}: {value}\n" for key, value in pairs
        ]
        return updated[:insert_idx] + added + updated[insert_idx:]

    env_idx, env_end, inline_val = env_block
    updated = list(lines)
    is_list = False
    entry_indent = " " * (prop_indent + 2)
    existing_keys: set[str] = set()

    if inline_val in {"{}", "[]"}:
        updated[env_idx] = f"{' ' * prop_indent}environment:\n"
        is_list = inline_val == "[]"
        env_end = env_idx + 1
    else:
        for i in range(env_idx + 1, env_end):
            line = updated[i]
            if _is_blank_or_comment(line):
                continue
            list_match = re.match(
                r"^(\s+)-\s*(?:[\"'])?([A-Za-z_][A-Za-z0-9_]*)(?:=|\s|$)", line
            )
            if list_match:
                is_list = True
                entry_indent = list_match.group(1)
                existing_keys.add(list_match.group(2))
                continue
            map_match = re.match(r"^(\s+)([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if map_match:
                entry_indent = map_match.group(1)
                existing_keys.add(map_match.group(2))

    missing = [
        (
            f"{entry_indent}- {key}={value}\n"
            if is_list
            else f"{entry_indent}{key}: {value}\n"
        )
        for key, value in pairs
        if key not in existing_keys
    ]
    if not missing:
        return lines
    if env_end > 0 and not updated[env_end - 1].endswith("\n"):
        updated[env_end - 1] += "\n"
    return updated[:env_end] + missing + updated[env_end:]


def _remove_service_env_var(lines: list[str], service_name: str, key: str) -> list[str]:
    """Remove an active KEY from `<service>.environment`, preserving comments and hooks."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, svc_indent = bounds
    prop_indent = _service_prop_indent(lines, svc_idx, svc_end, svc_indent)
    env_block = _find_environment_block(lines, svc_idx, svc_end, prop_indent)
    if env_block is None:
        return lines
    env_idx, env_end, _ = env_block
    key_re = re.compile(rf"^\s+(?:-\s*(?:[\"'])?)?{re.escape(key)}(?:\s*:|=)")
    kept: list[str] = []
    removed = False
    for i in range(env_idx + 1, env_end):
        line = lines[i]
        if not _is_blank_or_comment(line) and key_re.match(line):
            removed = True
            continue
        kept.append(line)
    if not removed:
        return lines
    if not any(not _is_blank_or_comment(line) for line in kept):
        return lines[:env_idx] + lines[env_end:]
    return lines[: env_idx + 1] + kept + lines[env_end:]


def _network_entries(
    lines: list[str], start: int, end: int, item_indent: int
) -> list[tuple[str, list[str]]]:
    """Return `(name, raw lines)` for every entry of a `networks:` block, in list or map form."""
    pad = " " * item_indent
    item_re = re.compile(rf"^{pad}-\s*([A-Za-z0-9_.-]+)\s*(?:#.*)?$")
    key_re = re.compile(rf"^{pad}([A-Za-z0-9_.-]+):\s*(?:#.*)?$")
    entries: list[tuple[str, list[str]]] = []
    for raw in lines[start:end]:
        item, key = item_re.match(raw), key_re.match(raw)
        if item or key:
            matched = item or key
            assert matched is not None
            entries.append((matched.group(1), [raw]))
        elif entries and raw.strip() and _line_indent(raw) > item_indent:
            entries[-1][1].append(raw)
    return entries


def _set_service_networks(
    lines: list[str],
    service_name: str,
    network_names: tuple[str, ...],
    retired: tuple[str, ...] = ("rede-supabase",),
) -> list[str]:
    """Set the template networks of `<service>.networks`; custom project networks stay untouched."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, svc_indent = bounds
    prop_indent = _service_prop_indent(lines, svc_idx, svc_end, svc_indent)
    nets_re = re.compile(rf"^{' ' * prop_indent}networks:[ \t]*(.*?)\r?\n?$")
    item_indent = " " * (prop_indent + 2)
    replacement = [f"{' ' * prop_indent}networks:\n"] + [
        f"{item_indent}- {net}\n" for net in network_names
    ]

    idx = next((i for i in range(svc_idx + 1, svc_end) if nets_re.match(lines[i])), None)
    if idx is not None:
        match = nets_re.match(lines[idx])
        assert match is not None
        inline_val = match.group(1).strip()
        if inline_val and not inline_val.startswith("#"):
            names = re.findall(r"[A-Za-z0-9_.-]+", inline_val)
            block_end = idx + 1
            extras = [
                (name, [f"{item_indent}- {name}\n"])
                for name in names
                if name not in network_names and name not in retired
            ]
        else:
            block_end = _subblock_end(lines, idx + 1, svc_end, prop_indent)
            extras = [
                (name, raw)
                for name, raw in _network_entries(lines, idx + 1, block_end, prop_indent + 2)
                if name not in network_names and name not in retired
            ]
        replacement += [line for _name, raw in extras for line in raw]
        return lines[:idx] + replacement + lines[block_end:]

    anchor_re = re.compile(rf"^{' ' * prop_indent}(?:environment|volumes|ports|labels|command):")
    insert_idx = next((i for i in range(svc_idx + 1, svc_end) if anchor_re.match(lines[i])), svc_end)
    updated = list(lines)
    if insert_idx > 0 and not updated[insert_idx - 1].endswith("\n"):
        updated[insert_idx - 1] += "\n"
    return updated[:insert_idx] + replacement + updated[insert_idx:]


def _split_inline_bracketed(text: str, open_ch: str, close_ch: str) -> tuple[str, str] | None:
    """Split `[...] # comment` or `{...} # comment` into `(bracketed, tail)` respecting quotes."""
    if not text.startswith(open_ch):
        return None
    quote_ch: str | None = None
    escaped = False
    for i, ch in enumerate(text):
        if quote_ch is not None:
            if escaped:
                escaped = False
            elif ch == "\\" and quote_ch == '"':
                escaped = True
            elif ch == quote_ch:
                quote_ch = None
            continue
        if ch in {'"', "'"}:
            quote_ch = ch
        elif ch == close_ch:
            return text[: i + 1], text[i + 1 :]
    return None


def _split_inline_items(inner: str) -> list[str]:
    """Split comma-separated flow YAML items while respecting single and double quotes."""
    items: list[str] = []
    cur: list[str] = []
    quote_ch: str | None = None
    escaped = False
    for ch in inner:
        if quote_ch is not None:
            cur.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\" and quote_ch == '"':
                escaped = True
            elif ch == quote_ch:
                quote_ch = None
            continue
        if ch in {'"', "'"}:
            quote_ch = ch
            cur.append(ch)
        elif ch == ",":
            item = "".join(cur).strip()
            if item:
                items.append(item)
            cur = []
        else:
            cur.append(ch)
    item = "".join(cur).strip()
    if item:
        items.append(item)
    return items


def _unquote_yaml_scalar(token: str) -> str:
    stripped = token.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _ensure_service_label(
    lines: list[str], service_name: str, label: str, value: str
) -> list[str]:
    """Add or update a single label on a service; every other label stays as the project left it."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, svc_indent = bounds
    prop_indent = _service_prop_indent(lines, svc_idx, svc_end, svc_indent)
    labels_re = re.compile(rf"^{' ' * prop_indent}labels:[ \t]*(.*?)\r?\n?$")
    idx = next((i for i in range(svc_idx + 1, svc_end) if labels_re.match(lines[i])), None)
    wanted = f"{label}={value}"
    updated = list(lines)

    if idx is None:
        pad = " " * (prop_indent + 2)
        nets_re = re.compile(rf"^{' ' * prop_indent}networks:")
        insert_at = next((i for i in range(svc_idx + 1, svc_end) if nets_re.match(lines[i])), svc_end)
        if insert_at > 0 and not updated[insert_at - 1].endswith("\n"):
            updated[insert_at - 1] += "\n"
        added = [f"{' ' * prop_indent}labels:\n", f'{pad}- "{wanted}"\n']
        return updated[:insert_at] + added + updated[insert_at:]

    match = labels_re.match(lines[idx])
    assert match is not None
    inline_val = match.group(1).strip()
    if inline_val and not inline_val.startswith("#"):
        list_split = _split_inline_bracketed(inline_val, "[", "]")
        if list_split is not None:
            bracketed, tail = list_split
            items = _split_inline_items(bracketed[1:-1])
            new_items: list[str] = []
            found = False
            for item in items:
                raw = _unquote_yaml_scalar(item)
                if raw.startswith(f"{label}="):
                    if not found:
                        found = True
                        new_items.append(item if raw == wanted else f'"{wanted}"')
                    continue
                new_items.append(item)
            if not found:
                new_items.append(f'"{wanted}"')
            new_line = f"{' ' * prop_indent}labels: [{', '.join(new_items)}]{tail}\n"
            if new_line == lines[idx]:
                return lines
            updated[idx] = new_line
            return updated

        map_split = _split_inline_bracketed(inline_val, "{", "}")
        if map_split is not None:
            bracketed, tail = map_split
            items = _split_inline_items(bracketed[1:-1])
            new_items = []
            found = False
            for item in items:
                kv = re.match(r"""^((?:"[^"]*"|'[^']*'|[^:]+?))\s*:\s*(.*)$""", item)
                if kv and _unquote_yaml_scalar(kv.group(1)) == label:
                    if not found:
                        found = True
                        if _unquote_yaml_scalar(kv.group(2)) == value:
                            new_items.append(item)
                        else:
                            new_items.append(f'{kv.group(1).strip()}: "{value}"')
                    continue
                new_items.append(item)
            if not found:
                new_items.append(f'{label}: "{value}"')
            new_line = f"{' ' * prop_indent}labels: {{{', '.join(new_items)}}}{tail}\n"
            if new_line == lines[idx]:
                return lines
            updated[idx] = new_line
            return updated

    block_end = idx + 1
    scan = idx + 1
    while scan < svc_end:
        line = lines[scan]
        if _is_blank_or_comment(line):
            scan += 1
            continue
        indent = _line_indent(line)
        if indent < prop_indent or (indent == prop_indent and not line.lstrip(" ").startswith("-")):
            break
        block_end = scan + 1
        scan += 1

    list_target_re = re.compile(
        rf"""^(?P<prefix>\s*-\s*)(?:"{re.escape(label)}=(?P<dq>[^"]*)"|'{re.escape(label)}=(?P<sq>[^']*)'|{re.escape(label)}=(?P<uq>[^#\r\n]*?))(?P<tail>[ \t]*(?:#.*)?)\r?\n?$"""
    )
    map_target_re = re.compile(
        rf"""^(?P<prefix>\s*(?:"{re.escape(label)}"|'{re.escape(label)}'|{re.escape(label)})\s*:)[ \t]*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<uq>[^#\r\n]*?))(?P<tail>[ \t]*(?:#.*)?)\r?\n?$"""
    )
    list_item_re = re.compile(r"^(\s*)-\s")
    map_item_re = re.compile(r"""^(\s*)(?:"[^"]+"|'[^']+'|[^-\s#][^:\r\n]*)\s*:""")

    seen_list = False
    seen_map = False
    entry_indent = " " * (prop_indent + 2)
    indent_detected = False
    enable_idx: int | None = None
    found = False
    changed = False
    new_block: list[str] = []

    for i in range(idx + 1, block_end):
        line = lines[i]
        if _is_blank_or_comment(line):
            new_block.append(line)
            continue

        list_match = list_target_re.match(line)
        if list_match:
            seen_list = True
            if not indent_detected:
                entry_indent = " " * _line_indent(line)
                indent_detected = True
            if found:
                changed = True
                continue
            found = True
            cur_val = (
                list_match.group("dq")
                if list_match.group("dq") is not None
                else list_match.group("sq")
                if list_match.group("sq") is not None
                else list_match.group("uq").strip()
            )
            if cur_val == value:
                new_block.append(line)
            else:
                changed = True
                quote_ch = "'" if list_match.group("sq") is not None else '"'
                trailing = list_match.group("tail") or ""
                new_block.append(f"{list_match.group('prefix')}{quote_ch}{wanted}{quote_ch}{trailing}\n")
            continue

        map_match = map_target_re.match(line)
        if map_match:
            seen_map = True
            if not indent_detected:
                entry_indent = " " * _line_indent(line)
                indent_detected = True
            if found:
                changed = True
                continue
            found = True
            cur_val = (
                map_match.group("dq")
                if map_match.group("dq") is not None
                else map_match.group("sq")
                if map_match.group("sq") is not None
                else map_match.group("uq").strip()
            )
            if cur_val == value:
                new_block.append(line)
            else:
                changed = True
                trailing = map_match.group("tail") or ""
                if map_match.group("sq") is not None:
                    formatted = f"'{value}'"
                elif map_match.group("dq") is not None:
                    formatted = f'"{value}"'
                else:
                    formatted = value
                new_block.append(f"{map_match.group('prefix')} {formatted}{trailing}\n")
            continue

        li = list_item_re.match(line)
        if li:
            seen_list = True
            if not indent_detected:
                entry_indent = li.group(1)
                indent_detected = True
            if re.search(r"""(?:^|[\s"'])traefik\.enable=""", line):
                enable_idx = len(new_block)
        else:
            mi = map_item_re.match(line)
            if mi:
                seen_map = True
                if not indent_detected:
                    entry_indent = mi.group(1)
                    indent_detected = True
                if re.match(r"""^\s*(?:["'])?traefik\.enable(?:["'])?\s*:""", line):
                    enable_idx = len(new_block)
        new_block.append(line)

    if found:
        if not changed:
            return lines
        return updated[: idx + 1] + new_block + updated[block_end:]

    is_map = seen_map and not seen_list
    added_line = f'{entry_indent}{label}: "{value}"\n' if is_map else f'{entry_indent}- "{wanted}"\n'
    insert_pos = enable_idx + 1 if enable_idx is not None else 0
    if insert_pos == 0 and not updated[idx].endswith("\n"):
        updated[idx] += "\n"
    elif insert_pos > 0 and not new_block[insert_pos - 1].endswith("\n"):
        new_block[insert_pos - 1] += "\n"
    new_block.insert(insert_pos, added_line)
    return updated[: idx + 1] + new_block + updated[block_end:]


def _rewrite_service_upstreams(lines: list[str], service_name: str, slug: str) -> list[str]:
    """Point project auth/rest DB pooler and template-service URLs through per-project nginx streams."""
    bounds = _service_bounds(lines, service_name)
    if bounds is None:
        return lines
    svc_idx, svc_end, _svc_indent = bounds
    nginx_host = f"supabase-nginx-{slug}"
    updated = list(lines)
    for i in range(svc_idx + 1, svc_end):
        line = updated[i]
        line = re.sub(
            r"@\$\{POSTGRES_POOLER\}:(\$\{POOLER_PROXY_PORT_(?:SESSION|TRANSACTION)(?:[:-][^}]*)?\}|\d+)/",
            rf"@{nginx_host}:\1/",
            line,
        )
        line = line.replace("http://template-service:18020/", f"http://{nginx_host}:18020/")
        updated[i] = line
    return updated


def _ensure_top_level_networks(
    lines: list[str], slug: str, keep_retired: tuple[str, ...] = ()
) -> list[str]:
    """Ensure the canonical template networks exist at top level; custom project networks stay untouched."""
    retired = {"rede-supabase"} - set(keep_retired)
    canonical_names = {name for name, _body in CANONICAL_PROJECT_NETWORKS}
    block = ["networks:\n"]
    for name, body in CANONICAL_PROJECT_NETWORKS:
        block.append(f"  {name}:\n")
        block.extend(line.replace("{slug}", slug) + "\n" for line in body)
    net_idx = next(
        (i for i, line in enumerate(lines) if re.match(r"^networks:\s*(?:#.*)?$", line)),
        None,
    )
    if net_idx is None:
        insert_idx = next(
            (i for i, line in enumerate(lines) if re.match(r"^volumes:\s*(?:#.*)?$", line)),
            len(lines),
        )
        updated = list(lines)
        if insert_idx > 0 and not updated[insert_idx - 1].endswith("\n"):
            updated[insert_idx - 1] += "\n"
        return updated[:insert_idx] + block + updated[insert_idx:]

    net_end = len(lines)
    for i in range(net_idx + 1, len(lines)):
        if not _is_blank_or_comment(lines[i]) and _line_indent(lines[i]) == 0:
            net_end = i
            break
    extras: list[str] = []
    keep = True
    for raw in lines[net_idx + 1 : net_end]:
        entry = re.match(r"^  ([A-Za-z0-9_.-]+):\s*(?:#.*)?$", raw)
        if entry:
            keep = entry.group(1) not in canonical_names and entry.group(1) not in retired
        if keep:
            extras.append(raw)
    return lines[:net_idx] + block + extras + lines[net_end:]


def _upsert_env_text(env_text: str, updates: dict[str, str]) -> str:
    lines = env_text.splitlines(keepends=True)
    for key, val in updates.items():
        pat = re.compile(rf"^[ \t]*{re.escape(key)}=")
        replaced = False
        for i, line in enumerate(lines):
            if pat.match(line):
                lines[i] = f"{key}={val}\n"
                replaced = True
                break
        if not replaced:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{key}={val}\n")
    return "".join(lines)


def render_project_compose(
    template_text: str,
    slug: str,
    existing_compose_text: str,
    server_env: dict[str, str],
    proj_env: dict[str, str],
    *,
    proj_env_readable: bool = True,
    segregate_networks: bool = False,
) -> str:
    """Surgically apply SEC-11 hardening while preserving per-project customizations (e.g. auth hooks)."""
    del template_text, server_env, proj_env, proj_env_readable
    if not PROJECT_SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid project slug: {slug}")

    lines = existing_compose_text.splitlines(keepends=True)
    for svc in TARGET_SERVICES:
        lines = _strip_redundant_env_files(lines, svc)

    nginx_env = SEC11_NGINX_ENV if segregate_networks else REQUIRED_NGINX_ENV
    lines = _ensure_service_env_vars(lines, "nginx", nginx_env)

    if segregate_networks:
        for retired_key in RETIRED_SEC11_NGINX_ENV:
            lines = _remove_service_env_var(lines, "nginx", retired_key)
        lines = _set_service_networks(
            lines,
            "nginx",
            ("project-gateways", "storage-gateways", "functions-gateways", "project-internal"),
        )
        lines = _set_service_networks(lines, "auth", ("project-internal", "project-egress"))
        lines = _set_service_networks(lines, "rest", ("project-internal",))
        lines = _ensure_service_label(
            lines, "nginx", "traefik.docker.network", "supabase-project-gateways"
        )
        lines = _rewrite_service_upstreams(lines, "auth", slug)
        lines = _rewrite_service_upstreams(lines, "rest", slug)
        # Keep top-level rede-supabase if another custom project service still attaches to it.
        services = re.sub(r"(?ms)^networks:.*?(?=^\S|\Z)", "", "".join(lines))
        still_shared = re.search(
            r"(?m)^\s+networks:\s*\[[^\]]*\brede-supabase\b"
            r"|^\s+-\s*rede-supabase\s*(?:#.*)?$"
            r"|^\s+rede-supabase\s*:\s*(?:#.*)?$",
            services,
        )
        lines = _ensure_top_level_networks(lines, slug, ("rede-supabase",) if still_shared else ())

    return "".join(lines)


def normalize_public_base_url(server_url: str, server_proto: str) -> str:
    url = server_url.strip().rstrip("/")
    if re.match(r"^https?://", url):
        return url
    proto = server_proto.strip() or "https"
    return f"{proto}://{url}"


def render_project_nginx(
    nginx_template_text: str,
    slug: str,
    server_env: dict[str, str],
    proj_env: dict[str, str],
) -> str:
    project_uuid = proj_env.get("PROJECT_UUID", "").strip()
    server_url = server_env.get("SERVER_URL", "").strip()
    project_public_ref = proj_env.get("PROJECT_PUBLIC_REF", "").strip()

    missing: list[str] = []
    if "{{project_uuid}}" in nginx_template_text and not project_uuid:
        missing.append("PROJECT_UUID")
    if (
        "{{server_url}}" in nginx_template_text
        or "{{public_base_url}}" in nginx_template_text
        or "{{project_public_url}}" in nginx_template_text
    ) and not server_url:
        missing.append("SERVER_URL")
    if "{{project_public_ref}}" in nginx_template_text and not project_public_ref:
        missing.append("PROJECT_PUBLIC_REF")
    if missing:
        raise RuntimeError(
            f"Cannot render nginx config for {slug}: missing {', '.join(missing)}"
        )

    public_base_url = (
        normalize_public_base_url(server_url, server_env.get("SERVER_PROTO", "https"))
        if server_url
        else ""
    )
    public_ref_or_slug = project_public_ref or slug
    docker_subnet = (
        server_env.get("SUPABASE_NETWORK_SUBNET")
        or server_env.get("DOCKER_SUBNET")
        or "172.50.0.0/16"
    ).strip()
    replacements = {
        "{{project_id}}": slug,
        "{{project_uuid}}": project_uuid,
        "{{project_public_ref}}": project_public_ref,
        "{{server_url}}": server_url,
        "{{project_public_url}}": f"{public_base_url}/{public_ref_or_slug}" if public_base_url else "",
        "{{public_base_url}}": public_base_url,
        "{{docker_subnet}}": docker_subnet,
    }
    rendered = nginx_template_text
    for marker, value in replacements.items():
        if marker in rendered:
            rendered = rendered.replace(marker, value)
    if "{{" in rendered:
        raise RuntimeError(f"Unresolved template markers in nginx config for {slug}")
    return rendered


def atomic_write_bytes(target: Path, data: bytes, mode: int) -> None:
    if target.is_symlink():
        raise RuntimeError(f"Refusing to write symlink: {target}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.tmp.", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_compose_candidate(
    project_dir: Path,
    slug: str,
    server_env_path: Path,
    proj_env_path: Path,
    candidate_compose_path: Path,
) -> None:
    cmd = [
        "docker",
        "compose",
        "-p",
        slug,
        "--project-directory",
        str(project_dir),
        "--env-file",
        str(server_env_path),
        "--env-file",
        str(proj_env_path),
        "-f",
        str(candidate_compose_path),
    ]
    override_path = project_dir / "docker-compose.override.yml"
    if override_path.is_file():
        cmd.extend(["-f", str(override_path)])
    cmd.extend(["config", "-q"])

    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        err_lines = [
            line.strip()
            for line in (completed.stderr or "").splitlines()
            if line.strip() and "=" not in line
        ]
        summary = err_lines[-1] if err_lines else f"exit code {completed.returncode}"
        raise RuntimeError(f"docker compose config -q failed for {slug}: {summary}")


def discover_projects(projects_dir: Path, selected: list[str] | None) -> list[Path]:
    if not projects_dir.is_dir():
        raise RuntimeError(f"Projects directory not found: {projects_dir}")

    if selected:
        discovered: list[Path] = []
        seen: set[str] = set()
        for slug in selected:
            if slug in seen:
                continue
            seen.add(slug)
            if not PROJECT_SLUG_RE.fullmatch(slug):
                raise RuntimeError(f"Invalid project slug: {slug}")
            proj_dir = projects_dir / slug
            if proj_dir.is_symlink() or not proj_dir.is_dir():
                raise RuntimeError(f"Project directory not found or symlink: {proj_dir}")
            entries = set(os.listdir(proj_dir))
            if ".env" not in entries or "docker-compose.yml" not in entries:
                raise RuntimeError(
                    f"Project directory missing .env or docker-compose.yml: {proj_dir}"
                )
            discovered.append(proj_dir)
        return discovered

    discovered = []
    for entry in sorted(projects_dir.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(".") or entry.is_symlink() or not entry.is_dir():
            continue
        if not PROJECT_SLUG_RE.fullmatch(entry.name):
            continue
        try:
            names = set(os.listdir(entry))
        except PermissionError:
            continue
        if ".env" in names and "docker-compose.yml" in names:
            discovered.append(entry)
    return discovered


def load_template_history(templates_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """Return every committed version of each template (newest first) to trace a project file to its origin."""
    history: dict[str, list[tuple[str, str]]] = {name: [] for name in TEMPLATE_FILES}
    try:
        base = templates_dir.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return history
    for name in TEMPLATE_FILES:
        rel = f"{base}/{name}"
        log = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "--format=%H", "--", rel],
            capture_output=True,
            text=True,
            check=False,
        )
        if log.returncode != 0:
            continue
        for commit in log.stdout.split():
            shown = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "show", f"{commit}:{rel}"],
                capture_output=True,
                check=False,
            )
            if shown.returncode == 0:
                history[name].append((commit, shown.stdout.decode("utf-8")))
    return history


def _sync_regions(
    base: list[str], ours: list[str], theirs: list[str]
) -> list[tuple[int, int, int, int, int, int]]:
    """Regions where base, ours and theirs hold identical lines (classic diff3 sync regions)."""
    ours_matches = difflib.SequenceMatcher(None, base, ours, autojunk=False).get_matching_blocks()
    theirs_matches = difflib.SequenceMatcher(None, base, theirs, autojunk=False).get_matching_blocks()
    regions: list[tuple[int, int, int, int, int, int]] = []
    i_ours = i_theirs = 0
    while i_ours < len(ours_matches) and i_theirs < len(theirs_matches):
        base_ours, start_ours, size_ours = ours_matches[i_ours]
        base_theirs, start_theirs, size_theirs = theirs_matches[i_theirs]
        start = max(base_ours, base_theirs)
        end = min(base_ours + size_ours, base_theirs + size_theirs)
        if start < end:
            ours_start = start_ours + (start - base_ours)
            theirs_start = start_theirs + (start - base_theirs)
            regions.append(
                (
                    start,
                    end,
                    ours_start,
                    ours_start + (end - start),
                    theirs_start,
                    theirs_start + (end - start),
                )
            )
        if base_ours + size_ours < base_theirs + size_theirs:
            i_ours += 1
        else:
            i_theirs += 1
    regions.append((len(base), len(base), len(ours), len(ours), len(theirs), len(theirs)))
    return regions


def _line_edits(base: list[str], other: list[str]) -> dict[int, tuple[str, int, int, int, int]]:
    """Map each base line touched by a change to the opcode that edits it (inserts sit at their anchor)."""
    edits: dict[int, tuple[str, int, int, int, int]] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, base, other, autojunk=False
    ).get_opcodes():
        if tag != "equal":
            for pos in range(i1, max(i2, i1 + 1)):
                edits[pos] = (tag, i1, i2, j1, j2)
    return edits


def _subsequence(small: list[str], large: list[str]) -> bool:
    remaining = iter(large)
    return all(any(line == candidate for candidate in remaining) for line in small)


def _same_block(a: list[str], b: list[str]) -> bool:
    """Return True when two blocks are edits of the same construct (sharing a non-blank line)."""
    meaningful = {line for line in a if line.strip()}
    return any(line.strip() and line in meaningful for line in b)


def _combine(
    ours: list[str], base: list[str], theirs: list[str], conflicts: list[int]
) -> list[str]:
    """Combine edits to the same base lines, preserving project decisions on real conflicts."""
    if ours == theirs:
        return ours
    prefix: list[str] = []
    suffix: list[str] = []
    while ours and theirs and ours[0] == theirs[0]:
        line = ours[0]
        prefix.append(line)
        ours, theirs = ours[1:], theirs[1:]
        if base and (base[0] == line or ours == base[1:] or theirs == base[1:]):
            base = base[1:]
    while ours and theirs and ours[-1] == theirs[-1]:
        line = ours[-1]
        suffix.append(line)
        ours, theirs = ours[:-1], theirs[:-1]
        if base and (base[-1] == line or ours == base[:-1] or theirs == base[:-1]):
            base = base[:-1]
    suffix.reverse()

    if ours == theirs or theirs == base:
        return prefix + ours + suffix
    if ours == base:
        return prefix + theirs + suffix
    if not ours:
        if not theirs or _same_block(base, theirs):
            return prefix + suffix
        return prefix + theirs + suffix
    if not theirs:
        conflicts.append(1)
        return prefix + ours + suffix
    if _subsequence(ours, theirs):
        return prefix + theirs + suffix
    if _subsequence(theirs, ours):
        return prefix + ours + suffix
    if not base:
        return prefix + theirs + ours + suffix
    conflicts.append(1)
    return prefix + ours + suffix


def _merge_region_lines(
    ours: list[str], base: list[str], theirs: list[str], conflicts: list[int]
) -> list[str]:
    """Merge a single unmatched region line by line so independent changes on different lines coexist."""
    edit_ours, edit_theirs = _line_edits(base, ours), _line_edits(base, theirs)
    out: list[str] = []
    pos = 0
    while pos < len(base) or pos in edit_ours or pos in edit_theirs:
        ours_edit, theirs_edit = edit_ours.get(pos), edit_theirs.get(pos)
        if ours_edit is not None and theirs_edit is None:
            touching = [k for k in range(pos + 1, max(ours_edit[2], pos + 1)) if k in edit_theirs]
            theirs_edit = edit_theirs[touching[0]] if touching else None
        elif theirs_edit is not None and ours_edit is None:
            touching = [k for k in range(pos + 1, max(theirs_edit[2], pos + 1)) if k in edit_ours]
            ours_edit = edit_ours[touching[0]] if touching else None
        if ours_edit is None and theirs_edit is None:
            out.append(base[pos])
            pos += 1
        elif theirs_edit is None:
            assert ours_edit is not None
            out.extend(ours[ours_edit[3] : ours_edit[4]])
            pos = max(ours_edit[2], ours_edit[1] + 1)
        elif ours_edit is None:
            out.extend(theirs[theirs_edit[3] : theirs_edit[4]])
            pos = max(theirs_edit[2], theirs_edit[1] + 1)
        elif (ours_edit[0] == "insert") != (theirs_edit[0] == "insert"):
            insertion, rewrite = (
                (ours_edit, theirs_edit) if ours_edit[0] == "insert" else (theirs_edit, ours_edit)
            )
            added = (ours if insertion is ours_edit else theirs)[insertion[3] : insertion[4]]
            rewritten = (ours if rewrite is ours_edit else theirs)[rewrite[3] : rewrite[4]]
            if not _subsequence(added, rewritten):
                out.extend(added)
            if insertion is ours_edit:
                edit_ours.pop(pos, None)
            else:
                edit_theirs.pop(pos, None)
        else:
            start = min(ours_edit[1], theirs_edit[1])
            end = max(ours_edit[2], theirs_edit[2])
            if end == start:
                edit_ours.pop(start, None)
                edit_theirs.pop(start, None)
            out.extend(
                _combine(
                    ours[ours_edit[3] - (ours_edit[1] - start) : ours_edit[4] + (end - ours_edit[2])],
                    base[start:end],
                    theirs[
                        theirs_edit[3] - (theirs_edit[1] - start) : theirs_edit[4] + (end - theirs_edit[2])
                    ],
                    conflicts,
                )
            )
            pos = end
    return out


def _resolve_region(
    ours: list[str], base: list[str], theirs: list[str], conflicts: list[int]
) -> list[str]:
    """Resolve one unmatched region, keeping project changes over template defaults."""
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    return _merge_region_lines(ours, base, theirs, conflicts)


def merge_template_change(ours_text: str, base_text: str, theirs_text: str) -> tuple[str, int]:
    """Three-way merge of a project file against the template delta `base -> theirs`.

    Returns the merged text and the count of conflicting regions (where project lines are retained).
    """
    base, ours, theirs = (
        text.splitlines(keepends=True) for text in (base_text, ours_text, theirs_text)
    )
    merged: list[str] = []
    conflicts: list[int] = []
    base_pos = ours_pos = theirs_pos = 0
    for base_start, base_end, ours_start, ours_end, theirs_start, theirs_end in _sync_regions(
        base, ours, theirs
    ):
        merged.extend(
            _resolve_region(
                ours[ours_pos:ours_start],
                base[base_pos:base_start],
                theirs[theirs_pos:theirs_start],
                conflicts,
            )
        )
        merged.extend(ours[ours_start:ours_end])
        base_pos, ours_pos, theirs_pos = base_end, ours_end, theirs_end
    merged.extend(
        _resolve_region(ours[ours_pos:], base[base_pos:], theirs[theirs_pos:], conflicts)
    )
    return "".join(merged), len(conflicts)


def plan_template_delta(
    ours: str | None, theirs: str, origins: list[tuple[str, str]]
) -> tuple[str, str | None, str]:
    """Decide how to synchronize a template-derived project file.

    `origins` contains past committed versions of the template rendered for this project. A pure
    template version is moved directly to `theirs`; a customized file gets only the template delta
    through a three-way merge; unmergeable files are reported instead of overwritten.
    """
    if ours is None:
        return "create", theirs, ""
    if ours == theirs:
        return "unchanged", None, ""
    pure = [commit for commit, text in origins if text == ours]
    if pure:
        return "update", theirs, f"matched pure template {pure[0][:10]}"
    if not origins:
        return "no-history", None, "no template git history available to compare"
    commit, base = max(
        origins,
        key=lambda item: difflib.SequenceMatcher(
            None, ours.splitlines(), item[1].splitlines(), autojunk=False
        ).ratio(),
    )
    if base == theirs:
        return "preserved", None, "customized; template unchanged since origin"
    merged, conflicts = merge_template_change(ours, base, theirs)
    if conflicts:
        return (
            "conflict",
            None,
            f"{conflicts} conflicting region(s) diverged from template origin {commit[:10]}",
        )
    if merged == theirs:
        return "update", merged, f"customization already covered by template (origin {commit[:10]})"
    if merged == ours:
        return "preserved", None, "customized; template delta already present"
    return "merge", merged, f"customized; merged template delta since {commit[:10]}"


def _render_dockerfile(text: str, slug: str, proj_dir: Path) -> str:
    rendered = text.replace("{{project_id}}", slug)
    if not (proj_dir / "nginx" / "public").is_dir():
        rendered = (
            "\n".join(line for line in rendered.splitlines() if "nginx/public/" not in line) + "\n"
        )
    return rendered


def _diff_counts(old: str, new: str) -> tuple[int, int]:
    plus = minus = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            plus += 1
        elif line.startswith("-") and not line.startswith("---"):
            minus += 1
    return plus, minus


def _print_diff(old: str, new: str, path: Path, limit: int = 80) -> None:
    shown = 0
    for line in difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"{path.name} (current)",
        tofile=f"{path.name} (planned)",
        lineterm="",
        n=1,
    ):
        if shown >= limit:
            print(f"      [...] diff for {path.name} truncated at {limit} lines")
            return
        print(f"      {line}")
        shown += 1


def sync_projects(
    *,
    projects_dir: Path,
    server_env_path: Path,
    templates_dir: Path,
    selected_projects: list[str] | None = None,
    apply: bool = False,
    skip_compose_validate: bool = False,
    sync_nginx: bool = False,
    segregate_networks: bool = False,
    force_templates: bool = False,
    show_diff: bool = False,
    template_history: dict[str, list[tuple[str, str]]] | None = None,
) -> dict[str, str]:
    """Synchronize projects with current templates by applying only template deltas and SEC-11 hardening."""
    compose_template_path = templates_dir / "dockercomposetemplate"
    if not compose_template_path.is_file():
        raise RuntimeError(f"Compose template not found: {compose_template_path}")
    compose_template_text = compose_template_path.read_text(encoding="utf-8")

    full = bool(sync_nginx or segregate_networks)
    templates: dict[str, str] = {}
    if full:
        for name in REQUIRED_NGINX_SYNC_TEMPLATES:
            path = templates_dir / name
            if not path.is_file():
                raise RuntimeError(f"Template not found: {path}")
            templates[name] = path.read_text(encoding="utf-8")
        for name in OPTIONAL_SYNC_TEMPLATES:
            path = templates_dir / name
            if path.is_file():
                templates[name] = path.read_text(encoding="utf-8")

    history = (
        template_history if template_history is not None else load_template_history(templates_dir)
    )

    if apply and not skip_compose_validate and not server_env_path.is_file():
        raise RuntimeError(f"Server env file not found: {server_env_path}")

    server_env, _ = parse_env_file(server_env_path, allow_unreadable=not apply)
    projects = discover_projects(projects_dir, selected_projects)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    allocated_cidrs: set[str] = set()

    results: dict[str, str] = {}
    for proj_dir in projects:
        slug = proj_dir.name
        compose_path = proj_dir / "docker-compose.yml"
        env_path = proj_dir / ".env"
        if compose_path.is_symlink() or os.path.islink(env_path):
            raise RuntimeError(f"Refusing project with symlinked config: {slug}")

        try:
            proj_env, proj_readable = parse_env_file(env_path, allow_unreadable=not apply)
        except (OSError, RuntimeError, ValueError) as exc:
            results[slug] = "ERROR"
            print(f"{slug}: ERROR ({exc})")
            continue

        existing_env_bytes = env_path.read_bytes() if proj_readable else b""
        desired_env_bytes = existing_env_bytes
        if segregate_networks and proj_readable:
            subnet_allocator = _load_subnet_allocator(templates_dir)
            env_updates: dict[str, str] = {}
            subnet = proj_env.get("PROJECT_INTERNAL_SUBNET", "").strip()
            if not subnet:
                subnet = str(
                    subnet_allocator.allocate_project_internal_subnet(
                        slug,
                        projects_dir,
                        extra_used=allocated_cidrs,
                        inspect_docker=not skip_compose_validate,
                    )
                )
                env_updates["PROJECT_INTERNAL_SUBNET"] = subnet
                proj_env["PROJECT_INTERNAL_SUBNET"] = subnet
            allocated_cidrs.add(subnet)
            if env_updates:
                desired_env_bytes = _upsert_env_text(
                    existing_env_bytes.decode("utf-8"), env_updates
                ).encode("utf-8")

        try:
            existing_compose_bytes = compose_path.read_bytes()
        except OSError as exc:
            results[slug] = "ERROR"
            print(f"{slug}: ERROR (docker-compose.yml: {exc.strerror}; run with read permission)")
            continue

        existing_compose_text = existing_compose_bytes.decode("utf-8")
        compose_status, compose_base, compose_note = "preserved", existing_compose_text, ""
        if full:
            compose_origins = [
                (commit, text.replace("{{project_id}}", slug))
                for commit, text in history.get("dockercomposetemplate", [])
            ]
            compose_status, merged, compose_note = plan_template_delta(
                existing_compose_text,
                compose_template_text.replace("{{project_id}}", slug),
                compose_origins,
            )
            if merged is not None and compose_status in {"update", "merge"}:
                compose_base = merged

        desired_compose_text = render_project_compose(
            compose_template_text,
            slug,
            compose_base,
            server_env,
            proj_env,
            proj_env_readable=proj_readable,
            segregate_networks=segregate_networks,
        )
        desired_compose_bytes = desired_compose_text.encode("utf-8")
        compose_blocked = compose_status in COMPOSE_BLOCKING
        if compose_blocked:
            compose_note = f"{compose_note}; only surgical security keys were applied"

        # (path, relative_name, status, current_bytes, final_bytes, mode, note)
        rows: list[tuple[Path, str, str, bytes | None, bytes | None, int, str]] = []
        if desired_env_bytes != existing_env_bytes:
            plus, minus = _diff_counts(
                existing_env_bytes.decode("utf-8"), desired_env_bytes.decode("utf-8")
            )
            rows.append(
                (
                    env_path,
                    ".env",
                    f"edited (+{plus} -{minus})",
                    existing_env_bytes,
                    desired_env_bytes,
                    env_path.stat().st_mode & 0o777,
                    "",
                )
            )
        if desired_compose_bytes != existing_compose_bytes or compose_blocked:
            plus, minus = _diff_counts(existing_compose_text, desired_compose_text)
            if compose_status in {"unchanged", "preserved"}:
                compose_status = "edited"
            rows.append(
                (
                    compose_path,
                    "docker-compose.yml",
                    f"{compose_status} (+{plus} -{minus})",
                    existing_compose_bytes,
                    desired_compose_bytes,
                    compose_path.stat().st_mode & 0o777,
                    compose_note,
                )
            )

        if full:
            nginx_dir = proj_dir / "nginx"
            nginx_path = nginx_dir / f"nginx_{slug}.conf"
            keys_path = nginx_dir / "keys.conf.template"
            stream_path = nginx_dir / "pooler.stream-template"
            dockerfile_path = proj_dir / "Dockerfile"
            for guarded in (nginx_path, keys_path, stream_path, dockerfile_path):
                if guarded.is_symlink():
                    raise RuntimeError(f"Refusing symlinked project file for {slug}: {guarded.name}")

            def plan(
                path: Path, theirs: str, origins: list[tuple[str, str]], create: bool = False
            ) -> None:
                ours = path.read_bytes().decode("utf-8") if path.is_file() else None
                if ours is None and not create:
                    return
                status, new, note = plan_template_delta(ours, theirs, origins)
                if status in FORCEABLE and force_templates:
                    status, new, note = (
                        "replaced",
                        theirs,
                        f"{note}; replaced from current template (--force)",
                    )
                current = path.read_bytes() if path.is_file() else None
                final = current if new is None else new.encode("utf-8")
                if final == current and status not in NEEDS_REVIEW:
                    status = "unchanged" if ours == theirs else "preserved"
                mode = (path.stat().st_mode & 0o777) if path.is_file() else 0o644
                rows.append((path, str(path.relative_to(proj_dir)), status, current, final, mode, note))

            nginx_origins: list[tuple[str, str]] = []
            for commit, text in history.get("nginxtemplate", []):
                try:
                    nginx_origins.append((commit, render_project_nginx(text, slug, server_env, proj_env)))
                except RuntimeError:
                    continue

            if nginx_path.is_file():
                try:
                    rendered_nginx = render_project_nginx(
                        templates["nginxtemplate"], slug, server_env, proj_env
                    )
                except RuntimeError as exc:
                    current = nginx_path.read_bytes()
                    rows.append(
                        (
                            nginx_path,
                            str(nginx_path.relative_to(proj_dir)),
                            "missing-data",
                            current,
                            current,
                            nginx_path.stat().st_mode & 0o777,
                            str(exc),
                        )
                    )
                else:
                    plan(nginx_path, rendered_nginx, nginx_origins)

            if "keys.conf.template" in templates and keys_path.is_file():
                plan(
                    keys_path,
                    templates["keys.conf.template"],
                    history.get("keys.conf.template", []),
                )
            if segregate_networks and "pooler.stream-template" in templates and nginx_dir.is_dir():
                plan(
                    stream_path,
                    templates["pooler.stream-template"],
                    history.get("pooler.stream-template", []),
                    create=True,
                )
            if dockerfile_path.is_file():
                dockerfile_origins = [
                    (commit, _render_dockerfile(text, slug, proj_dir))
                    for commit, text in history.get("Dockerfile", [])
                ]
                plan(
                    dockerfile_path,
                    _render_dockerfile(templates["Dockerfile"], slug, proj_dir),
                    dockerfile_origins,
                )

        review = [row for row in rows if row[2] in NEEDS_REVIEW]
        writes = [row for row in rows if row[4] != row[3]]
        if review:
            results[slug] = "NEEDS_REVIEW"
        elif compose_blocked:
            results[slug] = "NEEDS_MERGE"
        elif not writes:
            results[slug] = "UP_TO_DATE"
        else:
            results[slug] = "UPDATED" if apply else "NEEDS_UPDATE"

        print(f"{slug}: {results[slug]}")
        for path, name, status, old, new, _mode, note in rows:
            print(f"   {name:<36} {status}" + (f"  ({note})" if note else ""))
            if show_diff and new is not None and new != old:
                _print_diff((old or b"").decode("utf-8"), new.decode("utf-8"), path)
        if review:
            cause = (
                "missing or unreadable .env values (PROJECT_UUID/PROJECT_PUBLIC_REF/SERVER_URL)"
                if any(row[2] == "missing-data" for row in review)
                else "resolve conflicts or rerun with --force"
            )
            print(f"   no files written for {slug}: {cause}")
        elif compose_blocked:
            print(f"   {slug}: docker-compose.yml needs manual merge; security keys were still applied")
        if not apply or not writes or review:
            continue

        # Validate candidate docker-compose.yml BEFORE modifying live files.
        fd, candidate_name = tempfile.mkstemp(
            prefix=".docker-compose.candidate.", suffix=".yml", dir=proj_dir
        )
        candidate_path = Path(candidate_name)
        env_candidate_path: Path | None = None
        try:
            with os.fdopen(fd, "wb") as handle:
                os.fchmod(handle.fileno(), 0o644)
                handle.write(desired_compose_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            validation_env_path = env_path
            if desired_env_bytes != existing_env_bytes:
                efd, e_name = tempfile.mkstemp(prefix=".env.candidate.", dir=proj_dir)
                env_candidate_path = Path(e_name)
                with os.fdopen(efd, "wb") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(desired_env_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                validation_env_path = env_candidate_path
            if not skip_compose_validate:
                validate_compose_candidate(
                    proj_dir, slug, server_env_path, validation_env_path, candidate_path
                )
        finally:
            candidate_path.unlink(missing_ok=True)
            if env_candidate_path is not None:
                env_candidate_path.unlink(missing_ok=True)

        written_targets: list[tuple[Path, bytes | None, int]] = []
        try:
            for target, _name, _status, old_bytes, new_bytes, mode, _note in writes:
                assert new_bytes is not None
                if old_bytes is not None:
                    backup_path = target.with_name(f"{target.name}.bak.{timestamp}")
                    atomic_write_bytes(backup_path, old_bytes, 0o600)
                atomic_write_bytes(target, new_bytes, mode)
                written_targets.append((target, old_bytes, mode))
        except Exception:
            for target, old_bytes, mode in reversed(written_targets):
                if old_bytes is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(target, old_bytes, mode)
            raise

        print(f"{slug}: UPDATED (backup .bak.{timestamp})")

    updated = sum(1 for status in results.values() if status == "UPDATED")
    errors = sum(1 for status in results.values() if status == "ERROR")
    needs_update = sum(1 for status in results.values() if status == "NEEDS_UPDATE")
    up_to_date = sum(1 for status in results.values() if status == "UP_TO_DATE")
    needs_review = sum(1 for status in results.values() if status == "NEEDS_REVIEW")
    needs_merge = sum(1 for status in results.values() if status == "NEEDS_MERGE")
    print(
        f"Summary: total={len(results)} updated={updated} needs_update={needs_update} "
        f"up_to_date={up_to_date} needs_review={needs_review} needs_merge={needs_merge} error={errors}"
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize existing project configurations (docker-compose.yml, .env, nginx, Dockerfile, "
            "and optional keys/stream templates) with current templates using surgical edits and three-way merges."
        )
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=DEFAULT_PROJECTS_DIR,
        help="Path to projects directory (default: <repo>/servidor/projects)",
    )
    parser.add_argument(
        "--server-env",
        type=Path,
        default=DEFAULT_SERVER_ENV,
        help="Path to server .env file (default: <repo>/servidor/.env)",
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=DEFAULT_TEMPLATES_DIR,
        help="Path to generateProject templates directory",
    )
    parser.add_argument(
        "--project",
        action="append",
        dest="projects",
        help="Project slug filter (repeatable)",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change in each project without modifying files (default)",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Back up, validate, and atomically update project files",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print the unified diff of every file that would change",
    )
    parser.add_argument(
        "--force",
        dest="force_templates",
        action="store_true",
        help=(
            "Replace project files reported as conflict/no-history with the rendered template "
            "(a mode-0600 backup is kept); without it a project in that state is left untouched"
        ),
    )
    parser.add_argument(
        "--skip-compose-validate",
        action="store_true",
        help="Skip `docker compose config -q` validation (for unit tests without Docker)",
    )
    parser.add_argument(
        "--compose-only",
        action="store_true",
        help="Only harden docker-compose.yml and .env; leave nginx and Dockerfile untouched",
    )
    parser.add_argument(
        "--sync-nginx",
        action="store_true",
        help="Synchronize nginx and template files (enabled by default unless --compose-only is set)",
    )
    parser.add_argument(
        "--segregate-networks",
        action="store_true",
        help="Apply SEC-11 project-gateways and per-project network segregation (enabled by default unless --compose-only is set)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    full = not args.compose_only
    try:
        results = sync_projects(
            projects_dir=args.projects_dir.resolve(),
            server_env_path=args.server_env.resolve(),
            templates_dir=args.templates_dir.resolve(),
            selected_projects=args.projects,
            apply=bool(args.apply),
            skip_compose_validate=bool(args.skip_compose_validate),
            sync_nginx=bool(args.sync_nginx or full),
            segregate_networks=bool(args.segregate_networks or full),
            force_templates=bool(args.force_templates),
            show_diff=bool(args.diff),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if any(status in {"NEEDS_REVIEW", "NEEDS_MERGE", "ERROR"} for status in results.values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
