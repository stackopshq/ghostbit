# Contributing to Ghostbit

Thanks for considering a contribution. This document covers how to get the project running locally and the conventions Ghostbit follows.

## Core invariant — please read first

**The server must never see plaintext.** All encryption happens client-side (browser via Web Crypto API in [static/e2e.js](static/e2e.js), CLI via [cli/_crypto.py](cli/_crypto.py)). The API only stores Base64 ciphertext + nonce + optional PBKDF2 salt.

The AES-256-GCM key (or, for password pastes, only the PBKDF2 salt) lives in the URL `#fragment`, which browsers never transmit. Any change that risks leaking the key to the server — a redirect that re-emits the fragment, analytics on the paste view page, a new server-side decryption path, accepting plaintext on `POST /api/v1/pastes`, logging request bodies on paste routes — is a protocol break and will be rejected.

The crypto parameters (PBKDF2-SHA256 at 600 000 iterations, AES-256-GCM with a 12-byte nonce, 16-byte salt) are duplicated in three places and must stay aligned: [static/e2e.js](static/e2e.js), [cli/_crypto.py](cli/_crypto.py), and the test vectors in [tests/test_cli_crypto.py](tests/test_cli_crypto.py). See [docs/adr/0001-zero-knowledge-crypto.md](docs/adr/0001-zero-knowledge-crypto.md) for the full rationale.

## Local development

```bash
git clone git@github.com:stackopshq/ghostbit.git
cd ghostbit
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pip install -e cli/                       # editable install of the CLI package
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The default backend is SQLite, no external service required. To exercise the Redis backend, run a local Redis (`podman run --rm -p 6379:6379 redis:7`) and set `STORAGE_BACKEND=redis` in `.env`.

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

The hooks run ruff (lint + format), gitleaks (secret scan), and a few hygiene checks. CI runs the same checks — installing locally just gives you the feedback before the push.

## Tests, lint, format

```bash
pytest tests/ -v                          # full suite (~2s)
ruff check app/ tests/ cli/               # lint
ruff format --check app/ tests/ cli/      # format check (no rewrite)
ruff format app/ tests/ cli/              # apply format
```

A PR is ready to merge when, in order:

1. The code runs locally (`uvicorn app.main:app --reload`).
2. `ruff format --check` passes.
3. `ruff check` passes (no new warnings).
4. `pytest tests/ -v` passes.
5. The container build succeeds (`podman build -t ghostbit .`).
6. For UI changes: the feature was exercised in a browser (golden path + at least one edge case).

## Branches and commits

- Branch naming: `feat/<short-description>`, `fix/...`, `chore/...`, `refactor/...`, `docs/...`.
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/). Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `style`, `revert`. Breaking change → `feat!:` or a `BREAKING CHANGE:` footer.
- Each commit should compile and pass tests on its own.

## Pull requests

- Keep PRs small and atomic — one intent per PR. If the diff is over ~400 significant lines, consider splitting.
- Description structure: *Context*, *Changes*, *Tests*, *Risks*.
- Link any related issue.

## Reporting a security vulnerability

Please **do not** open a public issue. Use [GitHub Security Advisories](https://github.com/stackopshq/ghostbit/security/advisories/new) instead — see [SECURITY.md](SECURITY.md) for the full policy.

## Architecture decisions

Significant design choices are recorded as ADRs under [docs/adr/](docs/adr/). If a PR materially changes architecture, add a new ADR alongside the code change.
