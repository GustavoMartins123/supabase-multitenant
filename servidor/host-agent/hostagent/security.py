"""Confinamento de paths do host-agent.

Toda operacao de arquivo derivada de um comando fica restrita ao diretorio
raiz de projetos. Nomes ja passam pela regex do protocolo, mas o path
resultante tambem e verificado contra symlink e traversal antes de tocar o
filesystem ou invocar scripts.
"""

from __future__ import annotations

from pathlib import Path

from .host_agent_protocol import is_valid_project_name


class PathConfinementError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def resolve_project_dir(
    projects_root: Path,
    project: str,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve ``projects_root/<project>`` com fail-closed.

    Rejeita nomes fora da regex do protocolo, componentes symlink e
    qualquer resolucao que escape do diretorio raiz.
    """
    if not is_valid_project_name(project):
        raise PathConfinementError("invalid_project_name", project)

    root = projects_root.resolve(strict=True)
    candidate = root / project

    if candidate.is_symlink():
        raise PathConfinementError("symlink_rejected", str(candidate))

    resolved = candidate.resolve(strict=False)
    if resolved.parent != root or resolved.name != project:
        raise PathConfinementError("path_escapes_root", str(resolved))

    if must_exist and not resolved.is_dir():
        raise PathConfinementError("project_dir_missing", str(resolved))
    return resolved


def ensure_inside(root: Path, target: Path) -> Path:
    """Garante que ``target`` (apos resolver) permanece sob ``root``."""
    resolved_root = root.resolve(strict=True)
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(resolved_root):
        raise PathConfinementError("path_escapes_root", str(resolved))
    return resolved
