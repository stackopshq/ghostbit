"""HTTP plumbing — user-agent, SSL context, typed error reporting.

Kept deliberately thin (no requests/httpx dependency) so the installed
CLI wheel stays small. certifi is an optional hard-dep from pyproject
mostly to make macOS behave; everywhere else the system trust store is
fine.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        _VERSION = _pkg_version("ghostbit-cli")
    except PackageNotFoundError:
        _VERSION = "dev"
except ImportError:
    _VERSION = "dev"

USER_AGENT = f"Ghostbit-CLI/{_VERSION}"

try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()


def api_create(server: str, payload: dict) -> dict:
    url = server.rstrip("/") + "/api/v1/pastes"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:  # noqa: BLE001
            detail = body
        print(f"Error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not connect to {server}: {e.reason}", file=sys.stderr)
        print("  Tip: run `gbit config set server <URL>` to set your server.", file=sys.stderr)
        sys.exit(1)
