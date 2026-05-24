"""Integration tests for the REST API."""

import base64
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("STORAGE_BACKEND", "sqlite")
# Use a temp file so tests work in any environment (CI has no /data/)
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tmp_db:
    os.environ["SQLITE_PATH"] = _tmp_db.name

from app.main import app  # noqa: E402
from app.storage import get_storage  # noqa: E402


@pytest_asyncio.fixture(scope="module")
async def client():
    # Manually initialize storage so lifespan side-effects are covered
    app.state.storage = await get_storage()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.storage.close()


def _fake_paste(**kwargs):
    key = os.urandom(32)
    nonce = os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ct = AESGCM(key).encrypt(nonce, b"hello world", None)
    return {
        "content": base64.b64encode(ct).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "burn": False,
        **kwargs,
    }


@pytest.mark.anyio
async def test_healthz(client):
    from app import __version__

    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # Surface the running version for monitoring tools that don't want to
    # fetch /openapi.json just to know which build they're hitting.
    assert body["version"] == __version__


@pytest.mark.anyio
async def test_healthz_stays_200_when_storage_is_down(client, monkeypatch):
    """Liveness MUST NOT depend on the storage backend — a Redis blip should
    not cascade into a container restart loop."""

    async def boom():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(app.state.storage, "ping", boom)
    r = await client.get("/healthz")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_readyz_200_when_storage_up(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_readyz_503_when_storage_down(client, monkeypatch):
    """Readiness must flip to 503 so the ingress drains traffic until the
    backend recovers."""

    async def boom():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(app.state.storage, "ping", boom)
    r = await client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "error"


@pytest.mark.anyio
async def test_csp_uses_nonce_not_unsafe_inline(client):
    """script-src must be nonce-based, not 'unsafe-inline'. A weakening
    of this header would silently re-enable XSS via any injection point."""
    r = await client.get("/")
    csp = r.headers.get("content-security-policy", "")
    assert "script-src" in csp
    # Extract the script-src directive
    script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
    assert "'nonce-" in script_src
    assert "'unsafe-inline'" not in script_src


@pytest.mark.anyio
async def test_csp_nonce_is_per_request(client):
    """Nonces must be unique per response — reuse would let an attacker
    who saw one nonce reuse it on later injections."""
    import re

    r1 = await client.get("/")
    r2 = await client.get("/")
    nonce_re = re.compile(r"'nonce-([^']+)'")
    n1 = nonce_re.search(r1.headers["content-security-policy"]).group(1)
    n2 = nonce_re.search(r2.headers["content-security-policy"]).group(1)
    assert n1 != n2
    # And the HTML must carry the same nonce as the header.
    assert f'nonce="{n1}"' in r1.text


@pytest.mark.anyio
async def test_homepage_og_image_is_absolute_banner(client):
    """Link unfurls need an absolute og:image. A relative URL (or the portrait
    logo) is what made iMessage render a huge blown-up icon."""
    html = (await client.get("/")).text
    assert 'property="og:image" content="http://test/static/og-banner.png"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html


@pytest.mark.anyio
async def test_paste_page_omits_og_image(client):
    """Paste pages carry no og:image on purpose, so unfurls fall back to the
    compact card instead of stretching an image into the hero slot."""
    pid = (await client.post("/api/v1/pastes", json=_fake_paste())).json()["id"]
    html = (await client.get(f"/{pid}")).text
    assert "og:image" not in html
    assert 'name="twitter:card" content="summary"' in html


@pytest.mark.anyio
async def test_paste_page_emits_sri_for_third_party_libs(client):
    """Third-party scripts on the paste page carry SRI hashes so a tampered
    file in /static/ (or a compromised CDN if we ever front it) fails to load
    instead of executing silently."""
    pid = (await client.post("/api/v1/pastes", json=_fake_paste())).json()["id"]
    html = (await client.get(f"/{pid}")).text
    assert 'integrity="sha384-' in html
    assert 'crossorigin="anonymous"' in html


@pytest.mark.anyio
async def test_compressed_flag_round_trips(client):
    """compressed is a server-transparent metadata flag — it must persist
    through save/load exactly as the client sent it, with no coercion."""
    r = await client.post("/api/v1/pastes", json=_fake_paste(compressed=True))
    assert r.status_code == 201
    pid = r.json()["id"]
    g = await client.get(f"/api/v1/pastes/{pid}")
    assert g.json()["compressed"] is True


@pytest.mark.anyio
async def test_compressed_flag_defaults_to_false(client):
    """Pastes created without the flag must come back with compressed=False —
    backwards compatibility for clients and existing pastes."""
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    pid = r.json()["id"]
    g = await client.get(f"/api/v1/pastes/{pid}")
    assert g.json()["compressed"] is False


@pytest.mark.anyio
async def test_paste_page_ships_qr_button_modal_and_lib(client):
    """QR code is rendered client-side so the URL fragment (encryption key)
    never reaches the server. The button + modal + lib must be in the shell;
    the lib must carry SRI like the other third-party scripts."""
    import re

    pid = (await client.post("/api/v1/pastes", json=_fake_paste())).json()["id"]
    html = (await client.get(f"/{pid}")).text
    assert 'id="qrBtn"' in html
    assert 'id="qrModal"' in html
    m = re.search(r'/static/qrcode\.min\.js[^>]+integrity="sha384-[A-Za-z0-9+/=]+"', html)
    assert m, "qrcode.min.js should ship with SRI"


def test_abs_url_prefers_configured_base_url(monkeypatch):
    """BASE_URL, when set, overrides the request-derived origin — the escape
    hatch for TLS-terminating proxies that would otherwise emit http:// URLs."""
    from app.config import settings
    from app.main import _abs_url

    class _Req:
        base_url = "http://internal:8000/"

    monkeypatch.setattr(settings, "base_url", "https://paste.example.com")
    assert _abs_url(_Req(), "/static/og-banner.png") == (
        "https://paste.example.com/static/og-banner.png"
    )

    monkeypatch.setattr(settings, "base_url", "")
    assert _abs_url(_Req(), "/static/og-banner.png") == (
        "http://internal:8000/static/og-banner.png"
    )


@pytest.mark.anyio
async def test_create_and_get_paste(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert "delete_token" in data

    r2 = await client.get(f"/api/v1/pastes/{data['id']}")
    assert r2.status_code == 200
    assert r2.json()["id"] == data["id"]


@pytest.mark.anyio
async def test_burn_after_read(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(burn=True))
    paste_id = r.json()["id"]

    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 404


@pytest.mark.anyio
async def test_max_views(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(max_views=2))
    paste_id = r.json()["id"]

    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 404


@pytest.mark.anyio
async def test_delete_with_valid_token(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    data = r.json()
    r2 = await client.delete(
        f"/api/v1/pastes/{data['id']}",
        headers={"X-Delete-Token": data["delete_token"]},
    )
    assert r2.status_code == 204
    assert (await client.get(f"/api/v1/pastes/{data['id']}")).status_code == 404


@pytest.mark.anyio
async def test_delete_with_invalid_token(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    r2 = await client.delete(
        f"/api/v1/pastes/{r.json()['id']}",
        headers={"X-Delete-Token": "wrongtoken"},
    )
    assert r2.status_code == 403


@pytest.mark.anyio
async def test_update_paste_replaces_ciphertext(client):
    """The PUT endpoint lets the owner change the ciphertext while keeping
    the same id and metadata — used by the in-place edit flow."""
    r = await client.post("/api/v1/pastes", json=_fake_paste(language="python"))
    data = r.json()
    original = await client.get(f"/api/v1/pastes/{data['id']}")
    new_payload = _fake_paste()  # fresh ciphertext + nonce
    u = await client.put(
        f"/api/v1/pastes/{data['id']}",
        json={"content": new_payload["content"], "nonce": new_payload["nonce"]},
        headers={"X-Delete-Token": data["delete_token"]},
    )
    assert u.status_code == 204
    after = await client.get(f"/api/v1/pastes/{data['id']}")
    j = after.json()
    assert j["content"] == new_payload["content"]
    assert j["nonce"] == new_payload["nonce"]
    # Metadata that must NOT change on edit.
    assert j["language"] == "python"
    assert j["created_at"] == original.json()["created_at"]
    assert j["has_password"] == original.json()["has_password"]


@pytest.mark.anyio
async def test_update_paste_invalid_token_returns_403(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    pid = r.json()["id"]
    new_payload = _fake_paste()
    u = await client.put(
        f"/api/v1/pastes/{pid}",
        json={"content": new_payload["content"], "nonce": new_payload["nonce"]},
        headers={"X-Delete-Token": "definitely-not-it"},
    )
    assert u.status_code == 403


@pytest.mark.anyio
async def test_update_unknown_paste_returns_403(client):
    """Same enumeration-resistance policy as DELETE: missing-vs-wrong-token
    must be indistinguishable to a caller."""
    new_payload = _fake_paste()
    u = await client.put(
        "/api/v1/pastes/doesnotexist",
        json={"content": new_payload["content"], "nonce": new_payload["nonce"]},
        headers={"X-Delete-Token": "anything"},
    )
    assert u.status_code == 403


@pytest.mark.anyio
async def test_update_can_flip_compressed_flag(client):
    """A re-encrypt path that turns compression on (or off) must be able to
    persist the new flag — otherwise the viewer would gunzip wrong bytes."""
    r = await client.post("/api/v1/pastes", json=_fake_paste(compressed=False))
    data = r.json()
    new_payload = _fake_paste()
    await client.put(
        f"/api/v1/pastes/{data['id']}",
        json={
            "content": new_payload["content"],
            "nonce": new_payload["nonce"],
            "compressed": True,
        },
        headers={"X-Delete-Token": data["delete_token"]},
    )
    assert (await client.get(f"/api/v1/pastes/{data['id']}")).json()["compressed"] is True


@pytest.mark.anyio
async def test_delete_of_unknown_paste_also_returns_403(client):
    """The API must not distinguish 'paste exists with wrong token' from
    'paste does not exist' — otherwise an attacker can enumerate IDs by
    probing with an arbitrary token."""
    r = await client.delete(
        "/api/v1/pastes/doesnotexist",
        headers={"X-Delete-Token": "anything"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_form_delete_of_unknown_paste_also_returns_403(client):
    """Same policy for the HTML form endpoint — the form is the legitimate
    owner path, but we still avoid leaking existence to anyone who can POST."""
    r = await client.post(
        "/doesnotexist/delete",
        data={"key": "anything"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_ssrf_webhook_blocked(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(webhook_url="http://192.168.1.1/hook"))
    assert r.status_code == 400


@pytest.mark.anyio
async def test_content_too_large(client):
    payload = {
        "content": "A" * (1024 * 1024),
        "nonce": base64.b64encode(os.urandom(12)).decode(),
    }
    r = await client.post("/api/v1/pastes", json=payload)
    # 413 from the body-size middleware (hard HTTP ceiling) or 400 from the
    # application-level max_paste_size check — both are acceptable rejections.
    assert r.status_code in (400, 413)


@pytest.mark.anyio
async def test_security_txt(client):
    r = await client.get("/.well-known/security.txt")
    assert r.status_code == 200
    assert "Contact:" in r.text


@pytest.mark.anyio
async def test_id_collision_retry(client, monkeypatch):
    """When the random ID generator collides, create_paste should retry
    up to 8 times before giving up — it must never overwrite an existing paste."""
    # Force the generator to return a colliding ID twice, then a fresh one.
    import secrets as _secrets

    from app import api as api_mod

    first = await client.post("/api/v1/pastes", json=_fake_paste())
    assert first.status_code == 201
    taken_id = first.json()["id"]

    calls = {"n": 0}
    real_token_urlsafe = _secrets.token_urlsafe

    def fake_token_urlsafe(nbytes):
        # 6-byte tokens are only used for paste IDs; 16-byte ones are delete tokens.
        if nbytes == 6 and calls["n"] < 2:
            calls["n"] += 1
            return taken_id
        return real_token_urlsafe(nbytes)

    monkeypatch.setattr(api_mod.secrets, "token_urlsafe", fake_token_urlsafe)

    r = await client.post("/api/v1/pastes", json=_fake_paste())
    assert r.status_code == 201
    assert r.json()["id"] != taken_id
    assert calls["n"] == 2  # proves we actually retried past the collisions


@pytest.mark.anyio
async def test_security_headers_present(client):
    r = await client.get("/")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "default-src 'self'" in r.headers.get("content-security-policy", "")
