"""Tests for X-Forwarded-For handling in rate_limit.client_ip."""

from unittest.mock import patch

from starlette.requests import Request

from app.rate_limit import client_ip


def _make_request(xff: str | None = None, peer: str = "203.0.113.9") -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345),
    }
    return Request(scope)


def test_peer_used_when_proxy_trust_disabled():
    with patch("app.rate_limit.settings.trust_proxy_headers", False):
        req = _make_request(xff="1.2.3.4", peer="9.9.9.9")
        assert client_ip(req) == "9.9.9.9"


def test_xff_rightmost_used_when_trusted():
    """Multi-entry XFF: the rightmost IP is the one appended by our proxy,
    which is the only hop we trust."""
    with patch("app.rate_limit.settings.trust_proxy_headers", True):
        req = _make_request(xff="198.51.100.10, 203.0.113.7")
        assert client_ip(req) == "203.0.113.7"


def test_xff_spoofing_rejected():
    """Client sends a fake leftmost entry; our proxy appends the real IP.
    Taking the leftmost (previous bug) would return the spoofed value."""
    with patch("app.rate_limit.settings.trust_proxy_headers", True):
        req = _make_request(
            xff="1.2.3.4, 198.51.100.10",  # "1.2.3.4" is client-supplied
            peer="203.0.113.7",
        )
        assert client_ip(req) == "198.51.100.10"


def test_xff_single_entry():
    """Overwrite-style proxy configuration (XFF contains one IP)."""
    with patch("app.rate_limit.settings.trust_proxy_headers", True):
        req = _make_request(xff="203.0.113.7")
        assert client_ip(req) == "203.0.113.7"


def test_xff_absent_falls_back_to_peer():
    with patch("app.rate_limit.settings.trust_proxy_headers", True):
        req = _make_request(xff=None, peer="203.0.113.7")
        assert client_ip(req) == "203.0.113.7"


def test_xff_whitespace_stripped():
    with patch("app.rate_limit.settings.trust_proxy_headers", True):
        req = _make_request(xff="198.51.100.10 ,   203.0.113.7   ")
        assert client_ip(req) == "203.0.113.7"
