#!/usr/bin/env python3
"""Filter internal guard EVENT TRIGGER entries out of PostgreSQL dumps.

`pg_dump --exclude-schema=studio_vector_fdw_guard` excludes the guard schema
and its functions, but PostgreSQL EVENT TRIGGER objects are database-global
(not schema-scoped) and are still emitted into `post-data`. Restoring that dump
into a fresh clone or restored database fails with:

    ERROR: schema "studio_vector_fdw_guard" does not exist

This helper strips excluded internal guard event triggers from:
- `pg_restore -l` TOC lists (`toc` mode), for custom-format archives (`-Fc`),
- plain-SQL `pg_dump` streams (`sql` mode), for `-Fp` / `schema-only` /
  `with-data` / backup dumps, while preserving `COPY ... FROM stdin;` payloads,
  dollar-quoted / single-quoted literals, and all user-defined event triggers.

Right after clone/restore completes, `provision_tenant_meta_role` recreates
`studio_vector_fdw_guard` and `studio_vector_fdw_enforce_server_endpoint` with
the destination tenant's own UUID, HMAC key, and pinned FDW endpoint.
"""
from __future__ import annotations

import io
import re
import sys
from typing import TextIO

EXCLUDED_EVENT_TRIGGERS: frozenset[str] = frozenset(
    {
        "studio_vector_fdw_enforce_server_endpoint",
    }
)

_TOC_EVENT_TRIGGER_RE = re.compile(
    r"^\d+;\s+\d+\s+\d+\s+"
    r"(?:EVENT TRIGGER\s+-\s+|COMMENT\s+-\s+EVENT TRIGGER\s+)"
    r'(?:"([^"]+)"|([^\s]+))(?:\s|$)'
)

_SQL_EVENT_TRIGGER_STMT_RE = re.compile(
    r"^\s*(?:CREATE|ALTER|COMMENT\s+ON)\s+EVENT\s+TRIGGER\s+"
    r'(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_$]*)\b)',
    re.IGNORECASE,
)

_COPY_STDIN_RE = re.compile(r"^COPY\s+.+\s+FROM\s+stdin;\s*$", re.IGNORECASE)
_DOLLAR_TAG_RE = re.compile(r"^\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def is_excluded_toc_line(
    line: str,
    excluded: frozenset[str] = EXCLUDED_EVENT_TRIGGERS,
) -> bool:
    """Return True if a `pg_restore -l` TOC line belongs to an excluded trigger."""
    match = _TOC_EVENT_TRIGGER_RE.match(line)
    if not match:
        return False
    name = match.group(1) or match.group(2)
    return name in excluded


def filter_toc(
    source: TextIO,
    destination: TextIO,
    excluded: frozenset[str] = EXCLUDED_EVENT_TRIGGERS,
) -> int:
    """Copy a `pg_restore -l` TOC list, dropping excluded event trigger entries."""
    removed = 0
    for line in source:
        if is_excluded_toc_line(line, excluded):
            removed += 1
            continue
        destination.write(line)
    return removed


class _SqlLexState:
    __slots__ = (
        "in_single_quote",
        "in_escape_string",
        "in_double_quote",
        "dollar_tag",
        "block_comment_depth",
    )

    def __init__(self) -> None:
        self.in_single_quote = False
        self.in_escape_string = False
        self.in_double_quote = False
        self.dollar_tag: str | None = None
        self.block_comment_depth = 0

    @property
    def at_top_level(self) -> bool:
        return (
            not self.in_single_quote
            and not self.in_double_quote
            and self.dollar_tag is None
            and self.block_comment_depth == 0
        )


def _advance_sql_line(
    line: str,
    state: _SqlLexState,
    *,
    stop_at_semicolon: bool = False,
) -> int | None:
    """Advance PostgreSQL lexical state over `line`.

    When `stop_at_semicolon` is True, stops immediately upon seeing a top-level
    `;` and returns its character index; otherwise scans the whole line and
    returns None.
    """
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if state.in_single_quote:
            if state.in_escape_string and ch == "\\":
                i += 2
                continue
            if ch == "'":
                if i + 1 < n and line[i + 1] == "'":
                    i += 2
                    continue
                state.in_single_quote = False
                state.in_escape_string = False
            i += 1
            continue

        if state.in_double_quote:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    i += 2
                    continue
                state.in_double_quote = False
            i += 1
            continue

        if state.dollar_tag is not None:
            if ch == "$" and line.startswith(state.dollar_tag, i):
                i += len(state.dollar_tag)
                state.dollar_tag = None
                continue
            i += 1
            continue

        if state.block_comment_depth > 0:
            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                state.block_comment_depth += 1
                i += 2
                continue
            if ch == "*" and i + 1 < n and line[i + 1] == "/":
                state.block_comment_depth -= 1
                i += 2
                continue
            i += 1
            continue

        # Top-level SQL
        if ch == "-" and i + 1 < n and line[i + 1] == "-":
            break
        if ch == "/" and i + 1 < n and line[i + 1] == "*":
            state.block_comment_depth = 1
            i += 2
            continue
        if ch == "'":
            is_escape = (
                i > 0
                and line[i - 1] in ("e", "E")
                and (i == 1 or not (line[i - 2].isalnum() or line[i - 2] in "_$"))
            )
            state.in_single_quote = True
            state.in_escape_string = is_escape
            i += 1
            continue
        if ch == '"':
            state.in_double_quote = True
            i += 1
            continue
        if ch == "$" and (i == 0 or not (line[i - 1].isalnum() or line[i - 1] in "_$")):
            tag_match = _DOLLAR_TAG_RE.match(line[i:])
            if tag_match:
                state.dollar_tag = tag_match.group(0)
                i += len(state.dollar_tag)
                continue
        if ch == ";" and stop_at_semicolon:
            return i
        i += 1
    return None


def filter_plain_sql(
    source: TextIO,
    destination: TextIO,
    excluded: frozenset[str] = EXCLUDED_EVENT_TRIGGERS,
) -> int:
    """Stream a plain-SQL `pg_dump`, dropping excluded event trigger DDL."""
    state = _SqlLexState()
    in_copy_data = False
    skipping_stmt = False
    removed = 0

    for line in source:
        if in_copy_data:
            destination.write(line)
            if line.rstrip("\r\n") == r"\.":
                in_copy_data = False
            continue

        if skipping_stmt:
            semi = _advance_sql_line(line, state, stop_at_semicolon=True)
            if semi is None:
                continue
            skipping_stmt = False
            remainder = line[semi + 1 :]
            if remainder.strip():
                _advance_sql_line(remainder, state)
                destination.write(remainder)
            continue

        if state.at_top_level:
            if _COPY_STDIN_RE.match(line):
                destination.write(line)
                in_copy_data = True
                continue
            match = _SQL_EVENT_TRIGGER_STMT_RE.match(line)
            if match:
                name = match.group(1) or match.group(2)
                if name in excluded:
                    removed += 1
                    semi = _advance_sql_line(line, state, stop_at_semicolon=True)
                    if semi is None:
                        skipping_stmt = True
                    else:
                        remainder = line[semi + 1 :]
                        if remainder.strip():
                            _advance_sql_line(remainder, state)
                            destination.write(remainder)
                    continue

        _advance_sql_line(line, state)
        destination.write(line)

    return removed


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ("toc", "sql"):
        sys.stderr.write("Usage: pg_dump_filter.py <toc|sql>\n")
        return 2

    reader = io.TextIOWrapper(
        sys.stdin.buffer,
        encoding="utf-8",
        errors="surrogateescape",
        newline="",
    )
    writer = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="surrogateescape",
        newline="",
    )
    try:
        if args[0] == "toc":
            filter_toc(reader, writer)
        else:
            filter_plain_sql(reader, writer)
        writer.flush()
    finally:
        reader.detach()
        writer.detach()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
