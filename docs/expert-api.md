# expert.de API — findings (as of 2026-11-21)

Unofficial API. Found by analysis of the expert.de web app (Nuxt, server-side rendered) and by direct tests.
expert can change it at any time. Verify an endpoint before you build on it.

## Hosts

- `https://production.brntgs.expert.de` — API host. **No Cloudflare challenge from a home connection** (Berlin): plain HTTP clients (curl, Python `urllib`) work with a normal browser `User-Agent`. **GitHub Actions runners get a challenge** (see "Findings 2026-11-22 (M0 probe)").
- `https://www.expert.de` — web site. **Behind Cloudflare** (JS challenge, `307 (Temporary Redirect)` to a challenge page for plain clients). Do not scrape the HTML pages. The same `/api/...` paths also answer on this host from a browser.

## Endpoints

| Purpose | Method + path (on API host) | Status |
|---|---|---|
| All stores (348) | `POST /_api/storeFinder/searchStoresByGeoLocation` | ✅ works |
| Price, stock, shipping per store | `GET /api/pricepds?webcode=<webcode>&storeId=<store id>` | ✅ works |
| Sets / bundles of one article per store | `GET /api/search/bundlesForArticle?articleId=<articleId>&storeId=<store id>` | ✅ works |
| Promotion index per store | `GET /api/promotions/getIndex?storeId=<store id>` | ✅ works (~1.3 MB, 2026-11-22) |
| Bundles for list views | `POST /api/search/bundlesForListView` (body: `bundleIds`, `storeId`) | seen in JS, not tested |
| Summed bundle price | `GET /api/neo/bundle/getSummedBundle?bundleId=…&store=…&disabledArticles=…` | seen in JS, not tested |
| Article data by webcode | `GET /api/search/article?webcode=<webcode>` | not tested in this analysis |
| Search suggest | `GET /api/search/suggest?q=…` | ❌ `500` — gone. No replacement found. |
| Active promotions (old) | `GET /api/activePromotions` | ❌ `404` — replaced by `promotions/getIndex` |

### Store finder request

```http
POST /_api/storeFinder/searchStoresByGeoLocation
Content-Type: application/json
Cookie: fmarktcookie=e_2879130

{"lat":0,"lng":0,"maxResults":500,"source":"HTML5","withWebsite":true,
 "conditions":{"storeFinderResultFilter":"ALL"}}
```

Response: list of `{store: {id, expId, name, city, zip, street, latitude, longitude, canUseShop, decentralizedShop, openingHours, ...}, ...}`.

## IDs

- **webcode**: the number at the start of the product URL slug. `.../13110012744-returnal-ps5-spiel.html` → `13110012744`. Query parameters (`?awc=…`, `?branch_id=…`) are not relevant.
- **articleId**: for example `e_969892`. Get it from `pricepds` (`articleId`).
- **store id**: `e_<expId>`, for example `e_26051723` (expert Freital). `pricepds` also accepts the plain `expId`.
- **Online shop**: `e_2879130`. It is not in the store finder list. Add it by hand.
- Product page for one store: `<product url>?branch_id=<store id>`.

Known stores: Freital `e_26051723`, Pirna `e_26051722`, Pasternak Bochum `e_1907435`.

## Field reference

### `pricepds`

Top keys: `articleId`, `webcode`, `store`, `price`, `promotionPrice`, `warranties`.

- `price.bruttoPrice` — price. `null` → the store does not offer the article.
- `price.onlineStock` — units the store ships. `0` → pickup only.
- `price.storeStock` — units in the store.
- `price.itemOnDisplay` — `{onDisplay, type}`. `type` is for example `"Restposten"` (clearance). **Restposten also has `onDisplay: true`.** Use `type` to tell clearance from real display items.
- `price.shipmentArray[0].shipmentBruttoPrice` — shipping. It differs per store: online shop often `0`, stores `6.99` (small items) or `59.90`–`86.89` (TVs).
- `price.minOnlineDelivery` / `maxOnlineDelivery` — delivery days.
- `promotionPrice` — `currentPrice`, `directDiscount`, `directDiscountTitle`, `checkoutPrice`, `cashbackDiscount`, `cashbackTitle`, `afterCashbackPrice`. Holds direct discounts and codes such as WERO10 (−10 €). It does **not** hold set deals, manufacturer cashback, or free extras.

### `bundlesForArticle`

`{bundles: [...]}` — empty body when the store does not sell the article. Per bundle:

- `id` — for example `20000109`, `warranty:e_969892`.
- `articles[]` — `id`, `name`, `link`. The first article is the main product.
- `unPromotedPrice.gross`, `promotedPrice.gross` — set price before and after set discount.
- `discounts[]` — `{promotionId: {promotionId, modificationId}, discount: {gross}}`. A set discount has a negative `gross`. Manufacturer cashback and free extras appear with `gross: 0`.
- `deliveryCost.gross`, `onlineAvailability`, `validFrom`, `validTo`.

Effective accessory price = `promotedPrice` of the set − TV price at the same store.

### `promotions/getIndex`

- `indexed` — `articleId` → list of `modificationId` (for example `e_969892 → [e_4207_5247728, e_3157_9810]`). Per store.
- `compactPromotionData` — `modificationId` → `{promotionId, isSetPromotion, possibleDiscountRanges, showBubbleOnlyWhenOnlineAvailable, teaserMediumId}`. `possibleDiscountRanges` sometimes holds an amount (`discount`, `discountType: ABSOLUTE`).
- `globalPromotions` — `promotionId` → `{type, title, description (HTML), priority}`. The description holds conditions, dates, partner webcodes, and links (for example a PDF on `cdn.expert.de`, or the manufacturer page).

## Promotions

Types in `globalPromotions` (online shop, 2026-11-21): `CASHBACK` 84, `PRODUCT_SET` 43, `DIRECT_DISCOUNT` 4.

| Kind | Type | Amount in data? | Example |
|---|---|---|---|
| Code / direct discount | `CASHBACK` / `DIRECT_DISCOUNT` | yes, in `pricepds.promotionPrice` | `e_7779` "10€ Rabatt mit WERO10" (online only) |
| Set deal in the same cart | `PRODUCT_SET` | yes, exact, in `bundlesForArticle` | `e_4207` LG TV + DSC9S −200 €; `e_4205` Sony + Theatre Bar 6 −100 €; `e_4206` Sony + HTA7100 −200 € |
| Manufacturer cashback | `CASHBACK` | **no** (`gross: 0`). Only title, description, link | `e_4294` "Sony Cashback" → sony.de/cashback/TVWinter2026 + PDF |
| Free extras (game, streaming) | `CASHBACK` | no | `e_4203` "Assassin's Creed sichern!" (Philips); Samsung "Inklusive Streaming Content" |
| Other | `CASHBACK` | — | `e_3157` PayPal 0 % financing, `e_4066` "100 Tage testen" (Philips), `e_4290` PAYBACK points |

Rules:

- **Promotions differ per store.** Example: LG set deal `e_4207` exists at the online shop and Pasternak, but not at Bischofswerda. Online-only promotions (WERO10, PayPal) do not appear at stores.
- `PRODUCT_SET` descriptions list the participating webcodes (TVs and accessories) in the text: `(Webcode: 12220123509)`.
- Manufacturer cashback amounts are only in the manufacturer PDF or page. They are not in expert data.

## Request behaviour

- Full scan, 349 stores × 1 `pricepds` call, 8 parallel workers: 28–40 s.
- About 2–7 % of calls return `500` at first. All succeeded after a retry with a short delay. Always retry.
- No `429 (Too Many Requests)` seen at 8 parallel workers. The old script handled `429` with exponential backoff; keep that.
- `bundlesForArticle` responses are 20–65 KB. `getIndex` is ~1.3 MB (online shop, 2026-11-22); do not load it for every store on every run.
- **Response sizes, measured 2026-11-22** (uncompressed → with `Accept-Encoding: gzip`, which the client sends): `pricepds` 4.5–6.5 KB → 1.7–2.4 KB; `bundlesForArticle` 61 KB → 7 KB; `getIndex` 1.27 MB → 195 KB. A price scan of 5 TVs over 349 stores moves about 10 MB uncompressed, 4 MB on the wire; a set scan over all stores about 55 MB uncompressed, 7 MB on the wire. On the phone (hosting decision of 2026-11-22 in plan.md) this is the data volume on mobile data; set scans over all stores run on Wi-Fi or once a day.
- A `500` has a JSON body (`{"error": true, "url": …, "statusCode": 500, "statusMessage": "Server Error", "message": "Server Error"}`) and takes about 1.2 s; a `200` takes 0.1–0.5 s. Example of 2026-11-22: `pricepds` for `11128378730` at Berlin Tauentzien (`e_34627162`) returned `500`, `500`, then `200`, so it needed two retries. On 2026-11-23 at 10:40 CET the same call returned four `500`s in a row (1 of 763 calls in the phone test). A JSON `500` is a retry case, not a challenge; a call that fails after the retries counts as "unknown" in the scanner, not as a lost offer.
- **Thin bodies and a cold cache (phone test, 2026-11-23).** `pricepds` for the Philips 65OLED951 at the online shop returned 955 B instead of ≈ 4.5 KB at 06:50 and 10:40 CET with `articleId` and `price` present (the body was not recorded). The sweep of 349 stores at 06:50 found an offer (`price.bruttoPrice` not `null`) at 22 stores instead of 230 and had 15 first-try `500`s (4.3 %) instead of 2 the evening before. The response carries `price.cacheLevel` (seen: `MOST_RECENT`) and `price.cachedOn`; record them. The scanner keeps the previous offer for 24 h when one vanishes and marks a run incomplete when more than half of a product's offers vanish.
- Normal response headers (2026-11-22): `server: cloudflare`, `cf-cache-status: DYNAMIC`, `cf-ray: <id>-<data centre>` (`-TXL` from Berlin), `via: 1.1 google`, no `cf-mitigated`. A `cf-mitigated` header or a non-JSON body means a Cloudflare challenge.
- **No browser calls from other sites (CORS).** Every response carries `access-control-allow-origin: https://www.expert.de`, also for a request with `Origin: https://moegelin.github.io` (verified 2026-11-22). A web app on another origin cannot read the API; native apps and server code are not affected.

## Verified examples (2026-11-21)

| Product (webcode) | Finding |
|---|---|
| Returnal PS5 (`13110012744`) | Online 72.99 € (free shipping). Pirna 17 €, Freital 19 € — Restposten, store stock 1, pickup only. 189 of 349 locations have an offer. |
| LG OLED65C69LB (`11128647509`, `e_969892`) | Online 1349 € free shipping (−10 € WERO). Pasternak 1299 €. Bischofswerda, Bautzen, Görlitz and others 1214.10 € + 79.90 € shipping. Set with DSC9S: online 1748 → 1548 €, Pasternak 1698 → 1498 € (soundbar effectively 199 €). No set at Bischofswerda. |
| Sony K-65XR8M25B (`11128360730`, `e_944796`) | Online 2299 €. Set with Theatre Bar 6: 2718 → 2618 € (−100 €). Sony Cashback `e_4294` shown with 0 €. Freital page shows 2497 €. Pasternak: no bundles (not sold there). |
| Philips 55OLED851 (`11128342052`, `e_977668`) | Online 1099 €. Pasternak 1049 € + 59.90 € shipping. Free game `e_4203`, "100 Tage testen" `e_4066`. |

## Old script

Repo: https://github.com/DJGorex/expert-checker (last commit 2025-11-05, 15 stars).

- Interactive CLI (`input()`), writes an HTML report, opens the browser. No schedule, no notifications.
- Uses `search/suggest` (now `500`) and `activePromotions` (now `404`). The unhandled `404` in `get_discount()` most likely crashes the script after the store scan (not run end to end).
- The "Ausstellungsstücke anzeigen? n" filter drops `onDisplay: true` items. This hides Restposten deals such as Freital 19 €.
- Useful as reference for request headers, store list handling, and `429 (Too Many Requests)` backoff. A local copy of the store list is in the repo (`expert_branches.json`, 361 entries, older).

## Findings 2026-11-21 (plan analysis)

Verified with live calls while writing [plan.md](plan.md).

- **The API host is behind Cloudflare too** (`server: cloudflare`, `cf-ray`, `cf-cache-status: DYNAMIC`), but without a JS challenge for plain clients. Data-center IPs (GitHub Actions) are untested → milestone 0 probe. Watch for a non-JSON body or a `cf-mitigated` header.
- **`GET /api/search/article?articleId=<articleId>`** ✅ works (also `?webcode=`). Returns `name`, `title`, `webcode`, `articleId`, `brandId`, `primaryCategory`, `slug`, `link`, `primaryImage`, `technicalData`, `additionalArticles` (numeric ids of cross-sell articles, `945058` → `e_945058`), `crossSaleArticles`. 18 KB. Use it to resolve the article ids from `getIndex.indexed` to names, and `additionalArticles` to find soundbar candidates for a TV.
- **`globalPromotions` layout**: `{id, type, priority, showInCheckout, couponType, localizedProperties: {title, description, pillTheme, pillTitle}}`. Title and description are under `localizedProperties`, not at the top level.
- **`possibleDiscountRanges`** is `null` for TV cashbacks (Sony `e_4294`, Samsung `e_4288`). It is filled for household-appliance cashbacks (AEG `e_4257`: 30/50/100 €, Bosch `e_4104`, Siemens `e_4116`, Epson `e_4233`) and WERO10 (`e_7779`: 10 € from 50 €).
- **Cashback promotions are the same across stores.** Online shop 131 promotions; Freital 128 (3 online-only); Pasternak 119 (12 online-only: PayPal, PAYBACK, WERO10). No store-only promotion. One `getIndex` call for `e_2879130` is enough for discovery.
- **Qualifying devices.** `indexed` lists the TVs of a cashback, not the soundbars: Sony `e_4294` → 8 BRAVIA 7 II / 8 II TVs, 0 soundbars, although the offer doubles the amount with a soundbar. Samsung `e_4288` → 4 The Frame Pro TVs.
- **Amounts are in the PDF on `cdn.expert.de`** linked from the description. Layouts seen:
  - Samsung (`SEG_VSX_..._TNBs.pdf`): tables `Serie / Modell-Code / Zoll / EEK / Cashback`, one row per model code, e.g. `GQ65LS03HWUXZG 65 F¹ 150 €`. Model code = start of the expert article name. Same layout in Mix & Match (TV + sound device, 20.7.–15.11.2026, 100–2 500 €) and The Frame Pro Deals (16.11.–6.12.2026, 130–250 €).
  - Sony (`FY26_HE_Double-Cashback_Promo_Expert_BG-AT.pdf`): table `Bezeichnung / SAP Nummer / Cashback / Double-Cashback`, e.g. `65" BRAVIA 8 II K-65XR8M2 K65XR8M25B.CEI 250 € 500 €`, then a soundbar table (HT-A7100, HT-A7100KIT, HT-A9000, HT-A9M2, HT-A8, HT-A8KIT). Double cashback only when TV and soundbar are on the same invoice. Text extraction with `pypdf` splits words per line; join lines before matching.
- **Samsung at expert, 2026-11-21**: `e_4288` "Samsung Cashback" = The Frame Pro Deals (TV only). `e_4309` "Samsung Black Weeks" = marketing pill on 19 TVs and soundbars, no cashback. `e_4093` "Inklusive Streaming Content" = free extra on 87 Samsung articles. No TV + soundbar cashback active (Mix & Match ended 15.11.2026).
- **Postcode lookup**: `GET https://api.zippopotam.us/de/01705` → `places[0].latitude/longitude` (Freital, 50.9968 / 13.6499). Free, no key.
- **Store finder**: 348 stores, all with `latitude`/`longitude`, `canUseShop`, `decentralizedShop`.

### Additions 2026-11-21 (afternoon)

- **Product search: none.** Probed `GET`/`POST` on `/api/search/{suggest,search,articles,fulltext,query,articleSearch,autocomplete,products,suggestions,listing}`, `/api/search?q=`, `/api/neo/search`, `/_api/search`: all `400 (Bad Request)`, `404` or empty `204 (No Content)`. Name lookup must come from a cache built from `getIndex.indexed` + `search/article`.
- **Images.** `search/article` → `primaryImage` (media id) → `GET /api/medium/<id>` → `{originalData: "05/15/c6/.../Abbildung_2663599.png.png", alt, title}` → `https://cdn.expert.de/<originalData>` (public, 150 KB–1.3 MB, white background). `cdn.expert.de/<id>` without the path is `403 (Forbidden)`.
- **Store finder names** are partly generic: five stores around Berlin are called "ESC" (Berlin Tauentzienstr., Rangsdorf, Königs Wusterhausen, Fürstenwalde, Cottbus); show city and street.
- **Berlin example (14167, 50 km), 2026-11-21:** Philips 65OLED951 online 2298.99 € + 79.90 € (−10 € WERO10); Rangsdorf and Fürstenwalde 2095 € as Aussteller, 1 in store, 1 shippable. Sony K65XR95M2PB BRAVIA 9 II online 3469 € free shipping, no store within 50 km; set with Theatre Bar 6: 3888 → 3788 €. LG OLED65C69LB: Rangsdorf 1214.10 € pickup; set DSC9S at Rangsdorf 1666.69 → 1466.69 €. Samsung 65" Frame Pro: online 1529 € + 79.90 €, Berlin Tauentzien 1663 €, Rangsdorf 1499 €.
- **Sony cashback `e_4294` covers BRAVIA 7 II and 8 II only** (8 TVs); the BRAVIA 9 II is not in it.

## Findings 2026-11-22 (M0 probe)

First runs of the `probe` workflow (`ubuntu-latest`, Python 3.12, client `scanner/expert_api.py` with the headers of docs/plan.md M0):

| Run (UTC) | Runner data centre (`cf-ray`) | First call | Result |
|---|---|---|---|
| 15:13, run 45037047940 | `PDX` | `POST /_api/storeFinder/searchStoresByGeoLocation` | `403 (Forbidden)`, `cf-mitigated: challenge`, HTML "Just a moment..." page |
| 15:13, run 45037122117 | `SEA` | same | same |

- The probe stops at the first challenge, so the `GET` endpoints (`pricepds`, `getIndex`) were not called from Actions.
- The same client from Berlin at 15:10 and 15:12 UTC: all 5 calls `200`, data centre `TXL`; sweep of 349 `pricepds` in 14.4 s, 3 first-try `500`s, all recovered, no `429`.
- So Cloudflare challenges by client network (Azure data-centre IPs), not by request shape.

## Findings 2026-11-23 (phone test)

Same client on the Galaxy S25 in Termux (Python 3.14), hourly for 24 h, plan.md §1 "Phone test result": 13 runs, 763 calls, 0 challenges, 0 non-JSON bodies, 0 `429 (Too Many Requests)`, 20 first-try `500` (2.6 %), every call through data centre `TXL` on Wi-Fi and on mobile data (2 manual runs, 5 calls each). Sweeps of 349 `pricepds` took 14.0 s and 23.4 s (p95 646 and 954 ms). So a home or mobile connection passes Cloudflare; data-centre addresses do not (findings of 2026-11-22).
