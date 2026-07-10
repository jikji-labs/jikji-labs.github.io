# Jikji Documentation Site

This repository publishes the English canonical product documentation for
[Jikji](https://github.com/jikji-labs/jikji) at
<https://jikji-labs.com>.

## Content Contract

- Product and architecture claims must match implemented Jikji behavior.
- Pre-1.0 or unverified behavior must be labeled explicitly.
- Release, security, and licensing statements must link to their controlling
  repository documents.
- English is the canonical language. Translations may return after they can be
  generated and checked against a specific canonical content revision.
- Do not publish credential values, private live-provider output, customer
  data, or internal test implementation.

## Verify

Run the static-site gate before every commit:

```sh
python3 scripts/verify_site.py
```

The gate checks local links and assets, required release/legal references, and
known stale claims. GitHub Actions runs the same command on every change.
