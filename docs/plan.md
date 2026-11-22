# expert-checker — plan

Status: draft for review, 2026-11-21, revised after the first review (German UI, Berlin location, redesigned prototype). Builds on [requirements.md](requirements.md) and [expert-api.md](expert-api.md). Feature list: [features.md](features.md). Clickable prototype: [prototype/index.html](../prototype/index.html), published at https://claude.ai/artifact/Cf3Y6zg8fAqWNPkKaELWdt (run locally with `python3 -m http.server 8765 --directory prototype`). Revised and final prototype (card B2, 2026-11-22): [prototype/b2.html](../prototype/b2.html), published at https://claude.ai/artifact/Y1dntJo3RAE6oRvnXTK2h2.

## 1. Decisions on the open questions

The open questions in requirements.md were analyzed with live API calls on 2026-11-21 (promotion index of the online shop, Freital and Pasternak; article lookups; the Sony and Samsung cashback PDFs). Results:

| # | Question | Decision | Evidence |
|---|---|---|---|
| 1 | Hosting | **GitHub Actions cron in a public repo.** Milestone 0 is a 3-day probe, because the API host *is* behind Cloudflare (`server: cloudflare`, `cf-ray`) and GitHub runners use Azure data-center IPs. Cloudflare Workers are ruled out: the free plan allows 50 external subrequests per invocation; a scan needs 349. Fallback if the probe fails: Oracle Cloud "Always Free" VM with cron (needs a card at signup, no charge). | Response headers of `pricepds`; Cloudflare Workers limits; GitHub Actions docs. |
| 2 | App type | **PWA on GitHub Pages + ntfy push (ntfy.sh, Android app).** Data = JSON files the scanner commits into the repo. The phone is a Samsung Galaxy S25 (Android, confirmed 2026-11-21), so web push has no iOS limits; it stays version 2 because the scanner would have to store push subscriptions and sign VAPID requests; ntfy needs one `POST`. | ntfy docs. |
| 3 | Cashback amounts | **Parse the Teilnahmebedingungen PDF on `cdn.expert.de`** that the promotion description links. Samsung and Sony PDFs hold model-code tables (`Modell-Code / Zoll / Cashback`, `Bezeichnung / SAP / Cashback / Double-Cashback`). `possibleDiscountRanges` is `null` for TV cashbacks (it is filled only for household appliances: Bosch, Siemens, AEG). Manual override file for unparsed brands. | PDFs of `e_4294` (Sony) and `e_4288` (Samsung Frame Pro); `compactPromotionData`. |
| 4 | Qualifying devices | **TVs: from `getIndex.indexed` (complete for expert's range). Soundbars: not linked** (Sony cashback `e_4294` → 8 TVs, 0 soundbars). Soundbar list comes from the PDF; expert articles for them are found through the TV article's `additionalArticles` cross-sell list (numeric ids → `search/article?articleId=e_<id>`), matched by model code. Manual add as fallback. | `indexed` reverse map; `search/article` response. |
| 5 | Samsung offers | At expert today: `e_4288` "Samsung Cashback" = **The Frame Pro Deals** (16.11.–6.12.2026, 130–250 €, TV only, 4 articles). `e_4309` "Samsung Black Weeks" is a marketing pill with 19 TVs and soundbars, no cashback. **Mix & Match (TV + sound device) ended 15.11.2026**; its PDF uses the same table layout as Frame Pro, so one Samsung parser covers both. Mix & Match rule confirmed: TV and soundbar may be bought at different retailers on different dates, registered together. | `globalPromotions`; Samsung Mix & Match and Frame Pro PDFs. |
| 6 | Discover offers without a product | **One `getIndex` call for the online shop per discovery run.** Store promotion sets are subsets of the online set (Freital: 3 online-only, Pasternak: 12 online-only, 0 store-only); the online-only ones are PayPal, PAYBACK and WERO10. | Diff of 3 indexes. |
| 7 | Store distance | **Postcode → coordinates with `api.zippopotam.us/de/<plz>`** once, stored in config. Store coordinates come from the store finder (348 stores with `latitude`/`longitude`). Haversine distance. | Tested with 01705 → Freital. |
| 8 | Other shops | Out of scope. Note: Samsung and Sony PDFs state "all participating retailers", so the cashback data model is shop-independent; a second price source could plug into the same offer. | PDFs. |

New API facts found during the analysis are recorded in [expert-api.md](expert-api.md) (section "Findings 2026-11-21").

### Decisions from the first review (2026-11-21, afternoon)

- **UI language German**, documentation English.
- **Location 14167 Berlin, radius 50 km.** Nearest stores: Berlin Tauentzien 4 km, Falkensee 21 km, Rangsdorf 25 km, Königs Wusterhausen 31 km, Fürstenwalde 50 km. Store names in the finder are partly generic ("ESC"); the app shows "expert <city>" plus postcode and street.
- **Alerts:** default = every price drop; per product switchable to target price or minimum drop (rule N1 changes accordingly).
- **Store links:** every store row links to `https://www.expert.de/shop/<webcode>-<slug>.html?branch_id=<store id>` and shows the postcode with a copy button, because the expert.de store picker works by postcode.
- **Online-Shop explained in the UI:** expert's central shop, ships from the central warehouse, own price, stock and codes (WERO10).
- **Product images:** `GET /api/search/article` → `primaryImage` id → `GET /api/medium/<id>` → `originalData` path → `https://cdn.expert.de/<originalData>`. Scanner stores a 640 px copy in `data/img/<webcode>.jpg`.
- **Product search:** no search endpoint exists (13 path variants probed, all `400 (Bad Request)` or `404`). Version 2 option: a name search over a cached article list built from the promotion index (17 841 article ids of the online shop, resolved once with `search/article`). Version 1 keeps the URL input.
- **Targets:** Philips 65OLED951 (webcode 11128346052, `e_977673`) and Sony BRAVIA 9 II 65"/75" (11128378730 / 11128379730). The Sony cashback (TV Winter 2026) covers BRAVIA 7 II and 8 II only; the 9 II has a set deal with the Theatre Bar 6 (−100 €) and no cashback.
- **Prototype design:** category-standard price-tracker look (white cards, product image per row, two prices side by side: Versand | Abholung, each naming its place; green = cheapest path), chosen by the user from a four-direction board. Design system recorded in DESIGN.md and .impeccable/design.json after the finish review (verdict: ship). Direction board (the four variants shown to the user): https://claude.ai/artifact/MJay7HjM79yGnRVh9SvQ26.
- **Prototype design, revised (2026-11-22):** the two-column price row is replaced by card B2. Card head: product image, name, subtitle, no price. Receipt rows: the cheapest path first (place, distance, stock, Aussteller badge, "kein Cashback" or "ohne Cashback"), the cashback deduction with its dates, the total "Dein Preis inkl. Cashback" (only with a cashback; otherwise the first row is the big price), the other path with "mit Cashback X €", set deals marked "nicht im Preis". Footer: 30-day sparkline of the daily best price, the movement ("−80 € seit gestern" or "−240 € in 30 Tagen") and the verdict ("Tiefstpreis seit 30 Tagen" or "60 € über dem 30-Tage-Tief von 3.399 €"); "Mehr" expands stores within the radius, the three cheapest shippers and all promotions including Zugaben. Green only when the effective price (after cashback) is the lowest of the last 30 days and at least 3 % under the 30-day high; the target price is optional. Product page: hero image, receipt rows and trend, cashback explanation, then Aktionen (cashback offer card, set deals, Zugaben), then alert settings, 30-day chart, stores as separate cards, shipping. The "Produkt hinzufügen" input moves to a plus button in the top bar. The list header hint "n am Tiefstpreis" is dropped. Prototype: prototype/b2.html, published at https://claude.ai/artifact/Y1dntJo3RAE6oRvnXTK2h2. Three-variant board (A Zwei Wege, B Bester Weg, C Preislage): prototype/variants.html, https://claude.ai/artifact/1dAJtj5qQMAKLFUqw5raxa.

### Decisions of 2026-11-22 (M0 planning)

- **Hosting stays a public repo.** On GitHub Free, a private repo gets $12 of compute per month (≈ 2 000 Linux minutes at $0.006/min; each job is rounded up to a whole minute; runs are blocked when the amount is used up), and GitHub Pages works only for public repos. The §3 schedule needs ≈ 2 100–3 000 minutes per month for 3–5 TVs. Also compared and rejected: public code + private data repo (two repos, personal docs must move, public logs must hide distances), Cloudflare Workers (free plan: 50 subrequests and 10 ms CPU per invocation, rewrite in JavaScript), Oracle Always Free VM (card, server upkeep, idle instances are reclaimed). The user accepts that the postcode, the watch list and the scan data are public.
- **Scan window 06:00–22:00 Berlin.** No scans at night: the first run at 06:15 picks up the changes of the night, and the user does not use the app at night. The schedules use the `timezone: "Europe/Berlin"` key of the Actions `schedule` event, so daylight saving time needs no code. No quiet hours (§5).
- **Data commits without `[skip ci]`.** Pushes with `GITHUB_TOKEN` start no workflow anyway, and `[skip ci]` can skip a branch-based Pages build (§7).
- **Commit address.** Commits in this repo use `81761762+moegelin@users.noreply.github.com` (repo-local git config), not the work address.
- **M0 probe.** Every run: store finder, 3 `pricepds` (Philips 65OLED951 at the Online-Shop, Sony BRAVIA 9 II 65" at Berlin Tauentzien, LG OLED65C69LB at Rangsdorf), `getIndex` of the Online-Shop. Sweep: `pricepds` for the Philips at all stores + Online-Shop (349 calls, 8 workers) in the first run and then when the last sweep is 6 h old, because 5 calls cannot show throttling at scan volume. The workflow runs hourly at :23 UTC around the clock and disables itself 72 h after the first run. A failed run turns red; the GitHub failure email is the alert until ntfy (M1).

## 2. Architecture

```mermaid
flowchart LR
  subgraph GH["GitHub (free)"]
    A["Actions cron\nscanner (Python)"] -->|commits JSON| R["repo: config/ + data/"]
    R --> P["GitHub Pages\nPWA (static)"]
  end
  A -->|8 parallel, retry 500| X["production.brntgs.expert.de\npricepds · bundlesForArticle\ngetIndex · search/article · storeFinder"]
  A -->|download| C["cdn.expert.de\nTeilnahmebedingungen PDF"]
  A -->|POST message| N["ntfy.sh topic"]
  A -->|ping per run| H["healthchecks.io\n(dead-man switch)"]
  N --> I["Galaxy S25: ntfy app"]
  P --> S["Galaxy S25: PWA on home screen"]
  S -->|optional: fine-grained PAT\nwrite config, trigger run| R
  Z["api.zippopotam.us"] -.->|postcode → lat/lng| S
```

Components:

- **Scanner** (`scanner/`, Python 3.12, stdlib + `pypdf`): one CLI with subcommands `stores`, `prices`, `sets`, `cashback`, `notify`. Runs locally and in Actions. No framework, no database.
- **Repo as database**: `config/*.json` (user input), `data/*.json` (scanner output). Every run commits its data, without `[skip ci]` (see §1, 2026-11-22). Git history is the price history backup.
- **PWA** (`app/`, static HTML/JS, no build step): reads `data/*.json` with `fetch`, renders the four screens of the prototype, installable on the home screen. Writes config through the GitHub Contents API when a fine-grained token (scope: this repo, Contents read/write, Actions read/write) is stored in the app; otherwise the user edits `config/watchlist.json` on GitHub.
- **Push**: ntfy topic with a random name (treated as a secret: Actions secret `NTFY_TOPIC`). Messages carry title, price line, store, distance, and a click URL to the product page with `?branch_id=<store>`.
- **Dead-man switch**: `healthchecks.io` free plan (20 checks). Pings at the end of each run. Missed ping → email/ntfy. Covers the silent disable of scheduled workflows after 60 days without activity (the data commits count as activity, but the check is the safety net).

## 3. Hosting details

| Item | Choice | Why |
|---|---|---|
| Repo visibility | Public | Unlimited Actions minutes on standard runners. Private = 2000 min/month, hourly runs would exceed it. The repo holds no secrets: ntfy topic, healthchecks URL, and PAT are Actions secrets or on the phone. |
| Runner | `ubuntu-latest`, Python 3.12 | Fastest cold start, no Docker. |
| Run length | 1–4 min per run | 35 s per product for prices (349 stores, 8 workers), 60–90 s for set deals (bundles are 20–65 KB per store). |
| Schedule delays | Accepted | Actions cron may run 5–30 min late. No requirement for exact times. |
| Fallback | Oracle Cloud Always Free ARM VM + cron, same scanner CLI | Only if milestone 0 shows Cloudflare blocking. |

### Batch scan schedule (cron in Europe/Berlin through the `timezone` key; no scans 22:00–06:00)

| Workflow | Cron | Work per run | Calls per run (5 watched products) |
|---|---|---|---|
| `scan-prices` | `15 6-21 * * *` (hourly 06:15–21:15, 16 runs; no night run) | `pricepds` for every watched product × 349 stores + online; compute best shipped / pickup; diff; notify | ≈ 1 750 |
| `scan-sets` | `45 6-21/3 * * *` | `bundlesForArticle` only for stores that offer the product (≈ 190 of 349 for a TV); diff set deals; notify | ≈ 950, ≈ 40 MB |
| `scan-cashback` | `30 6-21/6 * * *` | 1 × `getIndex` (online shop, 1.2 MB); filter `CASHBACK` promotions for watched brands and watched articles; download new PDFs; parse amounts; resolve qualifying TVs with `search/article` (cached in `data/articles.json`); refresh best prices of qualifying devices the user picked | 1 + ≤ 50 |
| `refresh-stores` | `0 6 * * 1` (weekly) | store finder → `data/stores.json`; alert when count changes by > 10 % | 1 |
| `probe` (milestone 0 only) | `23 * * * *` in UTC, around the clock; disables itself 72 h after the first run | 1 store finder, 3 `pricepds`, 1 `getIndex`; log status, `cf-mitigated`/challenge detection; sweep: `pricepds` for one TV at all stores in the first run and every 6 h | 5, plus 349 per sweep |

Rules: 8 workers, retry `500` three times with 1–2 s delay, exponential backoff on `429 (Too Many Requests)`, abort the run when > 20 % of calls fail (and notify). More than 10 watched products → split `scan-prices` into a matrix of 10 products per job. The requirement "150 stores, then the rest 30 minutes later" is not needed on Actions; a full scan of one product takes 35 s.

## 4. Data model

All files are JSON in the repo. `config/` is written by the user (or the PWA), `data/` by the scanner only.

```mermaid
erDiagram
  WATCHLIST ||--o{ PRODUCT : "webcode"
  WATCHLIST {
    object location "zip, lat, lng, maxDistanceKm"
    string[] brands "cashback brands to watch"
    object notify "min drop"
  }
  PRODUCT ||--o{ OFFER : "per store"
  PRODUCT ||--o{ SET_DEAL : "per store"
  PRODUCT ||--o{ HISTORY_POINT : "daily"
  PRODUCT {
    string webcode PK
    string articleId
    string name
    string brand
    number targetPrice "optional, from config"
    string role "watch | cashback-tv | cashback-soundbar"
    string alertMode "every | low30 | target"
    string image "data/img/<webcode>.jpg"
    object best "shipped, pickup (storeId, total)"
    string lastScan
  }
  OFFER {
    string storeId PK
    number price
    number shipping
    number codeDiscount "WERO10 etc."
    int onlineStock
    int storeStock
    string displayType "null | Restposten | Ausstellungsstueck"
    number totalShipped
    number totalPickup
    number distanceKm
  }
  SET_DEAL {
    string bundleId PK
    string storeId PK
    string promotionId
    string[] articleIds
    number unpromoted
    number promoted
    number discount
    number accessoryEffective "promoted - TV price at store"
    string validTo
  }
  CASHBACK ||--o{ QUALIFYING_DEVICE : "tv | soundbar"
  CASHBACK {
    string promotionId PK
    string title
    string brand
    string kind "cashback | free-extra | other"
    string buyFrom
    string buyTo
    string registerBy
    string registerUrl
    string pdfUrl
    string amountSource "pdf | override | unknown"
    string firstSeen
    string lastSeen
  }
  QUALIFYING_DEVICE {
    string modelCode PK
    string type "tv | soundbar"
    string articleId "expert, if found"
    string webcode
    number amount
    number amountDouble "with soundbar"
    number bestPrice
    string source "index | pdf | cross-sell | manual"
  }
  STORE {
    string id PK
    string name
    string city
    string zip
    string street
    number lat
    number lng
  }
  ALERT {
    string id PK
    string time
    string kind "price | target | set | cashback | restposten | failure"
    string webcode
    string text
    string url
  }
  STATUS {
    string lastRun
    string workflow
    number calls
    number failed
    string error
  }
```

Files:

| File | Content | Writer |
|---|---|---|
| `config/watchlist.json` | `location`, `brands`, `notify`, `products[]` (`webcode`, `label`, `targetPrice`, `watchSets`) | user / PWA |
| `config/cashback-overrides.json` | amounts and devices for offers the parser could not read | user |
| `data/stores.json` | 348 stores + online shop | `refresh-stores` |
| `data/products/<webcode>.json` | product, offers, sets, best, history (90 daily points: best shipped, best pickup) | `scan-prices`, `scan-sets` |
| `data/cashbacks.json` | all cashback-like promotions seen in the last 30 days, with qualifying devices | `scan-cashback` |
| `data/articles.json` | cache `articleId` → `webcode`, `name`, `brand`, `additionalArticles` | `scan-cashback` |
| `data/alerts.json` | last 200 alerts (the PWA inbox) | all |
| `data/status.json` | last run per workflow | all |

Best price formulas (unchanged from requirements):

- `totalShipped = price + shipping − codeDiscount` (codes from `promotionPrice.cashbackDiscount`, online only), only when `onlineStock > 0`.
- `totalPickup = price`, only when `storeStock > 0` and `distanceKm ≤ maxDistanceKm`.
- `accessoryEffective = set.promotedPrice − TV price at the same store`.
- Restposten counts as a normal offer; `displayType` is shown as a badge.

## 5. Notification rules

Every rule writes an `ALERT` and sends one ntfy message. No scans run 22:00–06:00 Berlin (§1, 2026-11-22), so no message is sent at night; there are no quiet hours.

| # | Rule | Condition | Cooldown |
|---|---|---|---|
| N1 | Price drop | per product one of three modes: **every drop** (default; any decrease of the effective best price, after cashback, against the **previous scan**, so a drop after a rise counts too), **new 30-day low** (only when the effective best price is below every value of the last 30 days), **target price** (see N2, only when a target is set) | 6 h per product and channel |
| N2 | Target price | optional per product; effective best total (after cashback) ≤ `targetPrice`; again only after it rose above the target in between | per crossing |
| N3 | Restposten / display deal | a `Restposten` or display offer within `maxDistanceKm` is ≥ 15 % below the best regular offer | once per store and product |
| N4 | New set deal | new `bundleId` for a watched product at the online shop or a store within range, or `discount` grows by ≥ 20 € | once per bundle and store |
| N5 | New cashback | new `CASHBACK` promotion whose brand is in `brands`, or whose `indexed` articles include a watched product. Second message when amounts become known (PDF parsed or override added). Third message 3 days before `buyTo`. | once per event |
| N6 | Cashback device price | best price of a qualifying device the user picked (role `cashback-tv` / `cashback-soundbar`) drops (same thresholds as N1) | 6 h |
| N7 | Scan failure | run aborted, > 20 % failed calls, non-JSON response (Cloudflare challenge), store count change > 10 %, or no successful run for 3 h (healthchecks.io, with a cron schedule in Europe/Berlin, so the night pause is no failure) | 1 per 6 h |

Rises are shown in the app (sparkline, "X € über dem 30-Tage-Tief") and never pushed (decided 2026-11-22).

Message format: `LG OLED65C69LB: 1 294 € pickup (was 1 339 €) · expert Bischofswerda, 32 km` with click URL `…?branch_id=e_…`, tags for the kind, priority `high` for N2 and N7.

## 6. Milestones

| M | Name | Deliverable | Done when |
|---|---|---|---|
| **M0** | Hosting probe | `probe` workflow + `scanner/expert_api.py` (client with retry/backoff) | 3 days of hourly runs from Actions show JSON responses, no challenge, no aborted run, < 10 % `500` at the first attempt. Decision hosting = Actions or fallback. |
| **M1** | Price scanner + push | `stores`, `prices`, `notify`; `config/watchlist.json`; `data/products/*.json`; ntfy N1, N2, N3, N7; healthchecks | Watching 3 TVs for a week with correct best prices (checked against the website) and alerts on the phone. |
| **M2** | PWA v1 | `app/` with watch list and product detail (screens 1–2 of the prototype), home-screen install, settings with postcode, radius, PAT | App on the phone shows the data within 1 min of a run; adding a product URL in the app triggers a scan. |
| **M3** | Set deals | `sets`; per-store set deals in product detail; N4 | LG DSC9S set shows 199 € effective at Pasternak and "no set" at Bischofswerda (verified example). |
| **M4** | Cashback | `cashback`; PDF parsers Samsung + Sony; qualifying TVs from the index; soundbars via cross-sell + manual; cashback list and detail with resale calculator (screens 3–4); N5, N6; `cashback-overrides.json` | Sony `e_4294` shows 8 TVs with single/double amounts and 6 soundbars; Samsung Frame Pro shows 4 TVs with amounts; calculator gives effective TV cost. |
| **M5** | Hardening | 90-day history sparkline, alert inbox, matrix split for > 10 products, docs | 30 days without a silent failure. |

Version 1 = M0–M4. M5 and the version-2 items in [features.md](features.md) come after the first month of use.

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Cloudflare blocks Azure runner IPs | no scans | M0 probe; fallback VM; the scanner CLI is host-independent |
| expert changes the API | silent wrong data | N7 on non-JSON or schema mismatch; verify endpoints and update expert-api.md |
| PDF layouts change | amounts unknown | parser reports "unknown", N5 still fires with the link; override file |
| GitHub disables the cron after 60 days | no scans | data commits keep the repo active; healthchecks catches it |
| Data commits do not reach GitHub Pages (M2) | the app shows old data | commits without `[skip ci]`; in M2, verify that a commit pushed with `GITHUB_TOKEN` updates Pages, else deploy Pages from the scanner workflow |
| ntfy.sh rate limits / outage | missed alerts | alerts are also in `data/alerts.json`, visible in the PWA |
| Private token on the phone | repo write access | fine-grained PAT limited to one repo, 90-day expiry; optional feature |
