"""Tests for SSRF protection in webhook.py."""

import pytest
from webhook import _is_ssrf_safe


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
    assert _is_ssrf_safe(url) is True
