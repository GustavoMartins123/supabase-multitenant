#!/usr/bin/env python3
"""Copy only the Studio public CA certificate into the server runtime tree."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "studio" / "authelia" / "ssl" / "ca.pem"
DEFAULT_TARGET = REPO_ROOT / "servidor" / "certs" / "ca.pem"


def sync_certificate(source: Path, target: Path, *, force: bool = False) -> None:
    if target.exists() and not force:
        raise RuntimeError(f"destino ja existe: {target}")
    certificate = source.read_text(encoding="ascii")
    if "-----BEGIN CERTIFICATE-----" not in certificate:
        raise RuntimeError("arquivo de origem nao e um certificado PEM")
    check = subprocess.run(
        ["openssl", "x509", "-noout", "-in", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if check.returncode != 0:
        raise RuntimeError("certificado PEM invalido")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(certificate)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        sync_certificate(args.source, args.target, force=args.force)
        print(f"CA publica sincronizada: {args.target}")
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
