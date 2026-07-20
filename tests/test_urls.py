"""Unit tests for absolute-URL construction.

Kept out of test_api.py deliberately. That module owns a module-scoped async
`client` fixture bound to a module-scoped event loop; a synchronous test sitting
in the middle of it made pytest finalize that fixture early, and the finalizer
then tried to close the Redis connection on an already-closed loop
("RuntimeError: Event loop is closed"). These tests touch neither the client nor
the loop, so they belong in a module with no async fixtures at all.
"""

from app.config import settings
from app.main import _abs_url


class _Req:
    base_url = "http://internal:8000/"


def test_abs_url_prefers_configured_base_url(monkeypatch):
    """BASE_URL, when set, overrides the request-derived origin — the escape
    hatch for TLS-terminating proxies that would otherwise emit http:// URLs."""
    monkeypatch.setattr(settings, "base_url", "https://paste.example.com")
    assert _abs_url(_Req(), "/static/og-banner.png") == (
        "https://paste.example.com/static/og-banner.png"
    )

    monkeypatch.setattr(settings, "base_url", "")
    assert _abs_url(_Req(), "/static/og-banner.png") == (
        "http://internal:8000/static/og-banner.png"
    )
