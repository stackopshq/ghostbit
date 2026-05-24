# ADR 0002 — Argon2id alongside PBKDF2 for password pastes

- **Status:** Accepted — server, CLI **and** browser implementations all shipped.
- **Date:** 2026-05-24
- **Builds on:** [ADR 0001 — Zero-knowledge end-to-end encryption](0001-zero-knowledge-crypto.md)

## Context

ADR 0001 fixed PBKDF2-SHA256 at 600 000 iterations as the KDF for password-protected pastes. PBKDF2 is well-supported (native in `crypto.subtle` and the Python `cryptography` package), but it is **not** memory-hard — a GPU/ASIC attacker can amortise the work massively in parallel. Argon2id (the PHC winner) is the current state of the art: memory-hard, side-channel resistant, recommended by OWASP since 2021.

Adding Argon2id wholesale would break every existing paste (and every existing CLI release in the wild), so it has to coexist with PBKDF2 — selected per paste, advertised by the server, run by whichever client opens the paste.

## Decision

Add an opt-in `kdf` field to the paste protocol with two values:

- `"pbkdf2-sha256"` — historical default. Unchanged parameters (600k iterations, see ADR 0001).
- `"argon2id"` — new. Parameters fixed for the protocol (no per-paste tuning, otherwise verifiers couldn't reproduce the derivation):
  - **memory** = 19 456 KiB (19 MiB)
  - **time** = 2 passes
  - **parallelism** = 1
  - **hash length** = 32 bytes (AES-256 key)
  - **salt** = 16 random bytes (shared with the PBKDF2 path)

These are the OWASP 2023 minimums for Argon2id in interactive contexts (browser/CLI). Anything stronger meaningfully impacts page-load time on mobile — bump in lockstep with the browser WASM library's defaults when we revisit.

## Wire format

`PasteData.kdf: str` — defaults to `"pbkdf2-sha256"` for backward compatibility. Persisted by both storage backends (new column in SQLite, JSON field in Redis, default applied for old rows on read). Returned in `GET /api/v1/pastes/{id}` so the viewer knows which KDF to run.

## Implementations

| Layer | Library | Status |
|---|---|---|
| Server | n/a (just stores the hint) | ✅ |
| CLI | `argon2-cffi` (already a top-level dep) | ✅ |
| Browser | `hash-wasm` argon2 bundle (29 KB UMD with the WASM inline), loaded on the homepage and on password paste pages only | ✅ |

The browser bundle came in smaller than expected once the argon2-only build was selected (29 KB instead of the ~70 KB full hash-wasm bundle), so we ship it eagerly with `defer` rather than dynamic-loading it on demand. Non-password paste pages don't include it at all, which is the only conditional needed in practice.

The CSP gains `'wasm-unsafe-eval'` in `script-src` so the bundle can `WebAssembly.instantiate()` its embedded module. This is a narrow opt-in — it does not enable JS `eval()`, only WebAssembly compilation — and is supported by Chrome 92+ / Firefox 122+ / Safari 16.4+.

## Backward compatibility

- Existing pastes have `kdf=NULL` in the row → storage layer fills in `"pbkdf2-sha256"` on read (SQLite NOT NULL default, Redis `setdefault`).
- CLI defaults `--kdf pbkdf2-sha256`. Users explicitly opt in with `gbit paste -p --kdf argon2id`.
- A paste created with `--kdf argon2id` (CLI) is now decryptable in any modern browser that can run WebAssembly — and conversely, a paste created with "Argon2id" picked in the browser KDF picker is readable by a CLI with `argon2-cffi`. Cross-impl round-trip verified manually.

## Consequences

### Positive

- Defenders get a path to a memory-hard KDF without a flag day.
- Power users with valuable secrets can opt in immediately via the CLI.
- The protocol carries the KDF choice explicitly, so any future addition (scrypt, Argon2d, etc.) plugs in the same way without breaking older clients — they just reject unknown values at the validator.

### Negative / accepted

- Three KDF call sites instead of two (browser, CLI, server-side validator). They must stay in sync with this ADR's parameter table.
- The browser WASM lib is dead weight on PBKDF2 pastes — the lazy-load partly addresses that, but bandwidth-conscious deployments may want to disable Argon2id entirely (future toggle).
- Cross-client compatibility window: until the browser implementation lands, an Argon2id paste created by the CLI cannot be opened in a browser. Documented in the CLI help and in this ADR.

## References

- [OWASP Password Storage Cheat Sheet — Argon2id](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#argon2id)
- RFC 9106 (Argon2)
- [hash-wasm](https://github.com/Daninet/hash-wasm) — chosen as the browser library for the follow-up
