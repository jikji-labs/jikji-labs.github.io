# Jikji Documentation Site

This repository publishes the English-canonical, internationalized product documentation for
[Jikji](https://github.com/jikji-labs/jikji) at
<https://jikji-labs.com>.

## Content Contract

- Product and architecture claims must match implemented Jikji behavior.
- Pre-1.0 or unverified behavior must be labeled explicitly.
- Platform claims must distinguish CGO-disabled cross-build validation from native
  runtime qualification, name capability gaps such as sandboxing and PTY support,
  and state the BSD support boundary explicitly.
- Release, security, and licensing statements must link to their controlling
  repository documents.
- English is embedded in every page and remains the canonical source. The site
  includes 13 locales with automatic browser detection and a persistent manual
  selector. Missing keys fall back to English.
- Every locale records the SHA-256 revision of the complete canonical English
  dictionary it was reviewed against. The verifier recomputes that revision,
  and the browser applies a locale only when its revision matches; otherwise the
  page falls back to current English instead of publishing stale translated copy.
- Product, example, navigation, caption, and image-alt keys must exist in all 13
  locale dictionaries. Legal, contact, and incident-runbook bodies remain
  authoritative in English and display an explicit notice for other locales.
- Detail-page hero images live in `assets/detail/` as optimized 1600x666 WebP
  assets. They must depict the page's mechanism, carry translated alt text, and
  declare intrinsic dimensions to prevent layout shift.
- Do not publish credential values, private live-provider output, customer
  data, or internal test implementation.

## Verify

Run the static-site gate before every commit:

```sh
python3 scripts/verify_site.py
```

The gate checks contained local links and fragments, canonical URLs, metadata,
navigation parity, main landmarks and skip links, locale source revisions, 100%
current translation-key coverage, English fallbacks, preserved HTML and numeric
tokens, detail-image placement and dimensions, declared DOM cardinalities,
runtime contracts, required release/legal references, and known stale claims.
This repository keeps the gate local so publication does not depend on paid CI
runners or remote credentials.

For local browser review, serve the repository root rather than opening files
directly so lazy-loaded locale assets use normal HTTP semantics:

```sh
python3 -m http.server 4173 --bind 0.0.0.0
```
