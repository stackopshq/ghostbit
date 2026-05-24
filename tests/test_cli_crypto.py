"""Tests for CLI crypto — mirrors e2e.js behaviour."""

import pytest
from cryptography.exceptions import InvalidTag

# Relies on the CLI being installed as an editable package (handled by the
# test workflow via `pip install -e cli/`). Lets the test reference the
# public names directly instead of a sys.path hack.
from cli import _decrypt, _derive_key, _encrypt, _gen_key, _gen_salt


def test_roundtrip_no_password():
    key = _gen_key()
    plaintext = "Hello, Ghostbit!"
    ciphertext, nonce = _encrypt(plaintext, key)
    assert _decrypt(ciphertext, nonce, key) == plaintext


def test_roundtrip_with_password():
    salt = _gen_salt()
    key = _derive_key("s3cr3t", salt)
    plaintext = "password-protected paste"
    ciphertext, nonce = _encrypt(plaintext, key)
    assert _decrypt(ciphertext, nonce, key) == plaintext


def test_wrong_key_raises():
    key = _gen_key()
    wrong = _gen_key()
    ciphertext, nonce = _encrypt("secret", key)
    with pytest.raises(InvalidTag):
        _decrypt(ciphertext, nonce, wrong)


def test_wrong_password_raises():
    salt = _gen_salt()
    key = _derive_key("correct", salt)
    ciphertext, nonce = _encrypt("secret", key)
    wrong_key = _derive_key("wrong", salt)
    with pytest.raises(InvalidTag):
        _decrypt(ciphertext, nonce, wrong_key)


def test_key_to_fragment_is_urlsafe():
    from cli import _key_to_fragment

    key = _gen_key()
    fragment = _key_to_fragment(key)
    assert "+" not in fragment
    assert "/" not in fragment
    assert "=" not in fragment


def test_different_keys_produce_different_ciphertexts():
    key1 = _gen_key()
    key2 = _gen_key()
    ct1, _ = _encrypt("same plaintext", key1)
    ct2, _ = _encrypt("same plaintext", key2)
    assert ct1 != ct2


def test_compressed_paste_round_trips():
    """The CLI compression path: gzip → encrypt → decrypt → gunzip → original.
    Mirrors the browser's gzipString/gunzipToString flow in static/e2e.js."""
    import gzip

    from cli import decrypt_bytes

    plaintext = "long text " * 500
    key = _gen_key()
    compressed = gzip.compress(plaintext.encode())
    assert len(compressed) < len(plaintext)  # sanity: gzip actually saved bytes
    ct, nonce = _encrypt(compressed, key)
    raw = decrypt_bytes(ct, nonce, key)
    assert gzip.decompress(raw).decode() == plaintext


def test_encrypt_accepts_both_str_and_bytes():
    """encrypt() must be polymorphic so the compression caller doesn't have
    to .decode() bytes back to str just to please the type signature."""
    key = _gen_key()
    ct_s, n_s = _encrypt("hi", key)
    ct_b, n_b = _encrypt(b"hi", key)
    assert _decrypt(ct_s, n_s, key) == "hi"
    assert _decrypt(ct_b, n_b, key) == "hi"


def test_argon2id_round_trip():
    """Same plaintext → encrypt with argon2id-derived key → decrypt back.
    Pins the cross-impl contract for password pastes when --kdf argon2id."""
    from cli import derive_key_for

    salt = _gen_salt()
    key = derive_key_for("argon2id", "topsecret", salt)
    assert len(key) == 32
    ct, nonce = _encrypt("argon2id paste", key)
    key2 = derive_key_for("argon2id", "topsecret", salt)
    assert _decrypt(ct, nonce, key2) == "argon2id paste"


def test_argon2id_different_password_fails():
    from cryptography.exceptions import InvalidTag

    from cli import derive_key_for

    salt = _gen_salt()
    key = derive_key_for("argon2id", "right", salt)
    ct, nonce = _encrypt("secret", key)
    wrong = derive_key_for("argon2id", "wrong", salt)
    with pytest.raises(InvalidTag):
        _decrypt(ct, nonce, wrong)


def test_derive_key_for_rejects_unknown_kdf():
    from cli import derive_key_for

    with pytest.raises(ValueError, match="unsupported kdf"):
        derive_key_for("scrypt", "x", _gen_salt())
