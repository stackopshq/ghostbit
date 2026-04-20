"""
Rate-limit key extraction.

When TRUST_PROXY_HEADERS is false (default), the direct peer address is used.

When true, the *rightmost* X-Forwarded-For entry is used — this is the IP
appended by the nearest hop, which is our own reverse proxy. Leftmost entries
are client-controlled: a client that sends `X-Forwarded-For: 1.2.3.4` would
have that spoofed value keyed for rate limiting if we took the first entry
(the historical bug).

Limitation for multi-hop setups (CDN → LB → app): the rightmost entry is
the LB, so rate limits will apply globally to the LB, not per-client. In
that case, configure the reverse proxy to collapse the chain (Nginx:
`set_real_ip_from <CDN range>; real_ip_header X-Forwarded-For;`) so XFF
reaches us with a single trusted hop.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            last = xff.rsplit(",", 1)[-1].strip()
            if last:
                return last
    return get_remote_address(request)


# Single Limiter instance used by both the HTTP app (main.py) and the API
# router (api.py). slowapi routes decorator-registered limits through the
# instance attached to `app.state.limiter`; keeping two separate instances
# worked only because the instance wiring happens at decoration time, but
# it meant runtime config changes applied to one and not the other.
limiter = Limiter(key_func=client_ip)
