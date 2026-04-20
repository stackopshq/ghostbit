"""Client-side crypto — mirrors the browser's static/e2e.js behaviour.

Any parameter change here (PBKDF2 iterations, AES mode, nonce length,
salt length) must be reflected in static/e2e.js and in the app/api.py
validators, or pastes created by one side will be unreadable by the
other. See tests/test_cli_crypto.py for the contract.
"""

from __future__ import annotations

import base64
import os
import sys

try:
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

_PBKDF2_ITERATIONS = 600_000


def require_crypto() -> None:
    """Abort with an actionable message if `cryptography` is missing."""
    if not _CRYPTO_OK:
        print(
            "Error: 'cryptography' package required. Run: pip install cryptography",
            file=sys.stderr,
        )
        sys.exit(1)


def gen_key() -> bytes:
    return os.urandom(32)


def gen_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def encrypt(plaintext: str, key: bytes) -> tuple[str, str]:
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode()


def decrypt(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    ct = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    pt = AESGCM(key).decrypt(nonce, ct, None)
    return pt.decode()


def derive_key(password: str, salt_b64: str) -> bytes:
    salt = base64.b64decode(salt_b64)
    kdf = PBKDF2HMAC(
        algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=_PBKDF2_ITERATIONS
    )
    return kdf.derive(password.encode())


def key_to_fragment(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode()
