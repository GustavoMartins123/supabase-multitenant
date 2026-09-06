"""Converte docs/api/openapi.json (3.1) para um subconjunto 3.0 legivel
pelo openapi-generator 7.x (cliente Dart).

Unica transformacao: `anyOf: [T, {"type": "null"}]` vira `T` com
`"nullable": true`. Todo o resto passa intacto. O artefato publicado
continua 3.1; esta conversao serve apenas como entrada do gerador.

Uso: python tools/openapi_to_30.py [entrada] [saida]
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "docs" / "api" / "openapi.json"


def _convert(node: object) -> object:
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _convert(value) for key, value in node.items()}
    branches = node.get("anyOf")
    if isinstance(branches, list) and len(branches) == 2:
        nullables = [b for b in branches if b == {"type": "null"}]
        if len(nullables) == 1:
            other = next(b for b in branches if b != {"type": "null"})
            if isinstance(other, dict):
                merged = dict(other)
                merged["nullable"] = True
                if "title" not in merged and "title" in node:
                    merged["title"] = node["title"]
                if "description" not in merged and "description" in node:
                    merged["description"] = node["description"]
                if "default" not in merged and "default" in node:
                    merged["default"] = node["default"]
                del node["anyOf"]
                node.update(merged)
    return node


def main() -> int:
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
    spec = json.loads(src.read_text(encoding="utf-8"))
    spec = _convert(spec)
    spec["openapi"] = "3.0.3"
    spec.pop("jsonSchemaDialect", None)
    rendered = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    if dst is None:
        print(rendered, end="")
        return 0
    dst.write_text(rendered, encoding="utf-8")
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
