# ADR 0001 — Zero-knowledge end-to-end encryption

- **Status:** Accepted
- **Date:** 2026-04-20 (initial); 2026-05-24 (this ADR formalising the decision)
- **Decision drivers:** privacy guarantee, operator-trust minimisation, paste-as-secret-sharing use case

## Context

Ghostbit is a paste service whose primary value is that **the operator cannot read what users paste**. This rules out the conventional design where the server stores plaintext (or has a master key it can use to decrypt at any time): if the server can read it, so can a malicious admin, a stolen backup, a court order, or a cloud provider that subpoenas the disk.

Two architectural shapes were considered:

1. **Server-side encryption at rest (e.g. AES key in environment variable).** Easy to implement, server-side search/highlighting possible, but the server holds the key. Compromise → all pastes readable. Court order → operator must hand over plaintext.
2. **End-to-end encryption, key never leaves the client.** Encryption and decryption run in the browser (Web Crypto API) or the CLI; the server only sees opaque ciphertext. Compromise → attacker gets ciphertext but no key. Court order → operator can hand over ciphertext but has no way to decrypt it.

Option 2 is the only design that delivers the product promise. The operational cost (no server-side search, no language detection on ciphertext, no opaque migration path) is acceptable for the paste use case.

## Decision

Use **client-side AES-256-GCM** with a key that lives only in the URL `#fragment` (which browsers never transmit). For password-protected pastes, the key is **derived from the password** using PBKDF2-SHA256; the salt is stored server-side, but the password and derived key never leave the client.

### Cryptographic parameters

| Parameter | Value | Rationale |
|---|---|---|
| Symmetric cipher | AES-256-GCM | NIST-approved AEAD; native in browser (`crypto.subtle`) and Python (`cryptography`); 256-bit key matches the post-quantum precaution most defenders are taking. |
| Nonce length | 12 bytes | GCM standard; collision risk negligible for a per-paste random nonce. |
| KDF (password mode) | PBKDF2-HMAC-SHA256, **600 000 iterations** | OWASP 2023+ recommendation for PBKDF2-SHA256 in browser/CLI contexts. Argon2id would be stronger but is not yet native in `crypto.subtle` — adding a WASM build would mean a third place to maintain crypto code. See "Future considerations" below. |
| Salt length | 16 bytes | NIST SP 800-132 minimum; per-paste random. |
| Key transport | URL `#fragment` | Browsers never include the fragment in HTTP requests, so the server cannot log it even by accident. |
| Delete token | `secrets.token_urlsafe(16)`; server stores only `sha256(token)` | Plaintext token returned once at creation; never logged, never persisted. |

### Where the parameters are duplicated

They appear in **three** implementations and must stay aligned:

- [`static/e2e.js`](../../static/e2e.js) — browser (Web Crypto API)
- [`cli/_crypto.py`](../../cli/_crypto.py) — `gbit` CLI (`cryptography` package)
- [`tests/test_cli_crypto.py`](../../tests/test_cli_crypto.py) — round-trip test vectors that cross both impls

Any change to one must change the other two in the same PR.

## Consequences

### Positive

- Operator (and anyone who compromises the operator) **cannot** read user pastes.
- A leaked backup, a subpoena, a malicious infrastructure provider — none of these break the secrecy of past pastes.
- Pastes created by the browser are decryptable by the CLI, and vice versa.

### Negative / accepted trade-offs

- No server-side search, no server-side syntax highlighting (must run in the client after decryption).
- No server-side language detection on ciphertext — clients call `POST /api/v1/detect` on **plaintext** before upload if they want language assist. The server route exists precisely to keep that workflow possible without ever sending the encrypted content to detect against.
- The server cannot migrate the encryption format on its own (e.g. PBKDF2 → Argon2id); doing so requires versioning the wire format so clients can recognise both during a transition.
- Lost URL fragment = lost paste. No recovery path. This is the price of zero-knowledge.

### Operational rules that follow

- `POST /api/v1/pastes` must accept only ciphertext + nonce + optional salt. Never plaintext.
- Paste routes must never log request bodies.
- `view_paste` (the HTML shell) must be side-effect-free. View counting, burn-after-read, and webhooks fire from the ciphertext fetch (`GET /api/v1/pastes/{id}`) so they cannot leak information about plaintext.
- The `gbit` CLI must use the same parameters as the browser; any divergence breaks cross-tool compatibility and is caught by `tests/test_cli_crypto.py` test vectors.

## Future considerations

- **Argon2id** (PHC winner, memory-hard) would be a stronger KDF than PBKDF2-SHA256. A future ADR may introduce it alongside PBKDF2 with a wire-format `kdf` field so both can coexist during migration. Browser support would require a WASM build of an Argon2 implementation (~50 KB).
- **Compression before encryption** (opt-in, opt-out via a `compressed` flag) would cut payload sizes 60–80% on text/JSON without weakening the crypto, but adds one more parameter to keep aligned across the three impls.

## References

- OWASP Password Storage Cheat Sheet (PBKDF2 iteration recommendations)
- NIST SP 800-38D (GCM mode)
- NIST SP 800-132 (PBKDF salt length)
- [docs/encryption.md](../encryption.md) — user-facing explanation of the protocol
