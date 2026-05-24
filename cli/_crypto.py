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

try:
    from argon2.low_level import Type as _Argon2Type
    from argon2.low_level import hash_secret_raw as _argon2_hash

    _ARGON2_OK = True
except ImportError:
    _ARGON2_OK = False

_PBKDF2_ITERATIONS = 600_000

# OWASP 2023+ minimum for Argon2id in interactive contexts (browser/CLI).
# m = memory in KiB; t = passes; p = parallelism; hash length in bytes.
# Anything stronger meaningfully impacts page-load time on a phone — bump
# these together with the browser WASM lib's defaults when it lands.
_ARGON2_MEMORY_KIB = 19_456  # 19 MiB
_ARGON2_TIME_COST = 2
_ARGON2_PARALLELISM = 1


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


def encrypt(plaintext: str | bytes, key: bytes) -> tuple[str, str]:
    """Encrypt a string or raw bytes with AES-256-GCM. Returns (ct_b64, nonce_b64)."""
    nonce = os.urandom(12)
    data = plaintext.encode() if isinstance(plaintext, str) else plaintext
    ct = AESGCM(key).encrypt(nonce, data, None)
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode()


def decrypt_bytes(ciphertext_b64: str, nonce_b64: str, key: bytes) -> bytes:
    """Decrypt returning raw bytes — used by the compressed-paste path."""
    ct = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    return AESGCM(key).decrypt(nonce, ct, None)


def decrypt(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    return decrypt_bytes(ciphertext_b64, nonce_b64, key).decode()


def derive_key(password: str, salt_b64: str) -> bytes:
    """PBKDF2-SHA256 at 600k iterations — the historical default."""
    salt = base64.b64decode(salt_b64)
    kdf = PBKDF2HMAC(
        algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=_PBKDF2_ITERATIONS
    )
    return kdf.derive(password.encode())


def derive_key_argon2id(password: str, salt_b64: str) -> bytes:
    """Argon2id with OWASP minimum params (m=19 MiB, t=2, p=1)."""
    if not _ARGON2_OK:
        print(
            "Error: 'argon2-cffi' package required for --kdf argon2id. "
            "Run: pip install argon2-cffi",
            file=sys.stderr,
        )
        sys.exit(1)
    salt = base64.b64decode(salt_b64)
    return _argon2_hash(
        secret=password.encode(),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_KIB,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=32,
        type=_Argon2Type.ID,
    )


def derive_key_for(kdf: str, password: str, salt_b64: str) -> bytes:
    """Dispatch to the right KDF based on the protocol's kdf field."""
    if kdf == "pbkdf2-sha256":
        return derive_key(password, salt_b64)
    if kdf == "argon2id":
        return derive_key_argon2id(password, salt_b64)
    raise ValueError(f"unsupported kdf {kdf!r}")


def key_to_fragment(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode()
