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
