"""Tests for SSRF protection in webhook.py."""

import socket
from unittest.mock import patch

import pytest

from app.webhook import SSRFError, _is_ssrf_safe, _resolve_public_ip

# Fake getaddrinfo that returns a public IP for any hostname lookup,
# so tests are deterministic regardless of CI DNS availability.
_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 0))]
_PRIVATE_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]


def _fake_getaddrinfo(host, port, *args, **kwargs):
    """Return a public IP for any hostname, simulating successful DNS."""
    return _PUBLIC_ADDRINFO


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/hook",
        "http://172.16.5.5/hook",
        "http://192.168.1.1/hook",
        "http://127.0.0.1/hook",
        "http://169.254.169.254/hook",  # AWS/GCP/Azure IMDS endpoint
        "https://10.255.255.255/hook",
        "ftp://example.com/hook",  # non-http scheme
        "http://0.0.0.0/hook",  # unspecified — resolves to localhost on Linux
        "http://100.64.1.1/hook",  # CGNAT (RFC 6598)
        "http://198.18.0.1/hook",  # benchmark (RFC 2544)
        "http://192.0.2.1/hook",  # TEST-NET-1
        "http://198.51.100.1/hook",  # TEST-NET-2
        "http://203.0.113.1/hook",  # TEST-NET-3
        "http://224.0.0.1/hook",  # multicast
        "http://[::1]/hook",  # IPv6 loopback
        "http://[fe80::1]/hook",  # IPv6 link-local
        "http://[fc00::1]/hook",  # IPv6 ULA
        "http://[::]/hook",  # IPv6 unspecified
    ],
)
def test_ssrf_blocked(url):
    assert _is_ssrf_safe(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://hooks.example.com/notify",
        "https://discord.com/api/webhooks/123/abc",
        "http://1.2.3.4/hook",  # public IP
    ],
)
def test_ssrf_allowed(url):
    with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo):
        assert _is_ssrf_safe(url) is True


# ── DNS rebinding defense (authoritative delivery-time check) ────────────────


def test_resolve_public_ip_accepts_public_dns():
    with patch("socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
        assert _resolve_public_ip("hooks.example.com", 443) == "93.184.215.14"


def test_resolve_public_ip_accepts_bare_public_ip_without_dns():
    # Bare IP literal must not trigger DNS — protects against spoofed resolvers
    # and keeps the fast path deterministic.
    with patch("socket.getaddrinfo", side_effect=AssertionError("DNS must not be called")):
        assert _resolve_public_ip("1.2.3.4", 443) == "1.2.3.4"


def test_resolve_public_ip_rejects_bare_private_ip():
    with pytest.raises(SSRFError):
        _resolve_public_ip("127.0.0.1", 443)


def test_resolve_public_ip_rejects_rebound_hostname():
    """DNS rebinding: `_is_ssrf_safe` saw a public IP at creation, the
    attacker flipped the record to a private IP before delivery. The
    delivery-time re-check must catch it."""
    with (
        patch("socket.getaddrinfo", return_value=_PRIVATE_ADDRINFO),
        pytest.raises(SSRFError, match="non-public IP"),
    ):
        _resolve_public_ip("attacker.example.com", 443)


def test_resolve_public_ip_rejects_mixed_result():
    """If one returned record is private, reject the whole host — we don't
    trust the attacker to let us pick the 'safe' one."""
    mixed = _PUBLIC_ADDRINFO + _PRIVATE_ADDRINFO
    with patch("socket.getaddrinfo", return_value=mixed), pytest.raises(SSRFError):
        _resolve_public_ip("mixed.example.com", 443)


def test_resolve_public_ip_raises_on_nxdomain():
    with (
        patch("socket.getaddrinfo", side_effect=socket.gaierror("no such host")),
        pytest.raises(SSRFError),
    ):
        _resolve_public_ip("nope.invalid", 443)


# ── Fire-and-forget task lifecycle ───────────────────────────────────────────


@pytest.mark.anyio
async def test_fire_keeps_strong_reference_to_delivery_task():
    """`fire()` must keep a strong reference to the created task so the event
    loop doesn't garbage-collect it mid-delivery. Without it, a delivery
    could silently never run — the task object is the only thing holding
    the coroutine alive."""
    import asyncio

    from app import webhook

    # Make `_post` a slow no-op so the task is still pending when we inspect.
    async def slow_post(*_args, **_kwargs):
        await asyncio.sleep(0.05)

    with patch.object(webhook, "_deliver", slow_post):
        webhook._pending_deliveries.clear()
        webhook.fire("http://1.2.3.4/hook", "abc", 1, False)
        assert len(webhook._pending_deliveries) == 1
        # Let the task finish; the done-callback must discard it from the set.
        await asyncio.sleep(0.1)
        assert len(webhook._pending_deliveries) == 0
