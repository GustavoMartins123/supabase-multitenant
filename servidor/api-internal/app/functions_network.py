"""Canonical, explicit outbound host:port grants for one project's workers."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


def network_hosts(value: str | list[str] = "") -> list[str]:
    if isinstance(value, str):
        entries = value.split(",") if value.strip() else []
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        entries = value
    else:
        raise ValueError("Functions network grants must be explicit host:port entries")
    if len(entries) > 32:
        raise ValueError("At most 32 external Functions network grants are allowed")
    result = []
    for entry in entries:
        entry = entry.strip().lower()
        parsed = urlsplit("//" + entry)
        try:
            host, port = parsed.hostname, parsed.port
        except ValueError as error:
            raise ValueError("Invalid Functions network destination") from error
        if (not host or not port or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or any(char in entry for char in "*%\\\r\n\t")):
            raise ValueError("Functions destinations require an exact host and port, without URLs or wildcards")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if (len(host) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host)
                    or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid"))):
                raise ValueError("Only explicit external API domains are allowed")
        else:
            if not address.is_global:
                raise ValueError("Private, local and reserved network destinations are not external APIs")
        canonical = ("[" + host + "]" if ":" in host else host) + ":" + str(port)
        if canonical != entry:
            raise ValueError("Noncanonical Functions network destination")
        if canonical not in result:
            result.append(canonical)
    return sorted(result)


def ensure_network_hosts_file(path: Path) -> None:
    """Initialize only the supervisor's private DNS map; never replace live pins."""
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Refusing a symlinked Functions DNS map")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise ValueError("Invalid Functions DNS map")
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"127.0.0.1 localhost\n::1 localhost ip6-localhost\n")
            stream.flush()
            os.fsync(stream.fileno())
