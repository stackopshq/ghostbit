# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Use GitHub's private vulnerability reporting instead:
**[Report a vulnerability](https://github.com/stackopshq/ghostbit/security/advisories/new)**

Include as much detail as possible:

- A clear description of the vulnerability
- Steps to reproduce
- Potential impact
- A suggested fix if you have one

We aim to acknowledge reports within **48 hours** and provide a fix or mitigation within **14 days** for critical issues.

## Scope

| In scope | Out of scope |
|---|---|
| Server-side vulnerabilities (injection, auth bypass, SSRF…) | Vulnerabilities in third-party dependencies |
| Encryption protocol weaknesses | Issues requiring physical access to the server |
| API abuse / rate-limiting bypass | Self-hosted instances not maintained by StackOps |
| Information leakage | Social engineering |

## Encryption model

Ghostbit uses true end-to-end encryption — the server stores ciphertext only and can never read paste content.
Full details: [docs.ghostbit.dev/encryption](https://docs.ghostbit.dev/encryption/)
