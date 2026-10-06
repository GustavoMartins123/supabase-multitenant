"""Filesystem integrity primitives for offline installation migrations."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


def canonical_path(path: Path) -> Path:
    absolute = path.absolute()
    for parent in (absolute, *absolute.parents):
        if parent.is_symlink():
            raise RuntimeError("Migration paths must not contain symbolic links")
    return absolute


def plain_tree(path: Path) -> None:
    canonical_path(path)
    if not path.is_dir():
        raise RuntimeError("Migration directory is required")
    for child in path.rglob("*"):
        mode = child.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise RuntimeError("Only regular files and directories are allowed")


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_tree(path: Path) -> None:
    plain_tree(path)
    for child in path.rglob("*"):
        if child.is_file():
            with child.open("rb") as stream:
                os.fsync(stream.fileno())
    for directory in sorted((p for p in path.rglob("*") if p.is_dir()), reverse=True):
        sync_directory(directory)
    sync_directory(path)


def file_digest(path: Path) -> str:
    canonical_path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError("Regular migration file is required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(path: Path) -> str:
    plain_tree(path)
    result = hashlib.sha256()
    for child in [path, *sorted(path.rglob("*"))]:
        metadata = json.dumps([
            child.relative_to(path).as_posix(),
            "directory" if child.is_dir() else "file",
            stat.S_IMODE(child.stat().st_mode),
            child.stat().st_size if child.is_file() else 0,
        ], separators=(",", ":")).encode()
        result.update(len(metadata).to_bytes(8, "big"))
        result.update(metadata)
        if child.is_file():
            result.update(child.read_bytes())
    return result.hexdigest()


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    canonical_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".migration-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(temporary, mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def remove_owned(path: Path, root: Path) -> None:
    canonical_path(path)
    canonical_path(root)
    if path == root or not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError("Migration cleanup escaped its private directory")
    plain_tree(path)
    shutil.rmtree(path)
    sync_directory(path.parent)
