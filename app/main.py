import hashlib
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__, metrics
from .api import router as api_router
from .config import settings
from .languages import codemirror_mode_map, extension_map, slugs
from .rate_limit import limiter
from .storage import get_storage


# Content Security Policy.
#
# script-src uses a per-request nonce: inline <script> tags must carry
# `nonce="{{ request.state.csp_nonce }}"` or they are blocked. This
# neutralises reflected/stored XSS even if an injection point appears,
# because the attacker cannot guess the nonce.
#
# style-src still carries 'unsafe-inline' because the templates use many
# `style="…"` attributes (nonces apply to <style> tags only, not to inline
# attribute styles). Externalising those to CSS classes is a separate
# refactor; until then, style-based attacks remain possible but their
# practical impact is limited (no script execution via CSS in current
# browsers, modulo already-broken setups).
#
# api.github.com is whitelisted for the footer star counter.
def _build_csp(nonce: str) -> str:
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' https://api.github.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate the nonce before dispatching so handlers and templates
        # can read `request.state.csp_nonce`. 128 bits of entropy is well
        # above the "unguessable in a request lifetime" bar.
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", _build_csp(nonce))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), interest-cohort=()",
        )
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before FastAPI parses them.

    Guards against clients that send Content-Length larger than the hard
    ceiling (base64-expanded paste size + headroom for nonce, salt, language,
    webhook URL, JSON overhead). Requests without Content-Length (chunked
    transfer) fall through to the per-field limits enforced by Pydantic.
    """

    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(
                {"detail": f"Request body too large (max {self.max_bytes} bytes)."},
                status_code=413,
            )
        return await call_next(request)


# Paths excluded from the latency histogram to keep /metrics from observing
# itself (scrape storm → infinite feedback) and to keep /healthz scrapes off
# the P99 line, since they're much more frequent than real traffic.
_LATENCY_EXCLUDED_PATHS = {"/metrics", "/healthz"}


class LatencyMiddleware(BaseHTTPMiddleware):
    """Record request latency in the Prometheus histogram.

    Uses the route template (e.g. "/api/v1/pastes/{paste_id}") rather than
    the raw URL so cardinality stays bounded regardless of traffic patterns.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _LATENCY_EXCLUDED_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        template = getattr(route, "path", request.url.path)
        metrics.http_request_duration_seconds.labels(
            method=request.method,
            path=template,
            status=str(response.status_code),
        ).observe(elapsed)
        return response


# Hard HTTP body ceiling: base64-expanded ciphertext (~1.4x) + 8 KB headroom
# for other JSON fields (nonce, salt, language, webhook_url, structure).
_MAX_BODY_BYTES = int(settings.max_paste_size * 1.4) + 8192

_ROOT = Path(__file__).resolve().parent.parent

TTL_OPTIONS = {
    0: "Never",
    3600: "1 hour",
    86400: "1 day",
    604800: "7 days",
    2592000: "30 days",
}

LANGUAGES = slugs()
CM_MODE_MAP = codemirror_mode_map()
EXTENSION_MAP = extension_map()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.storage = await get_storage()
    yield
    await app.state.storage.close()


app = FastAPI(
    title="Ghostbit",
    description=(
        "Self-hosted, end-to-end encrypted paste service.\n\n"
        "All encryption is performed **client-side** (AES-256-GCM). "
        "The server stores ciphertext only and can **never** read paste content.\n\n"
        "The decryption key lives exclusively in the URL `#fragment` — it is never transmitted to the server."
    ),
    version=__version__,
    contact={
        "name": "StackOps HQ",
        "url": "https://github.com/stackopshq/ghostbit",
    },
    license_info={
        "name": "MIT",
        "url": "https://github.com/stackopshq/ghostbit/blob/main/LICENSE",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=_MAX_BODY_BYTES)
app.add_middleware(LatencyMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Prometheus scrape endpoint. Explicit route (not `app.mount`) because
# Starlette's prefix-mount only matches `/metrics/…`, redirecting bare
# `/metrics` to `/metrics/` — scrapers hate redirect chains.
@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    return PlainTextResponse(
        metrics.generate_latest(),
        media_type=metrics.CONTENT_TYPE_LATEST,
    )


_health_log = logging.getLogger("ghostbit.health")


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    # Version is surfaced here so monitoring/ops can read it without parsing
    # the full OpenAPI spec — useful when `podman inspect` labels aren't
    # enough (e.g. confirming the running image matches what was deployed).
    try:
        await request.app.state.storage.ping()
        return JSONResponse(
            {
                "status": "ok",
                "storage": settings.storage_backend,
                "version": __version__,
            }
        )
    except Exception:
        _health_log.exception("storage healthcheck failed")
        return JSONResponse(
            {"status": "error", "storage": settings.storage_backend, "version": __version__},
            status_code=503,
        )


def _security_txt() -> str:
    # Expires must be an ISO 8601 UTC datetime < 1 year away (RFC 9116 §2.5.5).
    # We regenerate it on every request so self-hosters never ship a stale file.
    from datetime import datetime, timedelta, timezone

    expires = (datetime.now(timezone.utc) + timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"Contact: https://github.com/stackopshq/ghostbit/security/advisories/new\n"
        f"Expires: {expires}\n"
        f"Encryption: https://docs.ghostbit.dev/encryption/\n"
        f"Policy: https://github.com/stackopshq/ghostbit/blob/main/SECURITY.md\n"
        f"Preferred-Languages: en, fr\n"
    )


@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    return PlainTextResponse(_security_txt())


_ROBOTS_TXT = "User-agent: *\nDisallow: /api/\nDisallow: /docs\nDisallow: /redoc\n"


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(_ROBOTS_TXT)


app.include_router(api_router)

# Silence uvicorn access logs for /healthz so probes don't pollute logs
logging.getLogger("uvicorn.access").addFilter(
    type(
        "_HealthzFilter",
        (logging.Filter,),
        {"filter": lambda self, r: "/healthz" not in r.getMessage()},
    )()
)
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))


# Cache-busting: short hash of static assets computed once at startup
def _asset_hash() -> str:
    # Recurse so files in static/cm/, static/fonts/, etc. also bust the cache.
    h = hashlib.md5()
    for f in sorted((_ROOT / "static").rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


templates.env.globals["v"] = _asset_hash()

_ERROR_TITLES = {
    404: "Not found",
    403: "Forbidden",
    429: "Too many requests",
    500: "Server error",
}

_ERROR_MESSAGES = {
    404: "This paste has expired, been deleted, or never existed.",
    403: "You don't have permission to access this resource.",
    429: "Slow down! Please wait a moment before trying again.",
    500: "Something went wrong on our end. Please try again later.",
}


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    # Keep JSON responses for API routes
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "error.html",
        context={
            "code": exc.status_code,
            "title": _ERROR_TITLES.get(exc.status_code, "Error"),
            "message": exc.detail
            or _ERROR_MESSAGES.get(exc.status_code, "An unexpected error occurred."),
        },
        status_code=exc.status_code,
    )


def _format_expiry(expires_at: int | None) -> str | None:
    if expires_at is None:
        return None
    delta = expires_at - int(time.time())
    if delta <= 0:
        return "expired"
    if delta < 3600:
        return f"expires in {delta // 60}m"
    if delta < 86400:
        return f"expires in {delta // 3600}h"
    return f"expires in {delta // 86400}d"


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "languages": LANGUAGES,
            "cm_mode_map": CM_MODE_MAP,
            "ttl_options": TTL_OPTIONS,
            "max_paste_size": settings.max_paste_size,
        },
    )


@app.get("/{paste_id}", response_class=HTMLResponse)
async def view_paste(
    request: Request,
    paste_id: str = PathParam(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
):
    storage = request.app.state.storage
    paste = await storage.get(paste_id)

    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found or expired.")

    if paste.is_expired():
        await storage.force_delete(paste_id)
        raise HTTPException(status_code=404, detail="Paste has expired.")

    # Serve the HTML shell only — increment_views, burn, and webhook
    # are handled by api.py when the client fetches the ciphertext.
    return templates.TemplateResponse(
        request,
        "paste.html",
        context={
            "paste": paste,
            "expiry_label": _format_expiry(paste.expires_at),
            "cm_mode_map": CM_MODE_MAP,
            "extension_map": EXTENSION_MAP,
        },
    )


@app.get("/{paste_id}/raw", response_class=HTMLResponse)
async def raw_paste(
    request: Request,
    paste_id: str = PathParam(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
):
    storage = request.app.state.storage
    paste = await storage.get(paste_id)

    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found or expired.")

    if paste.is_expired():
        await storage.force_delete(paste_id)
        raise HTTPException(status_code=404, detail="Paste has expired.")

    # Raw view is not available for password-protected pastes — no way to
    # decrypt without the password, and we don't want to silently expose
    # the ciphertext in a plain-looking page.
    if paste.has_password:
        raise HTTPException(
            status_code=404, detail="Raw view not available for password-protected pastes."
        )

    return templates.TemplateResponse(request, "raw.html", context={"paste": paste})


@app.post("/{paste_id}/delete")
async def delete_paste(
    request: Request,
    paste_id: str = PathParam(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
    key: str = Form(...),
):
    # Unified 403 response whether the paste is missing or the token is wrong,
    # same rationale as the JSON API: avoid leaking paste existence to anyone
    # who can POST a form. The legitimate owner has the token, so they always
    # hit the success path.
    storage = request.app.state.storage
    if not await storage.delete(paste_id, key):
        raise HTTPException(status_code=403, detail="Invalid delete token.")
    return RedirectResponse("/", status_code=303)
