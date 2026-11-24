# expert-checker — features

Status: draft for review, 2026-11-21; revised 2026-11-23 after the phone test (the scanner runs on the phone, plan.md §3). Milestones are defined in [plan.md](plan.md), section 6. Version 1 = M0–M4.

Legend: **in** = version 1, **out** = version 2 or later, **✗** = not planned.

## M0 — Hosting probe (done 2026-11-23)

| Feature | v1 | Notes |
|---|---|---|
| API client with browser `User-Agent`, 8 workers, retry `500` ×3, backoff on `429 (Too Many Requests)` | in | shared by every later command |
| Challenge detection (non-JSON body, `cf-mitigated` header) | in | feeds the failure alert |
| `probe` workflow: hourly for 3 days around the clock (5 calls; sweep of 349 `pricepds` in the first run and every 6 h), writes `data/probe.json`, disables itself after 72 h | in | no-go on 2026-11-22 (Cloudflare challenge); the workflow is deleted in M1, the `probe` command stays as a diagnostic |
| Phone test: the same probe hourly for 24 h on the Galaxy S25 in Termux (JobScheduler, Termux:Boot, healthchecks ping) | in | go on 2026-11-23; plan.md §1, "Phone test result" |

## M1 — Phone runtime, price scanner and push

| Feature | v1 | Notes |
|---|---|---|
| Phone runtime: `scanner run --push` (lock file, `git pull`, the due steps, `data/status.json`, commit and push of `data/` with the PAT, N7 after three failed pushes); `phone/run.sh` (time window, wake lock, network, healthchecks ping, failure notification); JobScheduler job every 2 h | in | plan.md §2 and §3; built 2026-11-23 (M1 step 1) |
| Unknown offers: a call that fails after the retries or a thin body without `bruttoPrice` keeps the previous offer for 24 h without an alert; a run that loses more than half of a product's offers is incomplete | in | findings F3 and F4 of the phone test |
| Watch list in `config/watchlist.json` (product URL or webcode, label, target price, alert mode, watch sets) | in | |
| Store list from the store finder, online shop added by hand, weekly refresh | in | |
| Full scan: price, shipping, online stock, store stock, display type per store | in | 349 stores + online per product |
| Best shipped total = price + shipping − codes | in | codes from `promotionPrice`, online only |
| Best pickup within radius (postcode → coordinates, Haversine) | in | radius default 50 km |
| Restposten counts as a normal offer, shown with a badge | in | decision from requirements |
| Real display items (Ausstellungsstück) included, with badge | in | can be hidden in the app |
| Daily history point per product (best shipped, best pickup), 90 days | in | 30-day sparkline and verdict in the list card (M2); 90-day chart in M5 |
| ntfy push: price drop (N1, default every drop against the previous scan, also after a rise; per product switchable to new 30-day low or target price), target price (N2, optional), Restposten deal (N3), failure (N7); rises shown in the app, never pushed | in | rules in plan.md §5 |
| healthchecks.io dead-man ping from `run.sh`; cron every 2 h, 06–20 Berlin, grace 2 h | in | |
| Scan window 06:00–22:00 Berlin, no night runs (`run.sh` skips the night); the healthchecks.io schedule matches the window | in | decided 2026-11-22 |
| Quiet hours | ✗ | not needed: no scans 22:00–06:00 (decided 2026-11-22) |
| Product images: the scanner stores the `cdn.expert.de` URL, the app loads it from there | in | no Pillow on the phone; M2 verifies the browser may load it, otherwise the scanner stores the original file |
| More than 10 products: the price step scans two halves in consecutive runs | out | M5 |
| Email instead of ntfy | ✗ | |

## M2 — PWA v1

Built 2026-11-24 (plan.md §6, "M2 scope"): https://moegelin.github.io/expert-checker/app/

| Feature | v1 | Notes |
|---|---|---|
| Screen 1 (Beobachten): one card per product; head with image, name, subtitle (no price); receipt rows: cheapest path first (place, distance, stock, Aussteller/Restposten badge, "kein Cashback" or "ohne Cashback"), cashback deduction, total "Dein Preis inkl. Cashback", the other path with "mit Cashback", set deal "nicht im Preis"; footer with 30-day sparkline, movement and verdict; "Mehr" expands stores within the radius, the three cheapest shippers and all promotions including Zugaben | in | prototype/b2.html (design B2, 2026-11-22) |
| List header without the "n am Tiefstpreis" hint; "Produkt hinzufügen" as a plus button in the top bar that opens the URL field, not at the list end | in | review 2026-11-22 |
| "Aktionen" row with marks under the receipt of a list card: Zugaben and further set deals, tappable to the product page; a priced cashback and the first set deal stay receipt rows, so nothing appears twice | in | added 2026-11-24 after the user missed the Zugaben on the list |
| Green = lowest effective price of the last 30 days and at least 3 % under the 30-day high; otherwise black with "X € über dem 30-Tage-Tief" | in | DESIGN.md, Colors |
| Screen 2 (Produkt): hero image, receipt rows and trend, cashback explanation; then Aktionen directly under the price (cashback offer card, set deals, Zugaben); then alert mode (every drop / new 30-day low / target) with an optional target, the 30-day chart (Versand and Abholung lines, target line only when set); stores within the radius as separate cards with postcode, street, stock, display badge, "ohne Cashback" label, "mit Cashback" net line, link to the store's product page (`?branch_id`) and a copy-postcode button; Online-Shop card with explanation; further shippers collapsed behind "n weitere Versender" | in | prototype/b2.html |
| Icon of the Aktionen lines in the expanded area aligned to the first text line (reviewer saw it centred) | in | review 2026-11-22 |
| Cashback tab | in | built 2026-11-24 with M4: three tabs; the count bubble shows active cashbacks this phone has not seen yet, opening the tab marks them seen (localStorage), the "neu" badge on a card stays 3 days; the product page also carries the offers (open question 9 closed: both) |
| Filter in product detail: shipped / pickup / within radius / show display items | in | |
| UI in German | in | decided 2026-11-21 |
| Product images from cdn.expert.de, URL stored by the scanner | in | verified 2026-11-24: the CDN serves to the browser, images stay linked |
| Add product by pasting the URL | in | writes config through the GitHub API when a token is stored; otherwise shows the JSON to paste on GitHub; the next run (at most 2 h later) scans it |
| Settings: postcode, radius, target prices, ntfy topic name (display only), GitHub token | in | token in `localStorage`, never in the repo. Built 2026-11-24: postcode with geocoding, radius, scanner status, token check; target prices live on the product page; the ntfy topic is not shown (it is a secret on the phone, the app only names the channel) |
| "Scan now" button | out | dropped 2026-11-23: no Actions; a manual run is `phone/run.sh manual` in Termux, a Termux:Widget shortcut is M5 |
| Home-screen install (manifest, icons, offline shell) | in | data needs network; built 2026-11-24: `sw.js` caches the shell and the last data copy, images from `cdn.expert.de` on first load |
| Last-scan age (from `data/status.json`) with warning when older than 4 h | in | runs every 2 h |
| Alert inbox (list of `data/alerts.json`) | out | M5 |
| Price history sparkline | out | M5 |
| Web push from the PWA (no ntfy app) | out | version 2 |
| Product search by name (over a cached article list from the promotion index) | out | version 2; no search endpoint in the API |
| Native app | ✗ | |
| Multi-user | ✗ | |

## M3 — Set deals

Built 2026-11-24 (plan.md §6, "M3 and M4 scope").

| Feature | v1 | Notes |
|---|---|---|
| Set deals per store from `bundlesForArticle` for stores that offer the product | in | every 3 h |
| Effective accessory price = set price − TV price at the same store | in | |
| Product detail: set deals section, grouped by accessory, best store per set | in | prototype screen "Product", section "Set deals" |
| Watch list: "set" badge when any set deal exists within range or online | in | |
| Push: new set deal or discount grows by ≥ 20 € (N4) | in | one message per product and bundle with online price, stores within range and the cheapest (2026-11-24) |
| Direct discounts (`DIRECT_DISCOUNT`, e.g. −65 € cart discount) shown as code line | in | comes from `pricepds.promotionPrice` |
| Summed bundle price endpoint (`getSummedBundle`) | out | only if a set has optional articles |

## M4 — Cashback

Built 2026-11-24 (plan.md §6, "M3 and M4 scope"). Device prices come from the online shop; "Watch this" gives the full scan.

| Feature | v1 | Notes |
|---|---|---|
| Discovery: one `getIndex` call for the online shop per run, all `CASHBACK` promotions | in | every 6 h |
| Classification: cashback (money back) / free extra (game, streaming, warranty) / other (PayPal, PAYBACK) by title and description keywords | in | the app shows cashback first, the rest behind a filter |
| Brand detection from title, description, and the first qualifying article | in | |
| Period and registration deadline parsed from the description | in | dates like `12.11. – 10.01.2027` |
| Screen 3 (Cashback): active offers as cards with brand mark, amount range, period bar, deadlines, condition badge (one invoice / separate purchases / TV only), "your TV qualifies"; free extras and ended offers in their own sections; filter chips | in | prototype screen "Cashback" |
| Qualifying TVs from `getIndex.indexed`, names via `search/article` (cached) | in | |
| Amounts from the Teilnahmebedingungen PDF on `cdn.expert.de`: Samsung parser (`Modell-Code / Zoll / Cashback`), Sony parser (`Bezeichnung / SAP / Cashback / Double`) | in | other brands: "amount unknown" + link |
| Manual override file for amounts and devices | in | `config/cashback-overrides.json` |
| Soundbar candidates: PDF list matched against the accessories named in set-deal descriptions of the brand by model code; manual add in `config/cashback-overrides.json` | in | `additionalArticles` holds cables and mounts, not soundbars (2026-11-24) |
| Screen 4 (Aktion): amount headline, buy/register dates, links, rule and condition in plain German, qualifying TVs with amount, best price and net, soundbars with best price and set-deal hint, "your TV does not qualify" note | in | prototype screen "Aktion" |
| Resale calculator: TV (best store) + soundbar (best store, may differ) − cashback − expected resale = effective TV cost; comparison with TV-only cashback and with a set deal in the same cart | in | prototype screen "Offer", section "Resale calculator" |
| "Watch this" on a qualifying device adds it to the watch list with role `cashback-tv` / `cashback-soundbar` | in | |
| Push: new cashback for a watched brand or product (N5), amounts became known (N5), 3 days before the end (N5), price drop of a picked device (N6) | in | |
| Parsers for LG, Philips, Hisense, TCL PDFs | out | version 2, after the first real offer of each |
| Amounts from aggregator sites (mydealz, cashback overview pages) | out | version 2; only if PDFs fail often |
| Other shops for the same cashback | ✗ | out of scope per requirements |
| Automatic resale price estimate (eBay sold listings) | out | version 2; the field stays manual in v1 |

## M5 — Hardening (after version 1)

| Feature | v1 | Notes |
|---|---|---|
| Price history sparkline per product (90 days) | out | |
| Alert inbox in the app | out | |
| Per-rule cooldowns in config | out | v1 uses the defaults from plan.md §5 |
| More than 10 products in two halves per run | out | |
| Termux:Widget shortcut for a manual run | out | |
| Delete the `actions` runner code of the probe; repo size check after 30 days of 8 pushes a day | out | |
| Weekly summary message | out | |
| Web push from the PWA, no ntfy app needed | out | |
| Native-feel polish from the finish review: disclosure chevron on tappable rows, segmented control instead of chips, tap-to-read on the price chart, swipe actions on the watch list (remove, change alert), pull-to-refresh tied to "Scan" | out | reviewer's ceiling notes, 2026-11-21 |

## Version 1 at a glance

**In:** scanner on the phone (Termux, JobScheduler every 2 h, data pushed to the repo), best shipped and pickup price across all stores, Restposten deals, set deals with effective accessory price, cashback discovery with Samsung and Sony amounts, qualifying TVs and soundbars, resale calculator, ntfy push for the seven rules, PWA with the four screens, failure alerts.

**Out:** web push from the PWA, "Scan now" in the app, history charts, alert inbox, more brand parsers, aggregator amounts, other shops, native app.
