# API

Base URL: `https://your-instance.com/api/v1`

Interactive docs are available at `/api` on any running instance.

---

## POST /pastes

Create a paste. Content must be **pre-encrypted client-side** (AES-256-GCM).

```http
POST /api/v1/pastes
Content-Type: application/json
```

### Request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | **Yes** | Base64 AES-256-GCM ciphertext |
| `nonce` | string | **Yes** | Base64 12-byte GCM nonce |
| `kdf_salt` | string | No | Base64 PBKDF2 salt — present only for password-protected pastes |
| `language` | string | No | Language hint for syntax highlighting |
| `expires_in` | integer | No | TTL in seconds (≥ 1) |
| `burn` | boolean | No | Delete after first view. Default: `false` |
| `max_views` | integer | No | Delete after N views (≥ 1) |
| `webhook_url` | string | No | URL to POST on each read |

### Response `201`

```json
{
  "id": "aB3kZx9m",
  "url": "https://your-instance.com/aB3kZx9m",
  "delete_token": "rA8mXvLqP2wKjN5sYtUcFg",
  "expires_at": 1716000000,
  "burn": false,
  "max_views": null
}
```

!!! warning "Save the delete token"
    The `delete_token` is shown only once. Append it to the URL fragment to enable the delete button in the UI.

---

## GET /pastes/{id}

Fetch a paste. This counts as a view — burn and max_views are evaluated server-side.

```http
GET /api/v1/pastes/{id}
```

### Response `200`

```json
{
  "id": "aB3kZx9m",
  "content": "<base64 ciphertext>",
  "nonce": "<base64 nonce>",
  "kdf_salt": null,
  "language": "python",
  "created_at": 1715900000,
  "expires_at": 1716000000,
  "burn": false,
  "max_views": 5,
  "view_count": 2,
  "has_password": false
}
```

### Errors

| Code | Reason |
|------|--------|
| `404` | Paste not found, expired, or already burned |

---

## DELETE /pastes/{id}

Delete a paste using the token issued at creation.

```http
DELETE /api/v1/pastes/{id}
X-Delete-Token: rA8mXvLqP2wKjN5sYtUcFg
```

### Response

| Code | Meaning |
|------|---------|
| `204` | Deleted |
| `403` | Invalid token |
| `404` | Paste not found |
| `422` | Missing `X-Delete-Token` header |

---

## POST /detect

Detect the language of a plaintext snippet. Used by the UI for auto-detection.

```http
POST /api/v1/detect
Content-Type: application/json

{ "content": "import os\nimport sys\n..." }
```

### Response `200`

```json
{ "language": "python" }
```

Returns `null` if the snippet is too short or the language cannot be determined.

---

## Webhook payload

When `webhook_url` is set, Ghostbit sends a `POST` request on each view:

```json
{
  "event": "paste.read",
  "paste_id": "aB3kZx9m",
  "view_count": 3,
  "burned": false,
  "timestamp": 1715900123
}
```

The request has a 5-second timeout and is fire-and-forget (failures are not retried).

### Webhook signature

If `WEBHOOK_SECRET` is configured on the server, every delivery includes an HMAC-SHA256 signature:

```
X-Ghostbit-Signature: sha256=<hex>
```

The signature is computed over the raw JSON body. Verify it on the receiving end:

```python
import hmac, hashlib

def verify(secret: str, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

Always use constant-time comparison to prevent timing attacks. See the [Encryption](encryption.md#webhook-signatures) page for more details and Node.js examples.

---

## Example — create and read with curl

```bash
# Encrypt client-side first (or use the CLI: gbit --json)
gbit file.py --json
# {
#   "id": "aB3kZx9m",
#   "full_url": "https://…/aB3kZx9m#KEY~DELETE_TOKEN",
#   …
# }

# Delete
curl -X DELETE https://your-instance.com/api/v1/pastes/aB3kZx9m \
  -H "X-Delete-Token: rA8mXvLqP2wKjN5sYtUcFg"
```
