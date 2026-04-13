"""
REST API — /api/v1

All encryption is performed CLIENT-SIDE (E2E). The server stores ciphertext only
and can never read paste content.

Endpoints:
  POST   /api/v1/pastes          Create a paste (send pre-encrypted content)
  GET    /api/v1/pastes/{id}     Get a paste (returns ciphertext — client decrypts)
  DELETE /api/v1/pastes/{id}     Delete a paste (requires X-Delete-Token header)
  POST   /api/v1/detect          Detect language of a plaintext snippet
"""

import hashlib
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Path, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings
from .detect import detect_language
from .storage.base import PasteData
from . import webhook
from .webhook import _is_ssrf_safe

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1", tags=["Pastes"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PasteCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Base64 AES-256-GCM ciphertext (client-encrypted).")
    nonce: str                    = Field(..., description="Base64 12-byte GCM nonce.")
    kdf_salt: Optional[str]       = Field(None, description="Base64 PBKDF2 salt. Present only for password-protected pastes.")
    language: Optional[str]       = None
    expires_in: Optional[int]     = Field(None, ge=1, description="TTL in seconds (≥ 1). Null = never.")
    burn: bool                    = False
    max_views: Optional[int]      = Field(None, ge=1, description="Delete after N views.")
    webhook_url: Optional[str]    = Field(None, description="URL to POST when the paste is read.")


class PasteCreateResponse(BaseModel):
    id: str
    url: str
    delete_token: str
    expires_at: Optional[int]
    burn: bool
    max_views: Optional[int]


class PasteResponse(BaseModel):
    id: str
    content: str              # base64 AES-256-GCM ciphertext
    nonce: str                # base64 12-byte GCM nonce
    kdf_salt: Optional[str]   # base64 PBKDF2 salt (password pastes only)
    language: Optional[str]
    created_at: int
    expires_at: Optional[int]
    burn: bool
    max_views: Optional[int]
    view_count: int
    has_password: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _storage(request: Request):
    return request.app.state.storage

def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/pastes",
    response_model=PasteCreateResponse,
    status_code=201,
    summary="Create a paste",
    description=(
        "Create a new end-to-end encrypted paste.\n\n"
        "The `content` field must be a **Base64-encoded AES-256-GCM ciphertext** produced client-side "
        "(use the CLI or `e2e.js`). The server never sees the plaintext.\n\n"
        "Returns the paste ID, its public URL, and a one-time `delete_token`."
    ),
    responses={
        400: {"description": "Content too large or invalid webhook URL."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(lambda: settings.rate_limit_create)
async def create_paste(body: PasteCreateRequest, request: Request):
    # Content is base64 ciphertext; max size check with base64 overhead (~4/3 expansion)
    max_b64 = int(settings.max_paste_size * 1.4)
    if len(body.content) > max_b64:
        raise HTTPException(400, f"Content too large (max {settings.max_paste_size // 1024} KB).")

    if body.webhook_url and not _is_ssrf_safe(body.webhook_url):
        raise HTTPException(400, "Invalid webhook URL.")

    delete_token = secrets.token_urlsafe(16)
    delete_token_hash = hashlib.sha256(delete_token.encode()).hexdigest()

    now = int(time.time())
    expires_at = now + body.expires_in if body.expires_in else None

    paste = PasteData(
        id=secrets.token_urlsafe(6),
        content=body.content,
        nonce=body.nonce,
        kdf_salt=body.kdf_salt,
        language=body.language,
        created_at=now,
        expires_at=expires_at,
        burn=body.burn,
        has_password=body.kdf_salt is not None,
        delete_token_hash=delete_token_hash,
        max_views=body.max_views,
        view_count=0,
        webhook_url=body.webhook_url,
    )

    await _storage(request).save(paste)

    return PasteCreateResponse(
        id=paste.id,
        url=f"{_base_url(request)}/{paste.id}",
        delete_token=delete_token,
        expires_at=expires_at,
        burn=paste.burn,
        max_views=paste.max_views,
    )


@router.get(
    "/pastes/{paste_id}",
    response_model=PasteResponse,
    summary="Retrieve a paste",
    description=(
        "Returns the ciphertext and metadata for a paste.\n\n"
        "The caller is responsible for **decrypting the content** using the key stored in the URL `#fragment`.\n\n"
        "This call counts as a view: burn-after-read and max-views pastes are deleted once the threshold is reached.\n\n"
        "If a webhook URL was set at creation, a notification is fired after this call."
    ),
    responses={
        404: {"description": "Paste not found, expired, or already burned."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(lambda: settings.rate_limit_view)
async def get_paste(paste_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"), request: Request = None):
    storage = _storage(request)
    paste = await storage.get(paste_id)

    if paste is None:
        raise HTTPException(404, "Paste not found or expired.")

    if paste.expires_at and int(time.time()) > paste.expires_at:
        await storage.force_delete(paste_id)
        raise HTTPException(404, "Paste has expired.")

    view_count = await storage.increment_views(paste_id)

    burned = paste.burn or (paste.max_views and view_count >= paste.max_views)
    if burned:
        await storage.force_delete(paste_id)

    if paste.webhook_url:
        webhook.fire(paste.webhook_url, paste_id, view_count, bool(burned))

    return PasteResponse(
        id=paste.id,
        content=paste.content,
        nonce=paste.nonce,
        kdf_salt=paste.kdf_salt,
        language=paste.language,
        created_at=paste.created_at,
        expires_at=paste.expires_at,
        burn=paste.burn,
        max_views=paste.max_views,
        view_count=view_count,
        has_password=paste.has_password,
    )


class DetectRequest(BaseModel):
    content: str

class DetectResponse(BaseModel):
    language: Optional[str]

@router.post(
    "/detect",
    response_model=DetectResponse,
    summary="Detect language",
    description=(
        "Attempt to detect the programming language of a **plaintext** snippet.\n\n"
        "Uses a two-stage strategy: fast regex patterns first, then a Pygments heuristic fallback "
        "for longer content. Returns `null` if confidence is too low."
    ),
    tags=["Utilities"],
)
@limiter.limit(lambda: settings.rate_limit_view)
async def detect(body: DetectRequest, request: Request):
    return DetectResponse(language=detect_language(body.content))


@router.delete(
    "/pastes/{paste_id}",
    status_code=204,
    summary="Delete a paste",
    description=(
        "Permanently delete a paste.\n\n"
        "Requires the `X-Delete-Token` header returned at creation time. "
        "The token is verified against a SHA-256 hash — the plaintext token is never stored."
    ),
    responses={
        403: {"description": "Invalid or missing delete token."},
        404: {"description": "Paste not found."},
    },
)
async def delete_paste(paste_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,20}$"), request: Request = None, x_delete_token: str = Header(..., description="Delete token returned at paste creation.")):
    storage = _storage(request)
    paste = await storage.get(paste_id)
    if paste is None:
        raise HTTPException(404, "Paste not found.")
    success = await storage.delete(paste_id, x_delete_token)
    if not success:
        raise HTTPException(403, "Invalid delete token.")
