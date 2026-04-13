"""Tests for SSRF protection in webhook.py."""

import socket
from unittest.mock import patch

import pytest
from app.webhook import _is_ssrf_safe

# Fake getaddrinfo that returns a public IP for any hostname lookup,
# so tests are deterministic regardless of CI DNS availability.
_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 0))]


def _fake_getaddrinfo(host, port, *args, **kwargs):
    """Return a public IP for any hostname, simulating successful DNS."""
    return _PUBLIC_ADDRINFO


@pytest.mark.parametrize("url", [
    "http://10.0.0.1/hook",
    "http://172.16.5.5/hook",
    "http://192.168.1.1/hook",
    "http://127.0.0.1/hook",
    "http://169.254.169.254/hook",      # AWS metadata endpoint
    "https://10.255.255.255/hook",
    "ftp://example.com/hook",           # non-http scheme
])
def test_ssrf_blocked(url):
    assert _is_ssrf_safe(url) is False


@pytest.mark.parametrize("url", [
    "https://hooks.example.com/notify",
    "https://discord.com/api/webhooks/123/abc",
    "http://1.2.3.4/hook",             # public IP
])
def test_ssrf_allowed(url):
    with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo):
        assert _is_ssrf_safe(url) is True
