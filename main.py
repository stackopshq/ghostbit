import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api import router as api_router
from config import settings
from storage import get_storage

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


app = FastAPI(title="Ghostbit", lifespan=lifespan, docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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
    paste_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
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


@app.post("/{paste_id}/delete")
async def delete_paste(
    request: Request,
    paste_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"),
    key: str = Form(...),
):
    success = await request.app.state.storage.delete(paste_id, key)
    if not success:
        raise HTTPException(status_code=403, detail="Invalid token.")
    return RedirectResponse("/", status_code=303)
