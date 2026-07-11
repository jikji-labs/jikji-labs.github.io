# Jikji Documentation Site

This repository publishes the English-canonical, internationalized product documentation for
[Jikji](https://github.com/jikji-labs/jikji) at
<https://jikji-labs.com>.

## Content Contract

- Product and architecture claims must match implemented Jikji behavior.
- Pre-1.0 or unverified behavior must be labeled explicitly.
- Release, security, and licensing statements must link to their controlling
  repository documents.
- English is embedded in every page and remains the canonical source. The site
  includes 13 locales with automatic browser detection and a persistent manual
  selector. Missing keys fall back to English.
- A translation is applied only while its recorded English source still matches
  the current page. Changed copy therefore falls back to current English instead
  of silently publishing an obsolete translation.
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

The gate checks local links and fragments, canonical URLs, metadata, locale
assets and dimensions, 100% current translation-key coverage, preserved HTML
tokens, declared DOM cardinalities, numeric claims, fallback runtime contracts,
required release/legal references, and known stale claims. This repository keeps
the gate local so publication does not depend on paid CI runners or remote
credentials.

For local browser review, serve the repository root rather than opening files
directly so lazy-loaded locale assets use normal HTTP semantics:

```sh
python3 -m http.server 4173 --bind 0.0.0.0
```
