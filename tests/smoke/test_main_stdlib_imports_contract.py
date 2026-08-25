"""main.py nao pode usar modulo stdlib sem importa-lo no topo.

Regressao real: startup usava os.getenv() sem 'import os' — py_compile passa,
o container quebra no boot. Este contrato varre a AST e falha se qualquer
modulo stdlib conhecido for usado como nome global sem import correspondente.
"""

from __future__ import annotations

import ast
import pathlib
import unittest


MAIN = (
    pathlib.Path(__file__).resolve().parents[2]
    / "servidor" / "api-internal" / "app" / "main.py"
)

STDLIB_MODULES = {
    "os", "sys", "re", "json", "time", "uuid", "secrets", "hmac",
    "hashlib", "base64", "tempfile", "shutil", "math", "statistics",
    "ipaddress", "socket",
}


class MainStdlibImportsContract(unittest.TestCase):
    def test_every_used_stdlib_module_is_imported(self) -> None:
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])

        used_roots = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in STDLIB_MODULES
        }

        missing = sorted(used_roots - imported)
        self.assertEqual(
            missing,
            [],
            "modulos usados sem import no topo de main.py: "
            f"{missing}",
        )

    def test_os_is_imported_for_startup_and_meta_paths(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^import os$")
        self.assertIn('os.getenv("META_ADMIN_DSN")', source)


if __name__ == "__main__":
    unittest.main()
