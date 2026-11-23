"""`config/watchlist.json` (docs/plan.md §4): the user's location, the brands to watch and the products.

Written by the user or the PWA, read by the steps. Every field has a default, so a minimal file is
`{"products": [{"url": "https://www.expert.de/shop/.../11128346052-65oled951-oled-tv.html"}]}`.
"""

import re

DEFAULT_RADIUS_KM = 50
ALERT_MODES = ("every", "low30", "target")
ROLES = ("watch", "cashback-tv", "cashback-soundbar")
WEBCODE = re.compile(r"(\d{8,})")


class WatchlistError(ValueError):
    pass


def load(config_dir):
    """The parsed watchlist with defaults applied. Raises WatchlistError when the file is missing or broken."""
    from .jsonfile import read_json

    path = config_dir / "watchlist.json"
    raw = read_json(path)
    if raw is None:
        raise WatchlistError(f"{path} is missing or not JSON")
    return normalize(raw, path)


def normalize(raw, path="config/watchlist.json"):
    location = dict(raw.get("location") or {})
    lat, lng = location.get("lat"), location.get("lng")
    products = []
    seen = set()
    for i, p in enumerate(raw.get("products") or []):
        webcode = parse_webcode(p.get("webcode") or p.get("url"))
        if webcode is None:
            raise WatchlistError(f"{path}: product {i + 1} has no webcode and no product URL")
        if webcode in seen:
            continue
        seen.add(webcode)
        mode = p.get("alertMode") or "every"
        if mode not in ALERT_MODES:
            raise WatchlistError(f"{path}: product {webcode}: alertMode must be one of {', '.join(ALERT_MODES)}")
        products.append({
            "webcode": webcode,
            "label": p.get("label") or webcode,
            "targetPrice": p.get("targetPrice"),
            "alertMode": mode,
            "watchSets": bool(p.get("watchSets", True)),
            "role": p.get("role") or "watch",
        })
    return {
        "location": {
            "zip": location.get("zip"),
            "lat": float(lat) if lat is not None else None,
            "lng": float(lng) if lng is not None else None,
            "maxDistanceKm": float(location.get("maxDistanceKm") or DEFAULT_RADIUS_KM),
        },
        "brands": list(raw.get("brands") or []),
        "notify": dict(raw.get("notify") or {}),
        "products": products,
    }


def parse_webcode(value):
    """`11128346052`, or the first run of at least 8 digits in a product URL (`.../11128346052-65oled951-oled-tv.html`)."""
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return text
    m = WEBCODE.search(text.split("?", 1)[0])
    return m.group(1) if m else None
