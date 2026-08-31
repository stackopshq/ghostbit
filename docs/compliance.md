# Compliance

**Last audit: 2026-08-31** · next review due: 2027-08-31 (or after any change
to what the server stores, logs, or sends).

This page is the record of a GDPR / nLPD (revised Swiss data protection act)
/ ISO 27001-alignment review of Ghostbit — code, deployment defaults, CI, and
public claims. It is a **self-assessment**: no accredited body has certified
anything here, and the badges in the README say exactly that. "ISO
27001-aligned" means the technical controls an auditor would ask this product
for are in place; actual certification is an organizational process (an ISMS,
management reviews, an accredited audit) that a single repository cannot
carry.

## Self-hosted instances

Ghostbit is a self-hostable product, so "compliant" is a property of an
*installation*, not only of this codebase. The software supplies
privacy-by-default (no accounts, cookies, third-party requests or access
logs) and a `/privacy` notice whose controller identity comes from
`PRIVACY_OPERATOR` / `PRIVACY_CONTACT_URL` / `PRIVACY_AUTHORITY` — a
hardcoded operator would have made every install but ours serve a false
notice. The deployment-side obligations (naming yourself, keeping access
logs off, bounding proxy/CDN log retention, backup retention, closing
`/metrics`, TLS) are the README checklist, **Compliant deployments (GDPR /
nLPD)**.

For the record, ghostbit.dev runs with:

```env
PRIVACY_OPERATOR="StackOps (France)"
PRIVACY_CONTACT_URL=mailto:privacy@stackops.ch
PRIVACY_AUTHORITY="the CNIL (France)"
```

## Why there is so little to assess

Ghostbit's data protection story is architectural, not procedural. Pastes are
encrypted in the client; the key never reaches the server; there are no
accounts, no cookies, no analytics, and no third-party requests from any page
the app serves. The full inventory of what the server does hold, for how
long, and for whom, is in the [privacy notice](https://ghostbit.dev/privacy)
— kept deliberately short because the honest answer is short.

## What the 2026-08-31 audit found and fixed

| Finding | Severity | Fix |
|---|---|---|
| uvicorn access logs on by default: every line paired a client IP with a paste ID, contradicting the documented "no IP logging" | High (privacy) | Access logging off by default in the image; `ACCESS_LOG=true` opts in, documented as a data-protection decision |
| `/docs` and `/redoc` referenced third-party CDNs (jsdelivr, Google Fonts) — and rendered blank anyway under our CSP | Medium (privacy) | Both removed; `/openapi.json` remains; API reference lives in this docs site |
| docs.ghostbit.dev imported Google Fonts — every docs reader's IP went to Google | Medium (privacy) | Fonts self-hosted (same woff2 the app serves) |
| CLI history stored full capability URLs (`#key~token`) with default file permissions | Medium | Created `0600` in a `0700` dir, tightened retroactively on append |
| Backups (containing webhook URLs and delete-token hashes) accumulated forever | Medium (retention) | Pruned after `BACKUP_RETENTION_DAYS` (default 30) |
| No privacy notice, no legal surface at all | High (GDPR art. 13 / nLPD art. 19) | `/privacy` served in-app, versioned in git, controller named per-instance via `PRIVACY_*` |
| Rate limiting on 3 of ~16 routes while README claimed all endpoints | Medium | PUT/DELETE and the HTML delete form now limited; README wording corrected |
| `/metrics` public: aggregate rates + exact Python version | Low–Medium | Optional `METRICS_TOKEN` bearer gate; production sets it |
| Dependencies unpinned (`>=`), invisible to Trivy's advisory matching; one known CVE in the resolved tree (cryptography < 50) | Medium (supply chain) | `requirements*.txt` pinned exactly; cryptography at 50.0.1 |
| gitleaks only ran as an optional local hook while docs claimed it ran in CI | Medium | Secret-scan job on every PR (pinned binary, checksum-verified) |
| Compose sample published the plaintext port on all interfaces; Redis password in probe argv | Low | Loopback publish by default, `no-new-privileges`, `REDISCLI_AUTH` probe |
| A dozen documentation claims contradicted the code (expiry bounds, DELETE status codes, image tags, KDF list…) | Low (trust) | Docs corrected, and the enforceable ones are now enforced server-side (TTL ≤ 1 year, `webhook_url` ≤ 2048 chars) |

## Control summary (ISO 27001 Annex A, technical slice)

- **Cryptography** (A.8.24): E2E AES-256-GCM client-side; PBKDF2/Argon2id for
  passwords; age-encrypted backups; TLS terminated upstream with HSTS.
- **Logging & monitoring** (A.8.15/16): no personal data in logs by default;
  app logs carry paste IDs only where operationally needed (webhook
  failures); Prometheus metrics with bounded labels, optionally
  token-gated.
- **Access control** (A.8.2/5): no user accounts to protect; delete/edit
  gated by hashed capability tokens compared in constant time; admin
  export/import is a CLI requiring host access, never HTTP.
- **Secure development** (A.8.25–31): CI on every PR — lint, tests on both
  storage backends, secret scan; Trivy (vuln/secret/misconfig) on main;
  pinned dependencies; signed-off release flow with protected `main`.
- **Supplier management** (A.5.19–23): subprocessors are Cloudflare (CDN/TLS)
  and GitHub (public repo hosting + hourly server-side star count). Nothing
  else receives traffic.
- **Backup** (A.8.13): daily, encrypted with a public key (private key held
  offline), plaintext never on disk, 30-day retention, restore path
  documented in `scripts/backup.sh`.

## What a real certification would still need

An ISMS scope statement, risk register and treatment plan, management
review, internal audit, and an accredited certification body. Those live at
the organization level (StackOps), not in this repository. Until then the
claim here stays what it is: **aligned, not certified**.
