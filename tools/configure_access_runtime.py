"""Generate private admission runtime values without changing existing secrets."""

import argparse
import ipaddress
import os
import json
from pathlib import Path
import secrets
import re


def configure(path: Path, studio_ip: str, studio_network: str):
    values = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key in values:
                raise ValueError("Duplicate runtime setting")
            values[key] = value
    additions = {}
    for key in ("ACCESS_ADMISSION_SECRET", "ACCESS_RATE_REDIS_PASSWORD"):
        if key not in values or values[key] in {"", "pass"}:
            additions[key] = secrets.token_hex(32)
    if "ACCESS_ADMIN_CIDRS" not in values or values["ACCESS_ADMIN_CIDRS"] in {"", "pass"}:
        ip = ipaddress.ip_address(studio_ip)
        network = ipaddress.ip_network(studio_network, strict=True)
        if network.prefixlen == 0:
            raise ValueError("Unrestricted administrative origin is forbidden")
        additions["ACCESS_ADMIN_CIDRS"] = f"{ip}/{ip.max_prefixlen},{network}"
    if "ACCESS_TRUSTED_PROXY_CIDRS" not in values:
        additions["ACCESS_TRUSTED_PROXY_CIDRS"] = ""
    values.update(additions)
    for key in ("ACCESS_ADMISSION_SECRET", "ACCESS_RATE_REDIS_PASSWORD"):
        if not re.fullmatch(r"[a-f0-9]{64}", values[key]):
            raise ValueError(f"Invalid {key}")
    for key in ("ACCESS_TRUSTED_PROXY_CIDRS", "ACCESS_ADMIN_CIDRS"):
        entries = values[key].split(",") if values[key] else []
        if key == "ACCESS_ADMIN_CIDRS" and not entries:
            raise ValueError("Administrative origins are required")
        for value in entries:
            network = ipaddress.ip_network(value, strict=True)
            if isinstance(network, ipaddress.IPv6Network) and network.network_address.ipv4_mapped:
                raise ValueError(f"Use IPv4 notation for mapped networks in {key}")
            if network.prefixlen == 0:
                raise ValueError(f"Unrestricted network is forbidden in {key}")
    proxies = (
        values["ACCESS_TRUSTED_PROXY_CIDRS"].split(",")
        if values["ACCESS_TRUSTED_PROXY_CIDRS"]
        else []
    )
    directory = path.resolve().parent / "traefik"
    template = (directory / "traefik.yml").read_text(encoding="utf-8")
    for port in ("80", "443"):
        marker = f'    address: ":{port}"'
        if template.count(marker) != 1:
            raise ValueError("Traefik entrypoint template is not canonical")
        forwarding = "\n    forwardedHeaders:\n      trustedIPs: " + json.dumps(proxies)
        template = template.replace(marker, marker + forwarding)
    for key, value in additions.items():
        if any(line.startswith(key + "=") for line in lines):
            lines = [f"{key}={value}" if line.startswith(key + "=") else line for line in lines]
        else:
            lines.append(f"{key}={value}")
    if additions:
        temporary = path.with_name(".access-runtime-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as file:
                os.chmod(temporary, 0o600)
                file.write("\n".join(lines) + "\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    output = directory / "traefik.runtime.yml"
    temporary = directory / (".traefik-runtime-" + secrets.token_hex(8))
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as file:
            os.chmod(temporary, 0o600)
            file.write(template)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--studio-ip", required=True)
    parser.add_argument("--studio-network", required=True)
    args = parser.parse_args()
    configure(args.env, args.studio_ip, args.studio_network)
