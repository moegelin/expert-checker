# expert-checker — requirements

## Goals

1. Find the best price for a product at expert: online shop or a local store. Each expert store has its own price.
2. Get a notification on the smartphone when a price drops or a good promotion appears.
3. Find manufacturer cashback offers early, with the possible saving, the link, and the conditions.

Main target: a TV.

## Use cases

1. **Watch a product.** The user adds a product URL. The tool scans all stores and the online shop and shows the best total price:
   - shipped: price + shipping − known codes;
   - pickup: price, only for stores within a maximum distance from the user's location.
2. **Discover cashback offers (most important for TVs).** The tool lists active manufacturer cashback offers (Samsung, Sony, LG, Philips, …):
   - title, brand, period, link to the conditions (manufacturer page, PDF);
   - the possible saving (amount, if it can be found);
   - the qualifying devices (TVs and accessories such as soundbars).
3. **Then find the best price for a qualifying device.** When the user finds an offer interesting, the user picks it and sees the best prices of the qualifying devices across all stores.
4. **Soundbar resale strategy.** The user buys TV + qualifying soundbar, gets the cashback, and sells the soundbar. The UI must show the parts of this calculation:
   - TV price, soundbar price (each at its best store);
   - cashback amount;
   - a field for the expected resale price of the soundbar (user input);
   - effective TV cost = TV + soundbar − cashback − resale.
5. **Set deals in the same cart** (expert `PRODUCT_SET`, exact amount known per store) are a second kind of saving. Show them per store.

### Samsung case

Samsung cashback offers often allow several soundbar options, not only one or two. The TV and the soundbar do not need to be bought in the same shop or at the same time. So for cashback, the tool must not depend on expert set bundles. It must treat TV and soundbar as separate purchases with separate best prices.

## Notifications

- TV-only best price drops, counted against the previous scan so a drop after a rise counts too (or falls below an optional target price). Rises are shown in the app, not pushed (2026-11-22).
- A new set deal appears or gets cheaper.
- A new manufacturer cashback offer starts for a watched brand or product.
- The scan fails (API changed), so failures are not silent.

## Constraints

- Free. No paid hosting, no paid APIs.
- Runs automatically, without the user's computer.
- The user has **no Raspberry Pi**.
- Smartphone app (or app-like) with push notifications and a nice UI for prices and promotions.
- Scans may run in batches, for example 150 stores, then the rest 30 minutes later. A full product view is fine with a delay.
- Polite request rate to the unofficial expert API. Retry on `500`, back off on `429 (Too Many Requests)`.

## Decisions

- Use the API host `production.brntgs.expert.de`, not HTML scraping — no Cloudflare challenge there. See [expert-api.md](expert-api.md).
- Product input is a product URL (webcode). Search is not needed — the search endpoint is gone.
- Restposten (clearance) items count as normal offers. Only real display items (`itemOnDisplay.type` ≠ Restposten) are optional.
- Manufacturer cashback amounts are not in expert data. First version: show that an offer exists, with link and conditions. Amount from another source or by hand.
- Do not build on the old DJGorex script. Reuse its knowledge only.

## Open questions

Analyzed on 2026-11-21; decisions are in [plan.md](plan.md), section 1. The list stays here as the record of the questions.

1. **Hosting for the scheduled scans** — options: GitHub Actions cron (free, may be blocked by expert as data-center IP — not tested), Cloudflare Workers cron (free tier: request limits per run — check), a free-tier cloud function. Recommendation: test GitHub Actions first, because the API host had no Cloudflare challenge.
2. **App type** — options: PWA (web app on the home screen, data as static JSON on GitHub Pages, push via ntfy), native app, ntfy-only push + web UI. Recommendation: PWA on GitHub Pages + ntfy push. Check iOS web-push limits if push should come from the PWA itself.
3. **Cashback amounts** — where to get them: manufacturer page, PDF on `cdn.expert.de`, `possibleDiscountRanges` in `getIndex`, aggregator sites (for example mydealz, cashback overview pages), or manual input. Needs analysis.
4. **Qualifying devices for a cashback** — `getIndex.indexed` maps articles to promotions per store. Check if this gives the full list of qualifying TVs and soundbars for one cashback, or if the manufacturer list is needed.
5. **Samsung offers** — analyze a current Samsung TV cashback at expert: how it appears in `getIndex`, if soundbars are linked to it, and where the amount table is.
6. **Discover all cashback offers without a product URL** — `getIndex` (online shop) lists all promotions. Check if one call per run is enough, or if store-specific offers exist.
7. **Store coordinates and distance** — user location by postcode (old script used `api.zippopotam.us`). Confirm.
8. **Other shops** — the same cashback can be used with other shops. Out of scope for now; note if an easy source exists.
9. **Cashback tab** (added 2026-11-22) — the user doubts the tab is needed. Options: keep the tab; fold offers into the watch list (an "Aktionen" block per product, new offers for watched brands as a push, the offer page with the resale calculator reachable from the product page). Recommendation: fold, decide at the start of M4.
