"""Step `stores` (docs/plan.md §3, §4): the store finder → `data/stores.json`.

Every store with coordinates, the online shop added by hand (it is not in the finder list, expert-api.md),
and the Haversine distance from the location in `config/watchlist.json`. Weekly. A count change of more
than 10 % against the previous file is suspicious (a truncated list would make every missing store's offer
vanish in the price scan): the step keeps the old file and fails, which the next run retries and N7 reports
(§5). `python -m scanner stores --force` accepts the new list.
"""

import math

from .expert_api import ONLINE_SHOP, ExpertApiError
from .jsonfile import read_json, write_json
from .probe import iso
from . import watchlist

FILE = "stores.json"
ONLINE_NAME = "Online-Shop"
EARTH_RADIUS_KM = 6371.0088
COUNT_CHANGE_LIMIT = 0.10


class StoreCountChanged(ExpertApiError):
    """The finder returned a list whose size differs by more than 10 % from the previous one."""


def step(ctx):
    previous = read_json(ctx.data / FILE)
    location = _location(ctx)
    payload = ctx.api.store_finder()
    found = parse(payload)
    if not found:
        raise ExpertApiError("store finder returned no stores")
    before = previous["count"] if previous else None
    force = bool((getattr(ctx, "options", None) or {}).get("force"))
    if before and not force and abs(len(found) - before) > COUNT_CHANGE_LIMIT * before:
        raise StoreCountChanged(f"store count changed from {before} to {len(found)}; "
                                f"kept the old list (python -m scanner stores --force accepts the new one)")
    records = with_distances(found + [online_shop()], location)
    write_json(ctx.data / FILE, {
        "updated": iso(ctx.now),
        "count": len(found),
        "location": location,
        "stores": records,
    })
    within = sum(1 for s in records if s["distanceKm"] is not None and s["distanceKm"] <= location["maxDistanceKm"])
    return {"stores": len(found), "before": before, "withinRadius": within}


def parse(payload):
    """The finder entries as flat records, sorted by id (stable diffs)."""
    records = []
    for entry in payload or []:
        s = entry.get("store") or {}
        if not s.get("id"):
            continue
        records.append({
            "id": s["id"],
            "expId": s.get("expId"),
            "name": s.get("name"),
            "city": s.get("city"),
            "zip": s.get("zip"),
            "street": s.get("street"),
            "lat": s.get("latitude"),
            "lng": s.get("longitude"),
            "online": False,
            "canUseShop": s.get("canUseShop"),
            "decentralizedShop": s.get("decentralizedShop"),
        })
    return sorted(records, key=lambda r: r["id"])


def online_shop():
    return {"id": ONLINE_SHOP, "expId": ONLINE_SHOP[2:], "name": ONLINE_NAME, "city": None, "zip": None,
            "street": None, "lat": None, "lng": None, "online": True, "canUseShop": True, "decentralizedShop": False}


def with_distances(records, location):
    """Copies with `distanceKm` from `location` (None without coordinates on either side)."""
    lat, lng = location.get("lat"), location.get("lng")
    out = []
    for r in records:
        d = None
        if lat is not None and lng is not None and r.get("lat") is not None and r.get("lng") is not None:
            d = round(haversine_km(lat, lng, r["lat"], r["lng"]), 1)
        out.append({**r, "distanceKm": d})
    return out


def haversine_km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def load(data_dir, location=None):
    """The stores of `data/stores.json` (online shop included), or None when the file is missing.

    With `location`, the distances are recomputed when the file was written for another location.
    """
    data = read_json(data_dir / FILE)
    if not data or not isinstance(data.get("stores"), list):
        return None
    records = data["stores"]
    if location is not None and _coords(location) != _coords(data.get("location") or {}):
        records = with_distances(records, location)
    return records


def _coords(location):
    return (location.get("lat"), location.get("lng"))


def _location(ctx):
    try:
        return watchlist.load(ctx.config)["location"]
    except watchlist.WatchlistError:
        return {"zip": None, "lat": None, "lng": None, "maxDistanceKm": watchlist.DEFAULT_RADIUS_KM}
