"""Corrige bugs de template do openapi-generator (dart) sobre o spec.

1. Modelos vazios extraídos de unions: o construtor `X({\n  });` é
   inválido (vira `X();`), o operador == termina em `&&` pendente
   (vira `|| other is X;`) e o hashCode fica sem expressão
   (vira `=> 0;`; toda instância vazia é igual, hash constante correto).
2. Defaults de enum declarados no schema se aplicam apenas a campos ausentes;
   valores desconhecidos geram FormatException.
3. Cast de lista de mapas: `.cast<Map>()` devolve
   `List<Map<dynamic, dynamic>>`, incompatível com o retorno
   `List<Map<String, Object>>` declarado: vira
   `.cast<Map<String, Object>>()`.

Roda dentro de tools/generate_dart_client.sh, antes do `dart analyze`
que funciona como gate: se os padrões mudarem, o analyze falha alto.
"""

from __future__ import annotations

import pathlib
import json
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
SCHEMA_FILE = MODEL_DIR.parents[3] / "docs/api/openapi.json"

EMPTY_EQUALS = re.compile(r"\|\| other is (\w+) &&\n\n  @override")
EMPTY_CTOR = re.compile(r"  (\w+)\(\{\n  \}\);")
CAST_MAP = re.compile(r"\.cast<Map>\(\)")
EMPTY_HASHCODE = re.compile(
    r"int get hashCode =>\n    // ignore: unnecessary_parenthesis\n\n"
)
ENUM_FALLBACK = re.compile(r"(\w+Enum)\.fromJson\(([^)]+)\) \?\? '([\w-]+)'")


def patch(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    counts = {"empty_equals": 0, "empty_ctor": 0, "empty_hashcode": 0, "enum_fallback": 0, "cast_map": 0, "required_keys": 0}
    model_name = re.search(r"^class (\w+) \{", text, re.M)
    if model_name and "requiredKeys.forEach" in text:
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        model = schema["components"]["schemas"].get(model_name.group(1))
        required = re.search(r"static const requiredKeys = <String>\{(.*?)\};", text, re.S)
        if model is None and required and not required.group(1).strip():
            model = {"properties": {}}
        if model is None:
            raise ValueError(f"Missing schema for {model_name.group(1)}")
        nullable = [key for key, prop in model.get("properties", {}).items()
                    if any(item.get("type") == "null" for item in prop.get("anyOf", []))]
        keys = ", ".join(f"r'{key}'" for key in nullable)
        replacement = f"""      const nullableKeys = <String>{{{keys}}};
      for (final key in requiredKeys) {{
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {{
          throw FormatException('Invalid required field: $key');
        }}
      }}"""
        text, counts["required_keys"] = re.subn(
            r"      // Ensure that the map contains the required keys\..*?      \}\(\)\);",
            lambda _: replacement, text, flags=re.S)
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
        return (f"{match.group(2)} == null ? const {match.group(1)}._('{match.group(3)}') "
                f": ({match.group(1)}.fromJson({match.group(2)}) "
                f"?? (throw const FormatException('Invalid {match.group(1)}')))")

    text, _ = ENUM_FALLBACK.subn(_enum, text)
    if any(counts.values()):
        path.write_text(text, encoding="utf-8")
    return counts


def main() -> int:
    if not MODEL_DIR.is_dir():
        print(f"missing {MODEL_DIR}; generate the client first")
        return 1
    total = {"empty_equals": 0, "empty_ctor": 0, "empty_hashcode": 0, "enum_fallback": 0, "cast_map": 0, "required_keys": 0}
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
    client = MODEL_DIR.parents[1]
    manifest = {
        path.relative_to(client).as_posix()
        for folder, extension in (("doc", "*.md"), ("lib", "*.dart"), ("test", "*.dart"))
        for path in (client / folder).rglob(extension)
    }
    manifest.update(name for name in (
        ".gitignore", ".openapi-generator-ignore", "README.md", "analysis_options.yaml", "pubspec.yaml"
    ) if (client / name).is_file())
    (client / ".openapi-generator/FILES").write_text(
        "\n".join(sorted(manifest)) + "\n", encoding="utf-8", newline="\n")
    for name in manifest:
        path = client / name
        if path.suffix in {".dart", ".md", ".yaml"}:
            original = path.read_text(encoding="utf-8")
            normalized = "\n".join(line.rstrip() for line in original.splitlines()) + "\n"
            path.write_text(normalized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
