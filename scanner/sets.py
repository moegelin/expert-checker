"""Step `sets` (docs/plan.md §3, §4; M3): `bundlesForArticle` for every watched product with `watchSets`
at every store that offers it (the offers of the last price scan, online shop included) → `sets` and
`setsScan` in `data/products/<webcode>.json`.

A set deal is a bundle with a negative set discount (`discounts[].discount.gross < 0`). Warranty bundles
(`warranty:…`) and accessory bundles without a discount (HDMI cable, 0 €) are not deals and are skipped.
Effective accessory price = promoted set price − the product's price at the same store (§4). Stores whose
call failed keep the sets of the previous scan; the scan block counts them.
"""

from .jsonfile import read_json, write_json
from .probe import iso
from . import prices, watchlist
from .expert_api import ExpertApiError


def step(ctx):
    try:
        wl = watchlist.load(ctx.config)
    except watchlist.WatchlistError as e:
        raise ExpertApiError(str(e)) from e
    summary = {"products": 0, "stores": 0, "sets": 0, "failed": 0, "skipped": []}
    for product in wl["products"]:
        if not product["watchSets"]:
            continue
        path = prices.product_path(ctx.data, product["webcode"])
        record = read_json(path)
        if not record or not record.get("articleId") or not record.get("offers"):
            summary["skipped"].append(product["webcode"])
            continue
        scan_product(ctx, record)
        write_json(path, record)
        summary["products"] += 1
        summary["stores"] += record["setsScan"]["stores"]
        summary["sets"] += len(record["sets"])
        summary["failed"] += record["setsScan"]["failed"]
    return summary


def scan_product(ctx, record):
    """Sets of one product at every store with an offer; updates `sets` and `setsScan` in place."""
    article_id = record["articleId"]
    offers = {o["storeId"]: o for o in record.get("offers") or []}
    store_ids = sorted(offers)
    results = ctx.api.map(lambda store_id: ctx.api.bundles_for_article(article_id, store_id), store_ids)
    previous = record.get("sets") or []
    sets, failed = [], []
    for store_id, result in zip(store_ids, results):
        if isinstance(result, Exception):
            failed.append(store_id)
            sets.extend(s for s in previous if s["storeId"] == store_id)
            continue
        offer = offers[store_id]
        for bundle in parse_bundles(result, article_id):
            sets.append({**bundle, "storeId": store_id, "distanceKm": offer.get("distanceKm"),
                         "productPrice": offer["price"],
                         "accessoryEffective": round(bundle["promoted"] - offer["price"], 2),
                         "seen": iso(ctx.now)})
    sets.sort(key=lambda s: (s["bundleId"], s["storeId"]))
    record["sets"] = sets
    record["setsScan"] = {"time": iso(ctx.now), "stores": len(store_ids), "withSet": len({s["storeId"] for s in sets}),
                          "failed": len(failed)}


def parse_bundles(payload, article_id):
    """The set deals in one `bundlesForArticle` response (expert-api.md, "bundlesForArticle")."""
    deals = []
    for bundle in (payload or {}).get("bundles") or [] if isinstance(payload, dict) else []:
        bundle_id = str(bundle.get("id") or "")
        if not bundle_id or bundle_id.startswith("warranty:"):
            continue
        discounts = [d for d in bundle.get("discounts") or [] if (_gross(d.get("discount")) or 0) < 0]
        if not discounts:
            continue
        promoted, unpromoted = _gross(bundle.get("promotedPrice")), _gross(bundle.get("unPromotedPrice"))
        if promoted is None:
            continue
        articles = [a for a in bundle.get("articles") or [] if isinstance(a, dict)]
        accessories = [a for a in articles if a.get("id") != article_id]
        deals.append({
            "bundleId": bundle_id,
            "promotionId": (discounts[0].get("promotionId") or {}).get("promotionId"),
            "articleIds": [a.get("id") for a in articles],
            "accessory": ", ".join(a.get("name") or a.get("id") or "" for a in accessories) or None,
            "accessoryIds": [a.get("id") for a in accessories],
            "unpromoted": unpromoted,
            "promoted": promoted,
            "discount": round(-sum(_gross(d.get("discount")) or 0 for d in discounts), 2),
            "validFrom": bundle.get("validFrom") or None,
            "validTo": bundle.get("validTo") or None,
        })
    return deals


def _gross(price):
    """`{gross: 2183.99}` → 2183.99; None without a number (a bundle without a price is skipped)."""
    if isinstance(price, dict) and isinstance(price.get("gross"), (int, float)):
        return price["gross"]
    return None
