"""Contrato estatico da versao unica da plataforma.

`VERSION` na raiz e a fonte canonica. Todo outro lugar que carrega o numero
(runtime da API, OpenAPI publicado, cliente Dart gerado, app Flutter, script
de geracao, matriz de compatibilidade) precisa concordar com ela.

O runtime nao le `VERSION`: o Dockerfile da API so copia `api-internal/app`,
entao `app/version.py` continua sendo uma constante literal. A garantia e
este contrato, exercitado no CI e em `tests/smoke/test_version_contract.py`.

Uso:
    python3 tools/check-version-parity.py [--fix]

Sem `--fix` apenas relata. Com `--fix`, reescreve os pontos derivados para o
valor de `VERSION` (nunca o contrario: `VERSION` so muda a mao).
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

SEMVER_RE = re.compile(
    r"^(?P<core>\d+\.\d+\.\d+)(?P<pre>-[0-9A-Za-z.-]+)?$"
)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def render(self) -> int:
        for message in self.errors:
            print(f"ERROR: {message}")
        for message in self.warnings:
            print(f"WARNING: {message}")
        print(
            f"version-parity: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s)"
        )
        return 1 if self.errors else 0


class Source:
    """Um lugar do repo que carrega a versao derivada de `VERSION`."""

    def __init__(
        self,
        relative: str,
        pattern: str,
        *,
        description: str,
        allow_build_metadata: bool = False,
    ) -> None:
        self.relative = relative
        self.description = description
        self.allow_build_metadata = allow_build_metadata
        self.regex = re.compile(pattern)

    def path(self) -> pathlib.Path:
        return ROOT / self.relative

    def read(self, report: Report) -> tuple[str, str] | None:
        path = self.path()
        if not path.is_file():
            report.error(f"{self.relative}: arquivo ausente ({self.description})")
            return None
        text = path.read_text(encoding="utf-8")
        match = self.regex.search(text)
        if match is None:
            report.error(
                f"{self.relative}: nao encontrei a versao "
                f"({self.description}); padrao mudou?"
            )
            return None
        return text, match.group("ver")

    def write(self, text: str, expected: str) -> None:
        match = self.regex.search(text)
        assert match is not None
        start, end = match.span("ver")
        self.path().write_text(
            text[:start] + expected + text[end:],
            encoding="utf-8",
            newline="\n",
        )


SOURCES = [
    Source(
        "servidor/api-internal/app/version.py",
        r'API_VERSION\s*=\s*"(?P<ver>[^"]+)"',
        description="versao servida pela Projects API em runtime",
    ),
    Source(
        "studio/projects_api_client/pubspec.yaml",
        r"(?m)^version:\s*'(?P<ver>[^']+)'",
        description="pubspec do cliente Dart gerado",
    ),
    Source(
        "studio/projects_api_client/README.md",
        r"(?m)^- API version:\s*(?P<ver>\S+)",
        description="README do cliente Dart gerado",
    ),
    Source(
        "tools/generate_dart_client.sh",
        r"pubVersion=(?P<ver>[^,]+),",
        description="argumento do openapi-generator",
    ),
    Source(
        "studio/seletor_de_projetos/pubspec.yaml",
        r"(?m)^version:\s*(?P<ver>\S+)",
        description="pubspec do app Flutter (aceita sufixo +build)",
        allow_build_metadata=True,
    ),
    Source(
        "COMPATIBILITY_MATRIX.md",
        r"(?m)^\| \*\*Plataforma\*\* \| `(?P<ver>[^`]+)` \|",
        description="linha da plataforma na matriz de compatibilidade",
    ),
]


def read_canonical(report: Report) -> str | None:
    if not VERSION_FILE.is_file():
        report.error("VERSION: arquivo ausente na raiz do repositorio")
        return None
    raw = VERSION_FILE.read_text(encoding="utf-8")
    version = raw.strip()
    if not version:
        report.error("VERSION: arquivo vazio")
        return None
    if raw != version + "\n":
        report.warning(
            "VERSION: deve conter uma unica linha terminada em newline"
        )
    if SEMVER_RE.match(version) is None:
        report.error(
            f"VERSION: {version!r} nao e semver "
            "`major.minor.patch[-prerelease]`"
        )
        return None
    return version


def check_openapi(report: Report, expected: str, fix: bool) -> None:
    """`docs/api/openapi.json` e gerado; so relata, nunca reescreve a mao."""
    relative = "docs/api/openapi.json"
    path = ROOT / relative
    if not path.is_file():
        report.error(f"{relative}: arquivo ausente (OpenAPI publicado)")
        return
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"{relative}: JSON invalido: {exc}")
        return
    found = document.get("info", {}).get("version")
    if found == expected:
        return
    message = f"{relative}: info.version={found!r}, esperado {expected!r}"
    if fix:
        message += " (rode `python tools/export_openapi.py` apos ajustar version.py)"
    report.error(message)


def check_sources(report: Report, expected: str, fix: bool) -> None:
    for source in SOURCES:
        result = source.read(report)
        if result is None:
            continue
        text, found = result
        comparable = found
        if source.allow_build_metadata:
            comparable = found.split("+", 1)[0]
        if comparable == expected:
            continue
        if fix:
            replacement = expected
            if source.allow_build_metadata and "+" in found:
                replacement = f"{expected}+{found.split('+', 1)[1]}"
            source.write(text, replacement)
            print(f"FIX: {source.relative}: {found} -> {replacement}")
            continue
        report.error(
            f"{source.relative}: versao {found!r}, esperado {expected!r} "
            f"({source.description})"
        )


def main() -> int:
    fix = "--fix" in sys.argv[1:]
    report = Report()
    expected = read_canonical(report)
    if expected is None:
        return report.render()
    check_sources(report, expected, fix)
    check_openapi(report, expected, fix)
    if not report.errors:
        print(f"version-parity: VERSION={expected} propagada em todos os pontos")
    return report.render()


if __name__ == "__main__":
    raise SystemExit(main())
