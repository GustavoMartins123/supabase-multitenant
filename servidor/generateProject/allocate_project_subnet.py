#!/usr/bin/env python3
"""Allocate a non-overlapping /28 subnet inside 172.52.0.0/16 for a project's internal network."""
from __future__ import annotations

import hashlib
import ipaddress
from pathlib import Path
import re
import subprocess
import sys

POOL_NETWORK = ipaddress.IPv4Network("172.52.0.0/16")
PROJECT_SLOTS = list(POOL_NETWORK.subnets(new_prefix=28))[1:]  # Reserve index 0; 4095 /28 blocks.
SUBNET_LINE_RE = re.compile(r"^[ \t]*PROJECT_INTERNAL_SUBNET=([^\r\n#]+)")


def _parse_network(raw: str) -> ipaddress.IPv4Network | None:
    cleaned = raw.strip().strip("\"'")
    if not cleaned:
        return None
    try:
        net = ipaddress.ip_network(cleaned, strict=False)
    except ValueError:
        return None
    return net if isinstance(net, ipaddress.IPv4Network) else None


def _collect_docker_networks() -> list[ipaddress.IPv4Network]:
    try:
        ids_proc = subprocess.run(
            ["docker", "network", "ls", "-q"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    net_ids = [line.strip() for line in ids_proc.stdout.splitlines() if line.strip()]
    if ids_proc.returncode != 0 or not net_ids:
        return []
    try:
        inspect_proc = subprocess.run(
            ["docker", "network", "inspect", *net_ids, "-f", "{{range .IPAM.Config}}{{.Subnet}} {{end}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if inspect_proc.returncode != 0:
        return []
    nets: list[ipaddress.IPv4Network] = []
    for token in inspect_proc.stdout.split():
        parsed = _parse_network(token)
        if parsed is not None:
            nets.append(parsed)
    return nets


def allocate_project_internal_subnet(
    project_id: str,
    projects_dir: Path | None = None,
    *,
    extra_used: set[str] | None = None,
    inspect_docker: bool = True,
) -> str:
    """Return an idempotent /28 CIDR for `project_id`, avoiding collisions with other projects or Docker bridges."""
    existing_for_project: ipaddress.IPv4Network | None = None
    used_cidrs: list[ipaddress.IPv4Network] = []

    if extra_used:
        for item in extra_used:
            parsed = _parse_network(item)
            if parsed is not None:
                used_cidrs.append(parsed)

    if projects_dir is not None and projects_dir.is_dir():
        for entry in sorted(projects_dir.iterdir(), key=lambda p: p.name):
            try:
                if entry.is_symlink() or not entry.is_dir():
                    continue
                env_path = entry / ".env"
                if not env_path.is_file() or env_path.is_symlink():
                    continue
                text = env_path.read_text(encoding="utf-8")
            except (PermissionError, OSError):
                continue
            for line in text.splitlines():
                match = SUBNET_LINE_RE.match(line)
                if not match:
                    continue
                parsed = _parse_network(match.group(1))
                if parsed is None:
                    continue
                if entry.name == project_id:
                    existing_for_project = parsed
                else:
                    used_cidrs.append(parsed)
                break

    if existing_for_project is not None:
        return str(existing_for_project)

    if inspect_docker:
        used_cidrs.extend(_collect_docker_networks())

    start_idx = int.from_bytes(hashlib.sha256(project_id.encode("utf-8")).digest()[:4], "big") % len(PROJECT_SLOTS)
    for offset in range(len(PROJECT_SLOTS)):
        candidate = PROJECT_SLOTS[(start_idx + offset) % len(PROJECT_SLOTS)]
        if not any(candidate.overlaps(used) for used in used_cidrs):
            return str(candidate)

    raise RuntimeError("No free /28 subnet left in 172.52.0.0/16")


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: allocate_project_subnet.py <project_id> [projects_dir]", file=sys.stderr)
        return 2
    project_id = sys.argv[1].strip()
    projects_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    print(allocate_project_internal_subnet(project_id, projects_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
