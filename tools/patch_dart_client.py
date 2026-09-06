"""Corrige bugs de template do openapi-generator (dart) sobre o spec.

1. Modelos vazios extraídos de unions: o construtor `X({\n  });` é
   inválido (vira `X();`), o operador == termina em `&&` pendente
   (vira `|| other is X;`) e o hashCode fica sem expressão
   (vira `=> 0;`; toda instância vazia é igual, hash constante correto).
2. Fallback de enum com literal string (`?? 'medium'`) onde o campo
   exige o enum: vira `?? const Enum._('literal')`.
3. Cast de lista de mapas: `.cast<Map>()` devolve
   `List<Map<dynamic, dynamic>>`, incompatível com o retorno
   `List<Map<String, Object>>` declarado: vira
   `.cast<Map<String, Object>>()`.

Roda dentro de tools/generate_dart_client.sh, antes do `dart analyze`
que funciona como gate: se os padrões mudarem, o analyze falha alto.
"""

from __future__ import annotations

import pathlib
import re
import sys

MODEL_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "studio"
    / "projects_api_client"
    / "lib"
    / "model"
)
API_DIR = MODEL_DIR.parent / "api"

EMPTY_EQUALS = re.compile(r"\|\| other is (\w+) &&\n\n  @override")
EMPTY_CTOR = re.compile(r"  (\w+)\(\{\n  \}\);")
CAST_MAP = re.compile(r"\.cast<Map>\(\)")
EMPTY_HASHCODE = re.compile(
    r"int get hashCode =>\n    // ignore: unnecessary_parenthesis\n\n"
)
ENUM_FALLBACK = re.compile(r"(\w+Enum)\.fromJson\(([^)]+)\) \?\? '([\w-]+)'")


def patch(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    counts = {"empty_equals": 0, "empty_ctor": 0, "empty_hashcode": 0, "enum_fallback": 0, "cast_map": 0}
    if path.suffix == ".dart" and ("/api/" in path.as_posix() or path.name.endswith("_api.dart")):
        text, counts["cast_map"] = CAST_MAP.subn(".cast<Map<String, Object>>()", text)
    text, counts["empty_equals"] = EMPTY_EQUALS.subn(
        r"|| other is \1;\n\n  @override", text
    )
    text, counts["empty_ctor"] = EMPTY_CTOR.subn(r"  \1();", text)
    if "int get hashCode =>\n    // ignore: unnecessary_parenthesis\n\n" in text:
        text, counts["empty_hashcode"] = EMPTY_HASHCODE.subn(
            "int get hashCode => 0;\n\n", text
        )

    def _enum(match: re.Match[str]) -> str:
        counts["enum_fallback"] += 1
        return f"{match.group(1)}.fromJson({match.group(2)}) ?? const {match.group(1)}._('{match.group(3)}')"

    text, _ = ENUM_FALLBACK.subn(_enum, text)
    if any(counts.values()):
        path.write_text(text, encoding="utf-8")
    return counts


def main() -> int:
    if not MODEL_DIR.is_dir():
        print(f"missing {MODEL_DIR}; generate the client first")
        return 1
    total = {"empty_equals": 0, "empty_ctor": 0, "empty_hashcode": 0, "enum_fallback": 0, "cast_map": 0}
    touched: list[str] = []
    targets = sorted(MODEL_DIR.glob("*.dart"))
    if API_DIR.is_dir():
        targets += sorted(API_DIR.glob("*.dart"))
    for path in targets:
        counts = patch(path)
        if any(counts.values()):
            touched.append(path.name)
            for key, value in counts.items():
                total[key] += value
    print(f"patched {len(touched)} files: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
