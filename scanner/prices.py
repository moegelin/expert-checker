"""Step `prices` (docs/plan.md §3, §4): `pricepds` for every watched product at every store and the online
shop → `data/products/<webcode>.json` with the offers, the best shipped and pickup totals, a daily history
point and the product data (name, brand, image URL from `search/article` and `medium`).

Rules of §3: a call that fails after the retries, and a body without `bruttoPrice` where the previous scan
had an offer, count as "unknown": the previous offer is kept with a flag for up to 24 h. A run in which
more than half of a product's known offers vanish is marked incomplete (`scan.incomplete`); the alert step
sends no price alert for it. `price.cacheLevel` and `cachedOn` are recorded per offer and summed per scan.

A store that does not list the article answers `500` for good (TCL 65C89L: 63 of 349 stores, 2026-11-27),
which looked like an outage to the 20 % abort rule. So: the stores whose call ended in an HTTP error last
scan (`scan.failedStores`) get one attempt and do not count for the rule. When a sweep still aborts, the
step pauses, asks up to three stores that just answered (the online shop without any) once more, and when
they answer, finishes the remaining stores without the rule: the failures are per store, not an outage.
When a control call fails too, the abort stands and ends the run.

Display items (`displayType` other than Restposten) are tracked beside the price, not in it: `best.shipped`
and `best.pickup` and the history points `shipped` and `pickup` cover new units only; `best.display` and the
history point `display` hold the cheapest display item on either path.
"""

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from .expert_api import ONLINE_SHOP, RETRIES, ChallengeError, ExpertApiError, RateLimitedError, ScanAborted
from .jsonfile import read_json, write_json
from .probe import berlin, iso, parse_time
from . import stores, watchlist

UNKNOWN_KEEP = timedelta(hours=24)
ABORT_RETRY_PAUSE = 20  # seconds; a burst of 500s right after a sweep aborted a product once (expert-api.md, 2026-11-23)
CONTROL_CALLS = 3  # stores that answered before the abort, asked once more after the pause
REGULAR_DISPLAY_TYPES = (None, "Restposten")  # Restposten counts as a normal offer (requirements)
SLEEP = time.sleep
INCOMPLETE_SHARE = 0.5
HISTORY_DAYS = 90
EXPERT_URL = "https://www.expert.de"
CDN_URL = "https://cdn.expert.de/"


def step(ctx):
    try:
        wl = watchlist.load(ctx.config)
    except watchlist.WatchlistError as e:
        raise ExpertApiError(str(e)) from e
    if not wl["products"]:
        raise ExpertApiError(f"no products in {ctx.config / 'watchlist.json'}")
    store_list = stores.load(ctx.data, wl["location"])
    if store_list is None:
        stores.step(ctx)
        store_list = stores.load(ctx.data, wl["location"])
    summary = {"products": 0, "withOffer": 0, "unknown": 0, "incomplete": [], "articleErrors": {}}
    for product in wl["products"]:
        record = scan_product(ctx, product, store_list, wl["location"]["maxDistanceKm"])
        summary["products"] += 1
        summary["withOffer"] += record["scan"]["withOffer"]
        summary["unknown"] += record["scan"]["unknown"]
        if record["scan"]["incomplete"]:
            summary["incomplete"].append(product["webcode"])
        if record.get("articleError"):
            summary["articleErrors"][product["webcode"]] = record["articleError"]
    return summary


def scan_product(ctx, product, store_list, max_distance_km):
    webcode = product["webcode"]
    path = product_path(ctx.data, webcode)
    previous = read_json(path) or {}
    record = {
        "webcode": webcode,
        "label": product["label"],
        "articleId": previous.get("articleId"),
        "name": previous.get("name"),
        "brand": previous.get("brand"),
        "brandId": previous.get("brandId"),
        "headline": previous.get("headline"),
        "image": previous.get("image"),
        "url": previous.get("url"),
        "targetPrice": product["targetPrice"],
        "alertMode": product["alertMode"],
        "watchSets": product["watchSets"],
        "role": product["role"],
        "lastScan": None,
        "scan": None,
        "best": None,
        "offers": [],
        "history": previous.get("history") or [],
        "sets": previous.get("sets") or [],
        "setsScan": previous.get("setsScan"),
        "promotionIds": previous.get("promotionIds") or [],
        "cashback": previous.get("cashback"),
    }
    if previous.get("articleError"):
        record["articleError"] = previous["articleError"]
    if not record["articleId"] or not record["image"]:
        fetch_article(ctx.api, record)

    store_ids = [s["id"] for s in store_list]
    expected = set((previous.get("scan") or {}).get("failedStores") or [])
    results, retried = sweep(ctx.api, webcode, store_ids, expected)
    by_id = {s["id"]: s for s in store_list}
    previous_offers = {o["storeId"]: o for o in previous.get("offers") or []}
    offers, scan = merge_offers(results, store_ids, by_id, previous_offers, ctx.now, max_distance_km)
    scan["time"] = iso(ctx.now)
    scan["retried"] = retried
    scan["failedStores"] = [sid for sid, r in zip(store_ids, results) if _http_error(r)]
    scan["failedAgain"] = sum(sid in expected for sid in scan["failedStores"])
    best = best_offers(offers)
    record.update({
        "lastScan": iso(ctx.now),
        "scan": scan,
        "best": best,
        "offers": [offers[k] for k in sorted(offers)],
        "history": update_history(record["history"], berlin(ctx.now).strftime("%Y-%m-%d"), best),
    })
    write_json(path, record)
    return record


def product_path(data_dir, webcode):
    return data_dir / "products" / f"{webcode}.json"


def sweep(api, webcode, store_ids, expected):
    """`pricepds` at every store. Returns (results in store order, retried). Stores in `expected` answered
    with an HTTP error last scan: one attempt, outside the abort rule. After an abort: pause, control calls,
    and the rest of the stores without the rule when the controls answer (see the module docstring)."""
    def call(store_id):
        return api.pricepds(webcode, store_id, retries=0 if store_id in expected else RETRIES)

    try:
        return api.map(call, store_ids, ignore=expected), False
    except ScanAborted as aborted:
        SLEEP(ABORT_RETRY_PAUSE)
        results = list(aborted.results or [None] * len(store_ids))
        answered = [sid for sid, r in zip(store_ids, results) if isinstance(r, dict)]
        controls = answered[:CONTROL_CALLS] or [ONLINE_SHOP]
        try:
            for store_id in controls:
                api.pricepds(webcode, store_id)
        except (ChallengeError, RateLimitedError):
            raise
        except ExpertApiError:
            raise ScanAborted(f"{aborted}; {len(controls)} control call(s) after {ABORT_RETRY_PAUSE} s failed too") from aborted
        remaining = [sid for sid, r in zip(store_ids, results) if not isinstance(r, dict)]
        rest = api.map(call, remaining, ignore=expected, abort=False)
        for store_id, result in zip(remaining, rest):
            results[store_ids.index(store_id)] = result
        return results, True


def _http_error(result):
    return isinstance(result, ExpertApiError) and result.outcome == "http_error"


def is_display(offer):
    """A real display item. Restposten (clearance) is a normal offer; see requirements."""
    return offer.get("displayType") not in REGULAR_DISPLAY_TYPES


def fetch_article(api, record):
    """Name, brand, article id, URL and image URL. A failed call is noted and does not stop the price scan."""
    try:
        article = api.search_article(record["webcode"]) or {}
        name = article.get("name") or article.get("title")
        headline = article.get("headline")
        record.update({
            "articleId": article.get("articleId") or record["articleId"],
            "name": name or record["name"],
            "brand": brand_from(headline, name) or record["brand"],
            "brandId": article.get("brandId") or record["brandId"],
            "headline": headline or record["headline"],
            "url": EXPERT_URL + article["link"] if article.get("link") else record["url"],
        })
        if article.get("primaryImage"):
            medium = api.medium(article["primaryImage"]) or {}
            if medium.get("originalData"):
                record["image"] = CDN_URL + medium["originalData"]
        record.pop("articleError", None)
    except (ChallengeError, RateLimitedError):
        raise
    except ExpertApiError as e:
        record["articleError"] = str(e)


def brand_from(headline, name):
    """`Philips 65OLED951 OLED TV (...)` with name `65OLED951 OLED TV` → `Philips`."""
    if not headline or not name:
        return None
    i = headline.find(name)
    if i <= 0:
        return None
    return headline[:i].strip() or None


def merge_offers(results, store_ids, by_id, previous_offers, now, max_distance_km):
    """The offers of this scan, with unknown ones kept from the previous scan (§3), and the scan totals."""
    offers = {}
    counts = Counter()
    cache_levels = Counter()
    known_before = {k for k, o in previous_offers.items() if not o.get("unknown")}
    vanished = 0
    for store_id, result in zip(store_ids, results):
        store = by_id[store_id]
        prev = previous_offers.get(store_id)
        if isinstance(result, Exception):
            reason = "failed"
        elif _brutto(result) is not None:
            offer = parse_offer(result, store, now, max_distance_km)
            offers[store_id] = offer
            counts["withOffer"] += 1
            cache_levels[offer["cacheLevel"] or "none"] += 1
            continue
        else:
            reason = "missing"
        counts[reason] += 1
        if prev is None:
            continue
        if store_id in known_before:
            vanished += 1
        since = prev.get("unknownSince") or iso(now)
        if now - parse_time(since) >= UNKNOWN_KEEP:
            counts["dropped"] += 1
            continue
        offers[store_id] = {**prev, "unknown": True, "unknownSince": since, "unknownReason": reason}
        counts["unknown"] += 1
    incomplete = bool(known_before) and vanished > INCOMPLETE_SHARE * len(known_before)
    scan = {
        "time": None,
        "stores": len(store_ids),
        "withOffer": counts["withOffer"],
        "failed": counts["failed"],
        "unknown": counts["unknown"],
        "vanished": vanished,
        "dropped": counts["dropped"],
        "incomplete": incomplete,
        "retried": False,
        "cacheLevels": dict(sorted(cache_levels.items())),
    }
    return offers, scan


def _brutto(payload):
    return ((payload or {}).get("price") or {}).get("bruttoPrice") if isinstance(payload, dict) else None


def parse_offer(payload, store, now, max_distance_km):
    price = payload["price"]
    promo = payload.get("promotionPrice") or {}
    amount = price["bruttoPrice"]
    shipping = _shipping(price)
    code_discount = round(abs(promo.get("directDiscount") or 0) + abs(promo.get("cashbackDiscount") or 0), 2)
    code_title = " · ".join(t for t in (promo.get("directDiscountTitle"), promo.get("cashbackTitle")) if t) or None
    online_stock = price.get("onlineStock") or 0
    store_stock = price.get("storeStock") or 0
    display = price.get("itemOnDisplay") or {}
    distance = store.get("distanceKm")
    total_shipped = round(amount + shipping - code_discount, 2) if online_stock > 0 and shipping is not None else None
    total_pickup = amount if store_stock > 0 and distance is not None and distance <= max_distance_km else None
    cached_on = price.get("cachedOn")
    return {
        "storeId": store["id"],
        "price": amount,
        "shipping": shipping,
        "codeDiscount": code_discount,
        "codeTitle": code_title,
        "onlineStock": online_stock,
        "storeStock": store_stock,
        "displayType": display.get("type") if display.get("onDisplay") else None,
        "totalShipped": total_shipped,
        "totalPickup": total_pickup,
        "distanceKm": distance,
        "cacheLevel": price.get("cacheLevel"),
        "cachedOn": iso(datetime.fromtimestamp(cached_on / 1000, timezone.utc)) if isinstance(cached_on, (int, float)) else None,
        "seen": iso(now),
    }


def _shipping(price):
    for s in price.get("shipmentArray") or []:
        if isinstance(s, dict) and s.get("shipmentBruttoPrice") is not None:
            return s["shipmentBruttoPrice"]
    return None


def best_offers(offers):
    """Best shipped and pickup of the new units, and the cheapest display item on either path (§4). Known
    offers win over kept-unknown ones at the same total; then the nearer store."""
    def rank(o, key):
        return (o[key], bool(o.get("unknown")), o["distanceKm"] if o["distanceKm"] is not None else 1e9, o["storeId"])

    def entry(o, key):
        best = {"storeId": o["storeId"], "total": o[key], "price": o["price"], "distanceKm": o["distanceKm"],
                "displayType": o["displayType"]}
        if key == "totalShipped":
            best.update({"shipping": o["shipping"], "codeDiscount": o["codeDiscount"]})
        if o.get("unknown"):
            best["unknown"] = True
        return best

    def pick(key):
        candidates = [o for o in offers.values() if o.get(key) is not None and not is_display(o)]
        return entry(min(candidates, key=lambda o: rank(o, key)), key) if candidates else None

    def display():
        candidates = [(o, key) for o in offers.values() if is_display(o)
                      for key in ("totalPickup", "totalShipped") if o.get(key) is not None]
        if not candidates:
            return None
        o, key = min(candidates, key=lambda c: rank(c[0], c[1]))
        return {**entry(o, key), "path": "pickup" if key == "totalPickup" else "shipped"}

    return {"shipped": pick("totalShipped"), "pickup": pick("totalPickup"), "display": display()}


HISTORY_KEYS = ("shipped", "pickup", "display")


def update_history(history, date, best):
    """One point per Berlin day with the day's lowest best shipped and pickup totals of new units and the
    day's cheapest display item; the last 90 days. Points before 2026-11-27 have no `display`."""
    best = best or {}
    point = {"date": date, **{k: best[k]["total"] if best.get(k) else None for k in HISTORY_KEYS}}
    points = [p for p in history if p.get("date") != date]
    today = next((p for p in history if p.get("date") == date), None)
    if today:
        point = {"date": date, **{k: _min(today.get(k), point[k]) for k in HISTORY_KEYS}}
    points.append(point)
    points.sort(key=lambda p: p["date"])
    return points[-HISTORY_DAYS:]


def _min(a, b):
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None
