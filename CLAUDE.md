# expert-checker

Price and promotion watcher for expert.de (per-store prices, set deals, manufacturer cashback).

Read first:
- [docs/requirements.md](docs/requirements.md) — goals, use cases, constraints, decisions, open questions.
- [docs/expert-api.md](docs/expert-api.md) — endpoints, fields, promotion semantics, verified examples.

Rules:
- The expert API is unofficial. Call `production.brntgs.expert.de`. Do not scrape `www.expert.de` HTML (Cloudflare).
- Be polite: at most 8 parallel requests, retry `500` with a short delay, back off on `429 (Too Many Requests)`.
- When an endpoint fails, verify it again and update `docs/expert-api.md`.
- Everything must stay free to run. The user has no Raspberry Pi.
