"""Challenge-bound canonical directory read. Shared byte-for-byte with the agent."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import ssl
import time
import urllib.request
from urllib.parse import urlsplit


class DirectoryUnavailable(RuntimeError):
    pass


def _read(origin: str, secret: str, ca_file: str | None) -> dict:
    parsed = urlsplit(origin)
    if not secret or parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.path not in {'', '/'} or parsed.username or parsed.query or parsed.fragment:
        raise DirectoryUnavailable('Canonical Studio callback is not configured')
    target = '/internal/users/directory'
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    canonical = '\n'.join(('internal-hmac-v1', 'projects-api', 'GET', target, timestamp, nonce, hashlib.sha256(b'').hexdigest()))
    headers = {
        'X-Internal-Version': 'internal-hmac-v1', 'X-Internal-Service': 'projects-api',
        'X-Internal-Timestamp': timestamp, 'X-Internal-Nonce': nonce,
        'X-Internal-Signature': hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest(),
    }
    context = ssl.create_default_context(cafile=ca_file) if parsed.scheme == 'https' else None
    # Do not follow redirects to another authority or downgrade TLS.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    with opener.open(urllib.request.Request(origin.rstrip('/') + target, headers=headers), timeout=5) as response:
        body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise DirectoryUnavailable('Directory exceeds size limit')
        expected = hmac.new(secret.encode(), b'studio-directory-v1\n' + nonce.encode() + b'\n' + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(response.headers.get('X-Directory-Signature', ''), expected):
            raise DirectoryUnavailable('Invalid directory response signature')
    result = json.loads(body)
    if not isinstance(result, dict) or not isinstance(result.get('sequence'), int) or isinstance(result['sequence'], bool) or not 0 < result['sequence'] <= 9007199254740991 or not isinstance(result.get('revision'), str) or not re.fullmatch('[0-9a-f]{64}', result['revision']) or not isinstance(result.get('users'), list):
        raise DirectoryUnavailable('Invalid directory snapshot')
    seen = set()
    for user in result['users']:
        if not isinstance(user, dict) or not isinstance(user.get('id'), str) or not re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', user['id']) or user['id'] in seen or not isinstance(user.get('is_active'), bool) or not isinstance(user.get('groups'), list) or not all(isinstance(g, str) for g in user['groups']):
            raise DirectoryUnavailable('Invalid directory user')
        seen.add(user['id'])
    return result


async def read_directory(origin: str, secret: str, ca_file: str | None) -> dict:
    try:
        return await asyncio.to_thread(_read, origin, secret, ca_file)
    except Exception as exc:
        raise DirectoryUnavailable('Canonical directory could not be proved') from exc
