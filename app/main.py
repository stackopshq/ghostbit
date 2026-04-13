import hashlib
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Path as PathParam, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api import router as api_router
from .config import settings
from .storage import get_storage

_ROOT = Path(__file__).resolve().parent.parent

limiter = Limiter(key_func=get_remote_address)

TTL_OPTIONS = {
    0: "Never",
    3600: "1 hour",
    86400: "1 day",
    604800: "7 days",
    2592000: "30 days",
}

LANGUAGES = [
    "", "bash", "c", "cpp", "csharp", "css", "diff", "dockerfile",
    "go", "html", "java", "javascript", "json", "kotlin", "lua",
    "makefile", "markdown", "php", "python", "ruby", "rust", "sql",
    "swift", "toml", "typescript", "xml", "yaml",
]


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
    version="1.1.1",
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    try:
        await request.app.state.storage.ping()
        return JSONResponse({"status": "ok", "storage": settings.storage_backend})
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "storage": settings.storage_backend, "detail": str(exc)},
            status_code=503,
        )


_SECURITY_TXT = """\
Contact: https://github.com/stackopshq/ghostbit/security/advisories/new
Encryption: https://docs.ghostbit.dev/encryption/
Policy: https://github.com/stackopshq/ghostbit/blob/main/SECURITY.md
Preferred-Languages: en, fr
"""

@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    return PlainTextResponse(_SECURITY_TXT)


_ROBOTS_TXT = """User-agent: *\nDisallow: /api/\nDisallow: /docs\nDisallow: /redoc\nAllow: /$\nSitemap:\n"""

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(_ROBOTS_TXT)


app.include_router(api_router)

# Silence uvicorn access logs for /healthz so probes don't pollute logs
logging.getLogger("uvicorn.access").addFilter(
    type("_HealthzFilter", (logging.Filter,), {
        "filter": lambda self, r: "/healthz" not in r.getMessage()
    })()
)
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))

# Cache-busting: short hash of static assets computed once at startup
def _asset_hash() -> str:
    h = hashlib.md5()
    for f in sorted((_ROOT / "static").glob("*")):
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
            "message": exc.detail or _ERROR_MESSAGES.get(exc.status_code, "An unexpected error occurred."),
        },
        status_code=exc.status_code,
    )


def _format_expiry(expires_at: Optional[int]) -> Optional[str]:
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

@app.get("/api", response_class=HTMLResponse)
async def api_docs(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "api_docs.html", context={"base_url": base_url})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html",
        context={"languages": LANGUAGES, "ttl_options": TTL_OPTIONS, "max_paste_size": settings.max_paste_size},
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

    if paste.expires_at and int(time.time()) > paste.expires_at:
        await storage.force_delete(paste_id)
        raise HTTPException(status_code=404, detail="Paste has expired.")

    # Serve the HTML shell only — increment_views, burn, and webhook
    # are handled by api.py when the client fetches the ciphertext.
    return templates.TemplateResponse(
        request, "paste.html",
        context={
            "paste": paste,
            "expiry_label": _format_expiry(paste.expires_at),
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

    if paste.expires_at and int(time.time()) > paste.expires_at:
        await storage.force_delete(paste_id)
        raise HTTPException(status_code=404, detail="Paste has expired.")

    # Raw view is not available for password-protected pastes — no way to
    # decrypt without the password, and we don't want to silently expose
    # the ciphertext in a plain-looking page.
    if paste.has_password:
        raise HTTPException(status_code=404, detail="Raw view not available for password-protected pastes.")

    return templates.TemplateResponse(request, "raw.html", context={"paste": paste})


@app.post("/{paste_id}/delete")
async def delete_paste(
    request: Request,
    paste_id: str = PathParam(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
    key: str = Form(...),
):
    storage = request.app.state.storage
    paste = await storage.get(paste_id)
    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found.")
    success = await storage.delete(paste_id, key)
    if not success:
        raise HTTPException(status_code=403, detail="Invalid delete token.")
    return RedirectResponse("/", status_code=303)
