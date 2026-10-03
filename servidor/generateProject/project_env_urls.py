from urllib.parse import urlsplit


def render_project_url_values(current: dict[str, str], replacements: dict[str, str]) -> dict[str, str]:
    configured = {key: current[key] for key in ("SITE_URL", "ADDITIONAL_REDIRECT_URLS") if key in current}
    if not configured:
        return {}
    old_auth_url = current.get("API_EXTERNAL_URL", "")
    parsed = urlsplit(old_auth_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("API_EXTERNAL_URL must be an absolute project Auth URL")
    if not parsed.path.endswith("/auth/v1"):
        raise ValueError("API_EXTERNAL_URL must end with /auth/v1")
    old_default = old_auth_url.removesuffix("/auth/v1") + "/verify-success.html"
    new_default = replacements["project_public_url"] + "/verify-success.html"
    if configured.get("SITE_URL") == old_default:
        configured["SITE_URL"] = new_default
    if "ADDITIONAL_REDIRECT_URLS" in configured:
        configured["ADDITIONAL_REDIRECT_URLS"] = ",".join(
            new_default if entry == old_default else entry
            for entry in configured["ADDITIONAL_REDIRECT_URLS"].split(",")
        )
    return configured
