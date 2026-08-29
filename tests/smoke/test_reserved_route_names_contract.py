from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

SLUG_WORD_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")


def _extract_py_set(text: str, name: str) -> frozenset[str]:
    match = re.search(
        rf"{name}\s*=\s*(?:frozenset\()?\s*\{{(.*?)\}}", text, re.DOTALL
    )
    if not match:
        raise AssertionError(f"{name} nao encontrado")
    return frozenset(re.findall(r'"([^"]+)"', match.group(1)))


def _extract_bash_array(text: str, name: str) -> frozenset[str]:
    match = re.search(rf"{name}=\(([^)]*)\)", text)
    if not match:
        raise AssertionError(f"{name} nao encontrado")
    return frozenset(match.group(1).split())


def _extract_dart_set(text: str, name: str) -> frozenset[str]:
    match = re.search(rf"{name} = <String>\{{(.*?)\}};", text, re.DOTALL)
    if not match:
        raise AssertionError(f"{name} nao encontrado")
    return frozenset(re.findall(r"'([^']+)'", match.group(1)))


DART_VALIDATOR = "studio/seletor_de_projetos/lib/utils/project_name_validator.dart"
DART_DIALOG_IMPORTS = {
    "studio/seletor_de_projetos/lib/new_project_dialog.dart": (
        "import 'package:seletor_de_projetos/utils/project_name_validator.dart';"
    ),
    "studio/seletor_de_projetos/lib/duplicate_project_dialog.dart": (
        "import 'package:seletor_de_projetos/utils/project_name_validator.dart';"
    ),
    "studio/seletor_de_projetos/lib/dialogs/rename_project_dialog.dart": (
        "import '../utils/project_name_validator.dart';"
    ),
}


class ReservedRouteNamesContractTest(unittest.TestCase):
    def test_reserved_words_are_identical_across_every_copy(self) -> None:
        # ProjectNameValidator em host_agent_protocol.py e a fonte unica; a
        # copia do host-agent e testada byte-a-byte contra ela em
        # test_host_agent_contract.py.
        canonical_text = (
            ROOT / "servidor/api-internal/app/host_agent_protocol.py"
        ).read_text(encoding="utf-8")
        combined = (
            _extract_py_set(canonical_text, "RESERVED_WORDS")
            | _extract_py_set(canonical_text, "RESERVED_ROUTE_NAMES")
            | _extract_py_set(canonical_text, "RESERVED_API_NAMES")
        )

        api_validation = (
            ROOT / "servidor/api-internal/app/validation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from app.host_agent_protocol import ProjectNameValidator", api_validation)
        self.assertNotIn("RESERVED_WORDS =", api_validation)
        self.assertNotIn("RESERVED_ROUTE_NAMES =", api_validation)

        for relative in (
            "servidor/generateProject/lib/generate_project_impl.sh",
            "servidor/generateProject/lib/duplicate_project_impl.sh",
            "servidor/generateProject/lib/rename_project_impl.sh",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            got = (
                _extract_bash_array(text, "RESERVED")
                | _extract_bash_array(text, "RESERVED_ROUTES")
                | _extract_bash_array(text, "RESERVED_API")
            )
            self.assertEqual(got, combined, relative)

        dart_validator = (ROOT / DART_VALIDATOR).read_text(encoding="utf-8")
        dart_words = _extract_dart_set(dart_validator, "reservedWords")
        self.assertEqual(dart_words, combined, DART_VALIDATOR)

        for relative, expected_import in DART_DIALOG_IMPORTS.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(expected_import, text, relative)
            self.assertNotIn("_reserved", text, relative)

    def test_reserved_route_names_match_malicious_paths_router(self) -> None:
        canonical_text = (
            ROOT / "servidor/api-internal/app/host_agent_protocol.py"
        ).read_text(encoding="utf-8")
        route_words = _extract_py_set(canonical_text, "RESERVED_ROUTE_NAMES")

        middlewares = (ROOT / "servidor/traefik/middlewares.yml").read_text(
            encoding="utf-8"
        )
        rule_match = re.search(r'malicious-paths:\s*\n\s*rule: "([^"]*)"', middlewares)
        if not rule_match:
            raise AssertionError("rule do malicious-paths nao encontrada")
        prefixes = re.findall(r"PathPrefix\(`/([^`]*)`\)", rule_match.group(1))
        blockable_slugs = frozenset(
            prefix for prefix in prefixes if SLUG_WORD_RE.fullmatch(prefix)
        )
        self.assertEqual(route_words, blockable_slugs)


if __name__ == "__main__":
    unittest.main()
