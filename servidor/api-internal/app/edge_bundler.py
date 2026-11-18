"""Validated npm/JSR dependency analysis and HTTP RPC client for offline ESZIP bundling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import PurePosixPath
import re
import time
from urllib.parse import unquote, urlsplit

import httpx

MAX_FILES = 128
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
    r"""(?:^|[;\r\n\u2028\u2029}])\s*(?:import\s*(?:(?:type\s+)?(?:[\w$*,\s{}]*?)\bfrom\s*)?|export\s*(?:type\b\s*)?(?:\*(?:\s*as\s+[\w$]+)?|\{[^}]*\})\s*from\s*)(['"])((?:\\.|(?!\1)[^\r\n\u2028\u2029])*)\1""",
    re.MULTILINE,
)
DYNAMIC_IMPORT_RE = re.compile(
    r"""(?<![.\w$])import\s*\(\s*(['"`])((?:\\.|(?!\1)[\s\S])*)\1\s*(?:,|\))"""
)

REGISTRY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
NPM_SCOPE_RE = re.compile(r"^@[a-z0-9][a-z0-9._-]{0,127}$")
PUBLIC_HOSTNAME_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
PRIVATE_HOSTNAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")
PEM_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----\s+([A-Za-z0-9+/=\s]+?)\s+-----END CERTIFICATE-----")

_JS_LINE_TERMS = ("\n", "\r", "\u2028", "\u2029")
_REGEX_PRECEDING_KEYWORDS = frozenset({
    "return", "throw", "case", "delete", "void", "typeof",
    "instanceof", "in", "of", "new", "yield", "await", "else", "do",
})
_METHOD_MODIFIERS = frozenset({
    "async", "static", "public", "private", "protected",
    "readonly", "override", "abstract", "get", "set",
})
_JSX_CLOSE_TAG_RE = re.compile(r"/(?:[A-Za-z_$][A-Za-z0-9_$.:-]*)?\s*>")
_MULTI_CHAR_OPS = (
    ">>>=", "===", "!==", ">>>", "<<=", ">>=", "**=", "&&=", "||=", "??=",
    "...", "=>", "?.", "++", "--", "==", "!=", "<=", ">=", "&&", "||",
    "??", "**", "<<", ">>", "+=", "-=", "*=", "%=", "&=", "|=", "^=",
)


class DependencyPolicyError(ValueError):
    """Raised when a function or registry configuration violates security policy."""


PolicyViolationError = DependencyPolicyError


class BundleBuildError(RuntimeError):
    """Raised when offline-safe ESZIP compilation fails."""


def _scan_regex_literal(source: str, start: int) -> int | None:
    """Scan a JS/TS RegExp literal starting at '/' or return None if not a single-line regex."""
    n = len(source)
    j = start + 1
    if j >= n or source[j] in ("/", "*", *_JS_LINE_TERMS):
        return None
    in_class = False
    while j < n:
        ch = source[j]
        if ch in _JS_LINE_TERMS:
            return None
        if ch == "\\":
            if j + 1 >= n or source[j + 1] in _JS_LINE_TERMS:
                return None
            j += 2
            continue
        if ch == "[":
            in_class = True
            j += 1
            continue
        if ch == "]" and in_class:
            in_class = False
            j += 1
            continue
        if ch == "/" and not in_class:
            j += 1
            while j < n and (source[j].isalnum() or source[j] in ("_", "$")):
                j += 1
            return j
        j += 1
    return None


def _scan_template_chunk(source: str, start: int, pos: int) -> tuple[str, str, int]:
    """Scan template text until closing backtick or '${' substitution start."""
    n = len(source)
    i = pos
    while i < n:
        cur = source[i]
        if cur == "\\":
            if i + 1 < n:
                if source[i + 1] == "\r" and i + 2 < n and source[i + 2] == "\n":
                    i += 3
                else:
                    i += 2
            else:
                i += 1
            continue
        if cur == "`":
            i += 1
            return "closed", source[start:i], i
        if cur == "$" and i + 1 < n and source[i + 1] == "{":
            i += 2
            return "subst", source[start:i], i
        i += 1
    return "eof", source[start:i], i


def _lex_js(source: str) -> list[tuple[str, str]]:
    """Tokenize JS/TS source, tracking comments, strings, regexes, and nested template literals."""
    tokens: list[tuple[str, str]] = []
    n = len(source)
    i = 0
    expr_allowed = True
    pending_ctrl_paren = False
    last_sig_kind = ""
    last_sig_val = ""
    paren_stack: list[bool] = []
    brace_stack: list[str] = []

    while i < n:
        ch = source[i]
        if i == 0 and source.startswith("#!"):
            i = 2
            while i < n and source[i] not in _JS_LINE_TERMS:
                i += 1
            tokens.append(("comment_line", source[:i]))
            continue
        if ch in _JS_LINE_TERMS:
            if ch == "\r" and i + 1 < n and source[i + 1] == "\n":
                tokens.append(("nl", "\r\n"))
                i += 2
            else:
                tokens.append(("nl", ch))
                i += 1
            continue
        if ch.isspace() or ch == "\ufeff":
            start = i
            i += 1
            while i < n and source[i] not in _JS_LINE_TERMS and (source[i].isspace() or source[i] == "\ufeff"):
                i += 1
            tokens.append(("ws", source[start:i]))
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            start = i
            i += 2
            while i < n and source[i] not in _JS_LINE_TERMS:
                i += 1
            tokens.append(("comment_line", source[start:i]))
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            tokens.append(("comment_block", source[start:i]))
            continue
        if ch in ("'", '"'):
            quote = ch
            start = i
            i += 1
            while i < n:
                cur = source[i]
                if cur == "\\":
                    if i + 1 < n:
                        if source[i + 1] == "\r" and i + 2 < n and source[i + 2] == "\n":
                            i += 3
                        else:
                            i += 2
                    else:
                        i += 1
                    continue
                if cur == quote:
                    i += 1
                    break
                if cur in _JS_LINE_TERMS:
                    break
                i += 1
            lit = source[start:i]
            tokens.append(("string", lit))
            expr_allowed = False
            pending_ctrl_paren = False
            last_sig_kind = "string"
            last_sig_val = lit
            continue
        if ch == "`":
            mode, chunk, i = _scan_template_chunk(source, i, i + 1)
            if mode == "subst":
                tokens.append(("template_head", chunk))
                brace_stack.append("template")
                expr_allowed = True
                pending_ctrl_paren = False
                last_sig_kind = "template_head"
                last_sig_val = "${"
            else:
                tokens.append(("template_nosub", chunk))
                expr_allowed = False
                pending_ctrl_paren = False
                last_sig_kind = "template_nosub"
                last_sig_val = chunk
            continue
        if ch == "}":
            ctx = brace_stack.pop() if brace_stack else "block"
            if ctx == "template":
                mode, chunk, i = _scan_template_chunk(source, i, i + 1)
                if mode == "subst":
                    tokens.append(("template_middle", chunk))
                    brace_stack.append("template")
                    expr_allowed = True
                    pending_ctrl_paren = False
                    last_sig_kind = "template_middle"
                    last_sig_val = "${"
                else:
                    tokens.append(("template_tail", chunk))
                    expr_allowed = False
                    pending_ctrl_paren = False
                    last_sig_kind = "template_tail"
                    last_sig_val = chunk
            else:
                tokens.append(("punct", "}"))
                i += 1
                expr_allowed = ctx == "block"
                pending_ctrl_paren = False
                last_sig_kind = "punct"
                last_sig_val = "}"
            continue
        if ch == "{":
            is_obj = (
                expr_allowed
                and bool(last_sig_kind)
                and last_sig_val not in {"}", ";", ")", "=>", "else", "do", "try", "finally"}
            )
            brace_stack.append("obj" if is_obj else "block")
            tokens.append(("punct", "{"))
            i += 1
            expr_allowed = True
            pending_ctrl_paren = False
            last_sig_kind = "punct"
            last_sig_val = "{"
            continue
        if ch == "(":
            paren_stack.append(pending_ctrl_paren)
            pending_ctrl_paren = False
            tokens.append(("punct", "("))
            i += 1
            expr_allowed = True
            last_sig_kind = "punct"
            last_sig_val = "("
            continue
        if ch == ")":
            is_ctrl = paren_stack.pop() if paren_stack else False
            tokens.append(("punct", ")"))
            i += 1
            expr_allowed = is_ctrl
            pending_ctrl_paren = False
            last_sig_kind = "punct"
            last_sig_val = ")"
            continue
        if ch == "/":
            if expr_allowed and not (i > 0 and source[i - 1] == "<" and _JSX_CLOSE_TAG_RE.match(source, i)):
                end_re = _scan_regex_literal(source, i)
                if end_re is not None:
                    tokens.append(("regex", source[i:end_re]))
                    i = end_re
                    expr_allowed = False
                    pending_ctrl_paren = False
                    last_sig_kind = "regex"
                    last_sig_val = "/re/"
                    continue
            op = "/=" if (i + 1 < n and source[i + 1] == "=") else "/"
            tokens.append(("punct", op))
            i += len(op)
            expr_allowed = True
            pending_ctrl_paren = False
            last_sig_kind = "punct"
            last_sig_val = op
            continue
        if ch.isalpha() or ch in ("_", "$") or (
            ch == "#" and i + 1 < n and (source[i + 1].isalpha() or source[i + 1] in ("_", "$"))
        ):
            start = i
            i += 1
            while i < n and (source[i].isalnum() or source[i] in ("_", "$")):
                i += 1
            ident = source[start:i]
            tokens.append(("ident", ident))
            if last_sig_kind == "punct" and last_sig_val in {".", "?."}:
                expr_allowed = False
                pending_ctrl_paren = False
            elif ident in {"if", "while", "for", "with"}:
                pending_ctrl_paren = True
                expr_allowed = False
            elif ident == "await" and last_sig_val == "for":
                pending_ctrl_paren = True
                expr_allowed = True
            else:
                pending_ctrl_paren = False
                expr_allowed = ident in _REGEX_PRECEDING_KEYWORDS
            last_sig_kind = "ident"
            last_sig_val = ident
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            start = i
            i += 1
            while i < n and (source[i].isalnum() or source[i] in ("_", ".")):
                if source[i] in ("e", "E") and i + 1 < n and source[i + 1] in ("+", "-"):
                    i += 2
                    continue
                i += 1
            num = source[start:i]
            tokens.append(("number", num))
            expr_allowed = False
            pending_ctrl_paren = False
            last_sig_kind = "number"
            last_sig_val = num
            continue

        matched_op = ""
        for candidate in _MULTI_CHAR_OPS:
            if source.startswith(candidate, i):
                matched_op = candidate
                break
        if matched_op:
            tokens.append(("punct", matched_op))
            i += len(matched_op)
            if matched_op in {"?.", "++", "--"}:
                expr_allowed = False
            else:
                expr_allowed = True
            pending_ctrl_paren = False
            last_sig_kind = "punct"
            last_sig_val = matched_op
            continue

        tokens.append(("punct", ch))
        i += 1
        if ch in {"]", "."}:
            expr_allowed = False
        elif ch == "!":
            expr_allowed = bool(expr_allowed)
        else:
            expr_allowed = True
        pending_ctrl_paren = False
        last_sig_kind = "punct"
        last_sig_val = ch

    return tokens


def _strip_js_comments(source: str) -> str:
    """Strip JS/TS comments while preserving quoted, regex, and template string literals."""
    out: list[str] = []
    for kind, val in _lex_js(source):
        if kind == "comment_line":
            continue
        if kind == "comment_block":
            out.append("\n" if any(ch in val for ch in _JS_LINE_TERMS) else " ")
            continue
        if kind == "nl":
            out.append("\n")
            continue
        out.append(val)
    return "".join(out)


def _decode_js_string_literal(token_text: str, source_name: str = "<source>") -> str:
    if len(token_text) < 2 or token_text[0] not in ("'", '"') or token_text[-1] != token_text[0]:
        raise DependencyPolicyError(f"Unterminated string literal in import in {source_name}")
    inner = token_text[1:-1]
    if "\\" not in inner:
        return inner
    out: list[str] = []
    i = 0
    n = len(inner)
    simple_escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
    while i < n:
        ch = inner[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= n:
            raise DependencyPolicyError(f"Invalid escape sequence in import specifier in {source_name}")
        esc = inner[i]
        if esc == "\r" and i + 1 < n and inner[i + 1] == "\n":
            i += 2
            continue
        if esc in _JS_LINE_TERMS:
            i += 1
            continue
        if esc in simple_escapes:
            out.append(simple_escapes[esc])
            i += 1
            continue
        if esc == "0":
            if i + 1 < n and inner[i + 1].isdigit():
                raise DependencyPolicyError(f"Invalid octal escape in import specifier in {source_name}")
            out.append("\0")
            i += 1
            continue
        if esc == "x":
            hex_part = inner[i + 1:i + 3]
            if len(hex_part) != 2 or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
                raise DependencyPolicyError(f"Invalid hex escape in import specifier in {source_name}")
            out.append(chr(int(hex_part, 16)))
            i += 3
            continue
        if esc == "u":
            if i + 1 < n and inner[i + 1] == "{":
                end_brace = inner.find("}", i + 2)
                hex_part = inner[i + 2:end_brace] if end_brace != -1 else ""
                if not (1 <= len(hex_part) <= 6) or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    raise DependencyPolicyError(f"Invalid unicode escape in import specifier in {source_name}")
                cp = int(hex_part, 16)
                if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
                    raise DependencyPolicyError(f"Invalid unicode code point in import specifier in {source_name}")
                out.append(chr(cp))
                i = end_brace + 1
                continue
            hex_part = inner[i + 1:i + 5]
            if len(hex_part) != 4 or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
                raise DependencyPolicyError(f"Invalid unicode escape in import specifier in {source_name}")
            cp = int(hex_part, 16)
            if 0xD800 <= cp <= 0xDFFF:
                raise DependencyPolicyError(f"Invalid surrogate escape in import specifier in {source_name}")
            out.append(chr(cp))
            i += 5
            continue
        if esc.isdigit():
            raise DependencyPolicyError(f"Invalid numeric escape in import specifier in {source_name}")
        out.append(esc)
        i += 1
    return "".join(out)


def _validate_relative_import(spec: str, source_name: str) -> None:
    if "?" in spec or "#" in spec or "\0" in spec or "\\" in spec or "%" in spec:
        raise DependencyPolicyError(f"Unsupported query, fragment, or encoding in local import '{spec}' ({source_name})")
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
    if depth <= 0:
        raise DependencyPolicyError(f"Local import '{spec}' in {source_name} must reference a file inside function directory")


def _validate_specifier(spec: str, source_name: str) -> str | None:
    """Validate an import specifier and return 'npm', 'jsr', or None."""
    if (
        not isinstance(spec, str)
        or not spec
        or "\\" in spec
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in spec)
    ):
        raise DependencyPolicyError(f"Invalid import specifier in {source_name}")
    unquoted = unquote(spec)
    if unquoted != spec and (
        spec.startswith(("/", "./", "../"))
        or unquoted.startswith(("/", "./", "../"))
        or unquoted in {".", ".."}
        or "\\" in unquoted
        or ".." in PurePosixPath(unquoted).parts
        or SCHEME_RE.match(unquoted)
    ):
        raise DependencyPolicyError(f"Disallowed percent-encoded import specifier '{spec}' in {source_name}")
    if spec.startswith("/"):
        raise DependencyPolicyError(f"Absolute path import '{spec}' is not allowed in {source_name}")
    if spec in {".", ".."} or spec.startswith(("./", "../")):
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
            if not NODE_SPEC_RE.fullmatch(spec) or ".." in PurePosixPath(spec[5:]).parts:
                raise DependencyPolicyError(f"Invalid node specifier '{spec}' in {source_name}")
            return None
        raise DependencyPolicyError(
            f"Disallowed import scheme '{spec}' in {source_name}; use local files, 'npm:', 'jsr:', or 'node:'"
        )
    if ".." in PurePosixPath(spec).parts:
        raise DependencyPolicyError(f"Invalid traversal segment in import specifier '{spec}' in {source_name}")
    return None


def _is_method_or_signature_decl(sig: list[tuple[str, str]], kw_idx: int, open_paren_idx: int) -> bool:
    """Return True when '<kw>(...)' is a function/object/class/interface method declaration."""
    if kw_idx > 0 and sig[kw_idx - 1] == ("ident", "function"):
        return True
    if kw_idx == 0:
        return False
    pk, pv = sig[kw_idx - 1]
    if not (
        (pk == "punct" and pv in {"{", ",", ";", "*"})
        or (pk == "ident" and pv in _METHOD_MODIFIERS)
    ):
        return False
    m = len(sig)
    depth = 1
    close_idx = open_paren_idx + 1
    while close_idx < m and depth > 0:
        if sig[close_idx] == ("punct", "("):
            depth += 1
        elif sig[close_idx] == ("punct", ")"):
            depth -= 1
        close_idx += 1
    if depth != 0:
        return False
    close_idx -= 1
    if close_idx == open_paren_idx + 1:
        return close_idx + 1 < m and sig[close_idx + 1][0] == "punct" and sig[close_idx + 1][1] in {"{", ":"}
    first_k, _ = sig[open_paren_idx + 1]
    if first_k != "ident" and sig[open_paren_idx + 1] != ("punct", "..."):
        return False
    if (
        open_paren_idx + 2 < close_idx
        and sig[open_paren_idx + 1][0] == "ident"
        and (
            sig[open_paren_idx + 2] == ("punct", ":")
            or (
                sig[open_paren_idx + 2] == ("punct", "?")
                and open_paren_idx + 3 < close_idx
                and sig[open_paren_idx + 3] == ("punct", ":")
            )
        )
    ):
        return True
    return close_idx + 1 < m and sig[close_idx + 1] == ("punct", "{")


def _extract_source_specifiers(source: str, source_name: str = "<source>") -> list[str]:
    sig = [
        (kind, val)
        for kind, val in _lex_js(source)
        if kind not in {"ws", "nl", "comment_line", "comment_block"}
    ]
    specs: list[str] = []
    m = len(sig)
    is_cjs = PurePosixPath(source_name).suffix.lower() in {".cjs", ".cts"}
    idx = 0

    while idx < m:
        kind, val = sig[idx]
        is_member = idx > 0 and sig[idx - 1][0] == "punct" and sig[idx - 1][1] in {".", "?."}
        is_alias = idx > 0 and sig[idx - 1] == ("ident", "as")

        if kind == "ident" and val == "import" and not is_member and not is_alias:
            if idx + 1 >= m:
                raise DependencyPolicyError(f"Incomplete import statement in {source_name}")
            nk, nv = sig[idx + 1]
            if nk == "punct" and nv in {".", ":", "?", ",", "}"}:
                idx += 1
                continue
            if nk == "punct" and nv == "(":
                if _is_method_or_signature_decl(sig, idx, idx + 1):
                    idx += 1
                    continue
                if (
                    idx + 3 < m
                    and sig[idx + 2][0] == "string"
                    and sig[idx + 3] in {("punct", ")"), ("punct", ",")}
                ):
                    specs.append(_decode_js_string_literal(sig[idx + 2][1], source_name))
                    idx += 3
                    continue
                raise DependencyPolicyError(
                    f"Dynamic import() requires a static string literal specifier in {source_name}"
                )
            if nk == "string":
                specs.append(_decode_js_string_literal(nv, source_name))
                idx += 2
                continue
            if nk in {"template_nosub", "template_head"}:
                raise DependencyPolicyError(f"Template literal module specifiers are not allowed in {source_name}")

            k = idx + 1
            eq_idx: int | None = None
            if nk == "ident" and k + 1 < m and sig[k + 1] == ("punct", "="):
                eq_idx = k + 1
            elif nk == "ident" and nv == "type" and k + 2 < m and sig[k + 1][0] == "ident" and sig[k + 2] == ("punct", "="):
                eq_idx = k + 2
            if eq_idx is not None:
                if (
                    eq_idx + 2 < m
                    and sig[eq_idx + 1] == ("ident", "require")
                    and sig[eq_idx + 2] == ("punct", "(")
                ):
                    if (
                        eq_idx + 4 < m
                        and sig[eq_idx + 3][0] == "string"
                        and sig[eq_idx + 4] == ("punct", ")")
                    ):
                        specs.append(_decode_js_string_literal(sig[eq_idx + 3][1], source_name))
                        idx = eq_idx + 5
                        continue
                    raise DependencyPolicyError(
                        f"import = require() requires a static string literal specifier in {source_name}"
                    )
                idx = eq_idx + 1
                continue

            j = k
            bdepth = 0
            matched_from = False
            while j < m:
                tk, tv = sig[j]
                if tk == "punct" and tv == "{":
                    bdepth += 1
                    j += 1
                    continue
                if tk == "punct" and tv == "}":
                    bdepth -= 1
                    if bdepth < 0:
                        break
                    j += 1
                    continue
                if bdepth == 0:
                    if tk == "punct" and tv == ";":
                        break
                    if tk == "ident" and tv == "from" and j > k:
                        if j == k + 1 and sig[k] == ("ident", "type") and j + 1 < m and sig[j + 1] == ("ident", "from"):
                            j += 1
                            continue
                        if j + 1 < m and sig[j + 1][0] == "string":
                            specs.append(_decode_js_string_literal(sig[j + 1][1], source_name))
                            idx = j + 2
                            matched_from = True
                            break
                        raise DependencyPolicyError(
                            f"Invalid module specifier in import statement in {source_name}"
                        )
                j += 1
            if matched_from:
                continue
            raise DependencyPolicyError(f"Malformed static import statement in {source_name}")

        if kind == "ident" and val == "export" and not is_member and not is_alias:
            if idx + 1 >= m:
                idx += 1
                continue
            if sig[idx + 1][0] == "punct" and sig[idx + 1][1] in {":", "?", ",", "}"}:
                idx += 1
                continue
            k = idx + 1
            if sig[k] == ("ident", "type") and k + 1 < m and sig[k + 1][0] == "punct" and sig[k + 1][1] in {"*", "{"}:
                k += 1
            if sig[k] == ("punct", "*"):
                j = k + 1
                if j + 1 < m and sig[j] == ("ident", "as") and sig[j + 1][0] == "ident":
                    j += 2
                if j < m and sig[j] == ("ident", "from") and j + 1 < m and sig[j + 1][0] == "string":
                    specs.append(_decode_js_string_literal(sig[j + 1][1], source_name))
                    idx = j + 2
                    continue
                raise DependencyPolicyError(f"Invalid module specifier in export * statement in {source_name}")
            if sig[k] == ("punct", "{"):
                j = k + 1
                bdepth = 1
                while j < m and bdepth > 0:
                    if sig[j] == ("punct", "{"):
                        bdepth += 1
                    elif sig[j] == ("punct", "}"):
                        bdepth -= 1
                    j += 1
                if bdepth == 0 and j < m and sig[j] == ("ident", "from"):
                    if j + 1 < m and sig[j + 1][0] == "string":
                        specs.append(_decode_js_string_literal(sig[j + 1][1], source_name))
                        idx = j + 2
                        continue
                    raise DependencyPolicyError(f"Invalid module specifier in export statement in {source_name}")

        if is_cjs and kind == "ident" and val == "require" and not is_member and not is_alias:
            if idx + 1 < m and sig[idx + 1] == ("punct", "(") and not _is_method_or_signature_decl(sig, idx, idx + 1):
                if idx + 3 < m and sig[idx + 2][0] == "string" and sig[idx + 3] == ("punct", ")"):
                    specs.append(_decode_js_string_literal(sig[idx + 2][1], source_name))
                    idx += 4
                    continue
                raise DependencyPolicyError(
                    f"CommonJS require() requires a static string literal specifier in {source_name}"
                )

        idx += 1

    return specs


def inspect_dependencies(files: list[dict]) -> dict[str, object]:
    """Validate deno.json and JS/TS imports and return summarized npm/JSR dependency metadata."""
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise DependencyPolicyError(f"Expected at most {MAX_FILES} function files")
    npm_specs: set[str] = set()
    jsr_specs: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise DependencyPolicyError("Invalid file entry payload")
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
            for spec in _extract_source_specifiers(content, name):
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


def validate_registry_name(name: str) -> str:
    clean = str(name or "").strip()
    if not REGISTRY_NAME_RE.fullmatch(clean):
        raise DependencyPolicyError("Registry name must start with alphanumeric and use 1-80 safe characters")
    return clean


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


def _bundler_url() -> str:
    url = (os.environ.get("EDGE_BUNDLER_URL") or "http://edge-bundler:18030").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise BundleBuildError("Invalid EDGE_BUNDLER_URL configuration")
    return url


def _sign_bundler_request(raw_body: bytes) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    secret = (os.environ.get("EDGE_BUNDLER_HMAC_SECRET") or "").strip()
    if not secret:
        raise BundleBuildError("Edge Function dependency bundling is not configured: set EDGE_BUNDLER_HMAC_SECRET for projects-api and edge-bundler")
    ts = str(int(time.time()))
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("ascii") + raw_body, hashlib.sha256).hexdigest()
    headers["X-Edge-Bundler-Timestamp"] = ts
    headers["X-Edge-Bundler-Signature"] = mac
    return headers


async def bundle_function_eszip(files: list[dict], *, registries: list[dict] | None = None) -> bytes:
    """Delegate ESZIP bundling for validated npm/JSR imports and private registries to edge-bundler."""
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise DependencyPolicyError(f"Expected 1 to {MAX_FILES} function files")
    validate_dependency_policy(files)
    normalized_regs = validate_registries_payload(registries)
    timeout_raw = int(os.environ.get("EDGE_BUNDLER_TIMEOUT_SECONDS", "60") or "60")
    timeout_sec = max(5, min(120, timeout_raw))
    max_raw = int(os.environ.get("EDGE_BUNDLER_MAX_ESZIP_BYTES", str(MAX_ESZIP_BYTES)) or str(MAX_ESZIP_BYTES))
    max_bytes = max(1024, min(MAX_ESZIP_BYTES, max_raw))

    payload: dict[str, object] = {"files": files}
    if normalized_regs:
        payload["registries"] = [
            {
                "kind": reg["kind"],
                "scope": reg["scope"],
                "registry_url": reg["registry_url"],
                "auth_type": reg["auth_type"],
                "token": reg["token"],
                "allow_private_network": reg["allow_private_network"],
                "ca_pem": reg["ca_pem"],
            }
            for reg in normalized_regs
        ]
    raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
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
            raise DependencyPolicyError(detail or "Disallowed Edge Function dependency or registry policy")
        raise BundleBuildError(detail or f"Edge Function dependency bundling failed (HTTP {response.status_code})")

    try:
        resp_payload = response.json()
        eszip_b64 = resp_payload["eszip_b64"]
        if not isinstance(eszip_b64, str):
            raise ValueError("Missing eszip_b64 string")
        data = base64.b64decode(eszip_b64, validate=True)
    except Exception as error:
        raise BundleBuildError("Invalid response payload from dependency bundler") from error

    if not data.startswith(b"ESZIP") or len(data) == 0 or len(data) > max_bytes:
        raise BundleBuildError("Generated ESZIP bundle failed format or size validation")
    return data
