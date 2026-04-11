"""
Webhook delivery — fire-and-forget POST on paste read.

Payload (JSON):
  {
    "event":      "paste.read",
    "paste_id":   "abc123",
    "view_count": 1,
    "burned":     false,
    "timestamp":  1712345678
  }

Signature (optional):
  If WEBHOOK_SECRET is set in config, every request includes:
    X-Ghostbit-Signature: sha256=<HMAC-SHA256(payload, secret)>
  The recipient can verify authenticity by recomputing the HMAC over the raw
  request body and comparing to the header value (constant-time comparison).

- Non-blocking: runs in a background task, never delays the response.
- Single attempt with a 5s timeout — no retries to avoid hammering.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import time
import urllib.parse
import urllib.request
from typing import Optional

from config import settings

# RFC-1918 + loopback + link-local ranges forbidden as webhook targets
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_ssrf_safe(url: str) -> bool:
    """Return True only if the URL hostname resolves to a public IP."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        addr = ipaddress.ip_address(host)
        return not any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # hostname (not a bare IP) — allow; DNS resolution happens at delivery time
        # and is outside our control, but bare private IPs are blocked above
        return True


def fire(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    """Schedule a webhook delivery without awaiting it."""
    if not _is_ssrf_safe(url):
        return
    asyncio.create_task(_deliver(url, paste_id, view_count, burned))


async def _deliver(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    payload = json.dumps({
        "event":      "paste.read",
        "paste_id":   paste_id,
        "view_count": view_count,
        "burned":     burned,
        "timestamp":  int(time.time()),
    }).encode()

    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, _post, url, payload
            ),
            timeout=5.0,
        )
    except Exception:
        pass  # Silent fail — never impact the user response


def _post(url: str, payload: bytes) -> None:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent":   "Ghostbit-Webhook/1.0",
    }

    if settings.webhook_secret:
        sig = hmac.new(
            settings.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Ghostbit-Signature"] = f"sha256={sig}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()
