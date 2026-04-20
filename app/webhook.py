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
import http.client
import ipaddress
import json
import logging
import socket
import ssl
import time
import urllib.parse

from . import metrics
from .config import settings


class SSRFError(RuntimeError):
    """Raised when a webhook target resolves to a non-public address."""


_log = logging.getLogger("ghostbit.webhook")


def _is_non_public(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    """Return True if `ip` is not a public, globally-routable unicast address.

    Delegates to the stdlib `is_global` property, which covers RFC-1918,
    loopback, link-local, CGNAT (100.64/10), benchmark (198.18/15), TEST-NET,
    reserved, and unspecified ranges. Multicast is also rejected — Python
    considers multicast ranges `is_global=True` but they make no sense as
    unicast webhook targets and could be abused (e.g. flooding).

    Keeping this logic here means we don't ship our own catalogue of ranges
    that drifts whenever a new block gets reserved.
    """
    return (not ip.is_global) or ip.is_multicast


def _resolve_public_ip(host: str, port: int) -> str:
    """Resolve `host` and return a single IP that passes the SSRF filter.

    This is the authoritative check: it runs at delivery time and pins the
    TCP connection to the returned IP, defeating DNS-rebinding attacks where
    `_is_ssrf_safe` sees a public record at creation time and the attacker
    flips the record to a private IP before the webhook fires.

    Policy: if *any* resolved address is private, the whole host is rejected
    (not just the bad IP) — the caller shouldn't be asked to pick a "safe
    one" among a set the attacker controls.

    Raises SSRFError on any failure. Callers must not fall back to hostname-
    based connection if this raises — the whole point is to bypass the
    kernel resolver for the actual request.
    """
    # Bare IP literal: no DNS, validate directly.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        if _is_non_public(addr):
            raise SSRFError(f"refusing non-public IP {host}")
        return host

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"cannot resolve {host}") from exc
    if not infos:
        raise SSRFError(f"no addresses for {host}")

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFError(f"unparseable address {ip_str}") from exc
        if _is_non_public(ip):
            raise SSRFError(f"{host} resolved to non-public IP {ip_str}")

    return infos[0][4][0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that connects to a fixed IP but keeps Host/SNI set
    to the original hostname so TLS cert validation and virtual hosting
    still work correctly."""

    def __init__(
        self, hostname: str, pinned_ip: str, port: int, timeout: float, context: ssl.SSLContext
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), timeout=self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that connects to a fixed IP but keeps the Host header
    set to the original hostname."""

    def __init__(self, hostname: str, pinned_ip: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), timeout=self.timeout)


def _is_ssrf_safe(url: str) -> bool:
    """Return True only if the URL hostname is public (bare IP or resolved DNS).

    This is a pre-check used at paste creation so users get fast feedback on
    an obviously-bad webhook URL. The authoritative check lives in
    `_resolve_public_ip`, which runs at delivery time and pins the TCP
    connection to the validated IP — that's what actually defeats DNS
    rebinding.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if not host:
            return False
        # Fast path: bare IP address
        try:
            addr = ipaddress.ip_address(host)
            return not _is_non_public(addr)
        except ValueError:
            pass
        # Hostname: resolve all returned addresses and reject if any is non-public
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        for info in infos:
            try:
                addr = ipaddress.ip_address(info[4][0])
                if _is_non_public(addr):
                    return False
            except ValueError:
                return False
        return bool(infos)
    except Exception:
        return False


# Hold strong references to in-flight delivery tasks so the event loop
# doesn't garbage-collect them mid-flight. `asyncio.create_task` only keeps
# a weak reference, and a task with no other referrer can be collected
# before it finishes — the webhook would silently never fire. The done
# callback discards the task from the set once delivery completes.
_pending_deliveries: set[asyncio.Task] = set()


def fire(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    """Schedule a webhook delivery without awaiting it."""
    if not _is_ssrf_safe(url):
        metrics.webhook_deliveries_total.labels(outcome="ssrf_blocked").inc()
        return
    task = asyncio.create_task(_deliver(url, paste_id, view_count, burned))
    _pending_deliveries.add(task)
    task.add_done_callback(_pending_deliveries.discard)


async def _deliver(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    payload = json.dumps(
        {
            "event": "paste.read",
            "paste_id": paste_id,
            "view_count": view_count,
            "burned": burned,
            "timestamp": int(time.time()),
        }
    ).encode()

    try:
        await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _post, url, payload),
            timeout=5.0,
        )
        metrics.webhook_deliveries_total.labels(outcome="ok").inc()
    except asyncio.TimeoutError:
        metrics.webhook_deliveries_total.labels(outcome="timeout").inc()
        _log.warning("webhook delivery timed out for paste %s", paste_id)
    except Exception as exc:
        metrics.webhook_deliveries_total.labels(outcome="error").inc()
        _log.warning(
            "webhook delivery failed for paste %s: %s",
            paste_id,
            exc,
        )


def _post(url: str, payload: bytes) -> None:
    """Deliver the webhook, pinning the TCP connection to a re-validated IP.

    We don't use `urllib.request.urlopen` here because it would trigger its
    own name resolution, which is precisely the gap DNS-rebinding exploits.
    Instead we resolve once via `_resolve_public_ip`, reject anything private,
    and connect straight to that IP while keeping Host header + TLS SNI set
    to the original hostname so routing and cert validation still work.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"unsupported scheme {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise SSRFError("missing hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))

    pinned_ip = _resolve_public_ip(host, port)

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "Ghostbit-Webhook/1.0",
    }
    if settings.webhook_secret:
        sig = hmac.new(
            settings.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Ghostbit-Signature"] = f"sha256={sig}"

    if parsed.scheme == "https":
        conn: http.client.HTTPConnection = _PinnedHTTPSConnection(
            host, pinned_ip, port, timeout=5, context=ssl.create_default_context()
        )
    else:
        conn = _PinnedHTTPConnection(host, pinned_ip, port, timeout=5)

    try:
        conn.request("POST", path, body=payload, headers=headers)
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
