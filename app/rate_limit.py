"""
Rate-limit key extraction.

When TRUST_PROXY_HEADERS is false (default), the direct peer address is used.
When true, the first IP from X-Forwarded-For is used — operators must ensure
their reverse proxy strips or rewrites this header, otherwise clients can
spoof it and bypass per-IP limits.
"""

from fastapi import Request
from slowapi.util import get_remote_address

from .config import settings


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
    return get_remote_address(request)
