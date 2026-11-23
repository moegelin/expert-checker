"""Step `prices` (docs/plan.md §3, §4): `pricepds` for every watched product at every store and the online
shop → `data/products/<webcode>.json` with the offers, the best shipped and pickup totals, a daily history
point and the product data (name, brand, image URL from `search/article` and `medium`).

Rules of §3: a call that fails after the retries, and a body without `bruttoPrice` where the previous scan
had an offer, count as "unknown": the previous offer is kept with a flag for up to 24 h. A run in which
more than half of a product's known offers vanish is marked incomplete (`scan.incomplete`); the alert step
sends no price alert for it. `price.cacheLevel` and `cachedOn` are recorded per offer and summed per scan. When a product's sweep
aborts (more than 20 % failed calls), it is retried once after a pause; a second abort ends the run.
"""

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from .expert_api import ChallengeError, ExpertApiError, RateLimitedError, ScanAborted
from .jsonfile import read_json, write_json
from .probe import berlin, iso, parse_time
from . import stores, watchlist

UNKNOWN_KEEP = timedelta(hours=24)
ABORT_RETRY_PAUSE = 20  # seconds; a burst of 500s right after a sweep aborted a product once (expert-api.md, 2026-11-23)
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
    }
    if previous.get("articleError"):
        record["articleError"] = previous["articleError"]
    if not record["articleId"] or not record["image"]:
        fetch_article(ctx.api, record)

    store_ids = [s["id"] for s in store_list]
    retried = False
    try:
        results = ctx.api.map(lambda store_id: ctx.api.pricepds(webcode, store_id), store_ids)
    except ScanAborted:
        SLEEP(ABORT_RETRY_PAUSE)  # one more try after a short pause; a second abort ends the run
        results = ctx.api.map(lambda store_id: ctx.api.pricepds(webcode, store_id), store_ids)
        retried = True
    by_id = {s["id"]: s for s in store_list}
    previous_offers = {o["storeId"]: o for o in previous.get("offers") or []}
    offers, scan = merge_offers(results, store_ids, by_id, previous_offers, ctx.now, max_distance_km)
    scan["time"] = iso(ctx.now)
    scan["retried"] = retried
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
    """Best shipped and pickup (§4). Known offers win over kept-unknown ones at the same total; then the nearer store."""
    def pick(key):
        candidates = [o for o in offers.values() if o.get(key) is not None]
        if not candidates:
            return None
        o = min(candidates, key=lambda o: (o[key], bool(o.get("unknown")), o["distanceKm"] if o["distanceKm"] is not None else 1e9, o["storeId"]))
        best = {"storeId": o["storeId"], "total": o[key], "price": o["price"], "distanceKm": o["distanceKm"],
                "displayType": o["displayType"]}
        if key == "totalShipped":
            best.update({"shipping": o["shipping"], "codeDiscount": o["codeDiscount"]})
        if o.get("unknown"):
            best["unknown"] = True
        return best

    return {"shipped": pick("totalShipped"), "pickup": pick("totalPickup")}


def update_history(history, date, best):
    """One point per Berlin day with the day's lowest best shipped and pickup totals; the last 90 days."""
    shipped = (best or {}).get("shipped")
    pickup = (best or {}).get("pickup")
    point = {"date": date, "shipped": shipped["total"] if shipped else None, "pickup": pickup["total"] if pickup else None}
    points = [p for p in history if p.get("date") != date]
    today = next((p for p in history if p.get("date") == date), None)
    if today:
        point = {"date": date, "shipped": _min(today.get("shipped"), point["shipped"]),
                 "pickup": _min(today.get("pickup"), point["pickup"])}
    points.append(point)
    points.sort(key=lambda p: p["date"])
    return points[-HISTORY_DAYS:]


def _min(a, b):
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None
