# Third-party notices

Ghostbit itself is under the [Elastic License 2.0](LICENSE). This file covers
the third-party code and fonts **redistributed inside this repository**, each
under its own licence.

It exists because those licences require it. MIT and Apache-2.0 both make
attribution a condition of redistribution, not a courtesy: shipping a minified
bundle with its header stripped is a licence breach even when the code is free.
CodeMirror is exactly that case here, and it is the reason this file was
written on 2026-08-31.

Nothing below is a Ghostbit dependency in the packaging sense. These files are
served to browsers from `/static/`, which is why they travel with every copy of
this repository and every container image built from it.

## Browser assets

| Project | Version | Licence | Files |
|---|---|---|---|
| [CodeMirror](https://codemirror.net/5/) | 5.65.16 | MIT | `static/cm/codemirror-core.min.js`, `static/cm/codemirror-modes.min.js`, `static/cm/codemirror.min.css` |
| [marked](https://marked.js.org/) | 15.0.12 | MIT | `static/marked.min.js` |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.1.7 | Apache-2.0 **or** MPL-2.0 | `static/purify.min.js` |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) | 1.4.4 | MIT | `static/qrcode.min.js` |
| [hash-wasm](https://github.com/Daninet/hash-wasm) | see note | MIT | `static/hash-wasm-argon2.umd.min.js` |

**Note on hash-wasm.** The vendored bundle carries no version string, and none
was recorded when it was added ([`e627d44`](https://github.com/stackopshq/ghostbit/commit/e627d44),
the Argon2id work in [ADR 0002](docs/adr/0002-argon2id-kdf.md)). Rather than
print a version nobody verified, here is what is verifiable: the file is the
argon2-only UMD build, and its SHA-256 begins `dcec617a2e1b700f`. Pinning the
exact upstream version is tracked as a follow-up; a dependency whose version
nobody can state is a dependency nobody can audit for vulnerabilities.

## Fonts

Hanken Grotesk and JetBrains Mono, both under the **SIL Open Font License 1.1**,
are served from `static/fonts/` and `docs/assets/fonts/`. The full licence text
ships beside them in `static/fonts/OFL.txt`, one section per family, as the OFL
requires.

## Licence texts

### MIT

Applies to CodeMirror, marked, qrcode-generator and hash-wasm. Copyright
holders, as stated by each project:

- CodeMirror: Copyright (C) by Marijn Haverbeke and others
- marked: Copyright (c) 2011-2025, Christopher Jeffrey
- qrcode-generator: Copyright (c) Kazuhiko Arase
- hash-wasm: Copyright (c) Dani Biro

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### DOMPurify

Copyright (c) Cure53 and other contributors. Dual-licensed, at your option,
under the **Apache License 2.0** or the **Mozilla Public License 2.0**; the
bundled file states this in its own header, which is preserved. Full texts:
<https://github.com/cure53/DOMPurify/blob/3.1.7/LICENSE>.

## What this file does not cover

The Python packages in `requirements.txt` are installed from PyPI when the
image is built, each under its own licence. They are not vendored here, but a
published container image does contain them: an image redistributed to third
parties carries their notices too, and that inventory belongs with the image
rather than with this repository.
