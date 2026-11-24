"""Alerts N1, N2, N3 and N7 of docs/plan.md §5, evaluated after the steps of a run (run.py).

Every alert is appended to `data/alerts.json` (the PWA inbox, last 200) and sent once over ntfy. The file
also holds the rule state: cooldowns, the last effective price per product (N1 compares against the
previous scan), the target side per product (N2 fires per crossing) and the display offers already
reported (N3 fires once per store and product). A failed ntfy send never fails the run: the alert stays
in the file with `sent: false` and the run reports a warning.

Effective price = the lower of the best shipped and the best pickup total; manufacturer cashback (M4)
is not deducted yet. N4 (set deals, M3): a new bundle at the online shop or a store within the radius, or
a discount that grew by at least 20 €, once per bundle and store. N5 and N6 come with M4.
"""

from datetime import timedelta

from .jsonfile import read_json, write_json
from .probe import berlin, iso, parse_time
from . import prices, stores, watchlist

FILE = "alerts.json"
KEEP = 200
PRICE_COOLDOWN = timedelta(hours=6)
FAILURE_COOLDOWN = timedelta(hours=6)
COOLDOWN_KEEP = timedelta(days=7)
LOW_WINDOW = timedelta(days=30)
DISPLAY_BELOW = 0.15  # N3: a Restposten or display offer at least 15 % below the best regular offer
DEFAULT_MIN_DROP = 1.0  # € (config: notify.minDrop)
SET_GROWTH = 20.0  # € (N4: a known set's discount grew by at least this)
TAGS = {"price": ["chart_with_downwards_trend"], "target": ["dart"], "restposten": ["label"],
        "set": ["package"], "failure": ["rotating_light"]}
TITLES = {"price": "Price drop", "target": "Target price reached", "restposten": "Restposten deal",
          "set": "Set deal", "failure": "expert-checker: scan failed"}


class Alerts:
    def __init__(self, data_dir, ntfy, now):
        self.path = data_dir / FILE
        raw = read_json(self.path) or {}
        self.items = list(raw.get("alerts") or [])
        self.state = {"cooldowns": {}, "prices": {}, "target": {}, "restposten": {}, "sets": {}, **(raw.get("state") or {})}
        self.ntfy = ntfy
        self.now = now
        self.raised = []  # ids of this run's alerts
        self.warnings = []

    # Evaluation

    def evaluate(self, ctx, status):
        """N1–N3 for the products scanned in this run, N7 for this run's abort and failed steps. Returns the ids."""
        try:
            wl = watchlist.load(ctx.config)
        except watchlist.WatchlistError:
            wl = None
        if wl:
            by_id = {s["id"]: s for s in stores.load(ctx.data, wl["location"]) or []}
            min_drop = float(wl["notify"].get("minDrop", DEFAULT_MIN_DROP))
            radius = wl["location"]["maxDistanceKm"]
            for product in wl["products"]:
                record = read_json(prices.product_path(ctx.data, product["webcode"]))
                if record and record.get("lastScan") == iso(self.now):
                    self.product_rules(record, by_id, min_drop)
                if record and (record.get("setsScan") or {}).get("time") == iso(self.now):
                    self.set_rules(record, by_id, radius)
        self.failure_rules(status)
        return list(self.raised)

    def product_rules(self, record, by_id, min_drop=DEFAULT_MIN_DROP):
        webcode = record["webcode"]
        label = record.get("label") or record.get("name") or webcode
        current = effective(record)
        usable = current is not None and not (record.get("scan") or {}).get("incomplete") and not current["unknown"]
        if usable:
            self._price_drop(record, label, current, by_id, min_drop)
            self._target(record, label, current, by_id)
        self._display_deals(record, label, by_id)

    def _price_drop(self, record, label, current, by_id, min_drop):
        """N1 in the modes `every` and `low30`; `target` leaves drops to N2."""
        webcode = record["webcode"]
        previous = self.state["prices"].get(webcode)
        mode = record.get("alertMode") or "every"
        drop = previous["total"] - current["total"] if previous else 0
        wanted = drop >= min_drop and mode in ("every", "low30")
        if wanted and mode == "low30":
            low = thirty_day_low(record.get("history") or [], berlin(self.now).date(), self.now)
            wanted = low is None or current["total"] < low
        raised = False
        if wanted:
            text = (f"{label}: {fmt_price(current['total'])} {current['path']} (was {fmt_price(previous['total'])})"
                    f" · {store_text(by_id.get(current['storeId']), current['distanceKm'])}")
            raised = self.emit("price", f"price:{webcode}", text, url=store_url(record, current["storeId"]),
                               webcode=webcode, store_id=current["storeId"], cooldown=PRICE_COOLDOWN)
        # The baseline moves with the price, except when a drop was swallowed by the cooldown or is still
        # below minDrop: those keep the old baseline, so the drop is reported once it is due or big enough.
        if raised or drop <= 0 or (drop >= min_drop and not wanted):
            self.state["prices"][webcode] = {**current, "scan": record.get("lastScan")}

    def _target(self, record, label, current, by_id):
        """N2: effective total ≤ target, again only after it rose above the target in between."""
        webcode = record["webcode"]
        target = record.get("targetPrice")
        if target is None:
            self.state["target"].pop(webcode, None)
            return
        below = current["total"] <= target
        if below and self.state["target"].get(webcode) != "below":
            text = (f"{label}: {fmt_price(current['total'])} {current['path']} ≤ target {fmt_price(target)}"
                    f" · {store_text(by_id.get(current['storeId']), current['distanceKm'])}")
            self.emit("target", None, text, url=store_url(record, current["storeId"]), webcode=webcode,
                      store_id=current["storeId"], priority="high")
        self.state["target"][webcode] = "below" if below else "above"

    def _display_deals(self, record, label, by_id):
        """N3: a Restposten or display offer within the radius at least 15 % below the best regular offer."""
        webcode = record["webcode"]
        offers = record.get("offers") or []
        regular = [t for o in offers if not o.get("displayType") and not o.get("unknown")
                   for t in (o.get("totalShipped"), o.get("totalPickup")) if t is not None]
        best_regular = min(regular) if regular else None
        active = set()
        for o in offers:
            if not o.get("displayType"):
                continue
            key = f"{webcode}:{o['storeId']}"
            active.add(key)
            total = o.get("totalPickup")
            if o.get("unknown") or total is None or best_regular is None or key in self.state["restposten"]:
                continue
            if total > (1 - DISPLAY_BELOW) * best_regular:
                continue
            share = round((1 - total / best_regular) * 100)
            text = (f"{label}: {fmt_price(total)} {o['displayType']} pickup, {share} % below {fmt_price(best_regular)}"
                    f" · {store_text(by_id.get(o['storeId']), o.get('distanceKm'))}")
            self.emit("restposten", None, text, url=store_url(record, o["storeId"]), webcode=webcode,
                      store_id=o["storeId"])
            self.state["restposten"][key] = iso(self.now)
        for key in [k for k in self.state["restposten"] if k.startswith(webcode + ":") and k not in active]:
            del self.state["restposten"][key]  # gone; a later one at the same store is a new deal

    def set_rules(self, record, by_id, max_distance_km):
        """N4: a new set deal at the online shop or a store within the radius, or a discount that grew by
        20 € or more; once per bundle and store. The state holds the last discount per bundle and store."""
        webcode = record["webcode"]
        label = record.get("label") or record.get("name") or webcode
        active = set()
        for s in record.get("sets") or []:
            key = f"{webcode}:{s['bundleId']}:{s['storeId']}"
            active.add(key)
            store = by_id.get(s["storeId"]) or {}
            in_range = store.get("online") or (s.get("distanceKm") is not None and s["distanceKm"] <= max_distance_km)
            if not in_range:
                continue
            previous = self.state["sets"].get(key)
            if previous is not None and s["discount"] - previous < SET_GROWTH:
                continue
            eff = s.get("accessoryEffective")
            text = (f"{label}: set with {s.get('accessory') or 'accessory'} −{fmt_price(s['discount'])}"
                    f"{f', accessory effectively {fmt_price(eff)}' if eff is not None else ''}"
                    f"{f' until {s['validTo']}' if s.get('validTo') else ''} · {store_text(store, s.get('distanceKm'))}")
            self.emit("set", None, text, url=store_url(record, s["storeId"]), webcode=webcode, store_id=s["storeId"])
            self.state["sets"][key] = s["discount"]
        for key in [k for k in self.state["sets"] if k.startswith(webcode + ":") and k not in active]:
            del self.state["sets"][key]  # gone; the same bundle later is a new deal

    def failure_rules(self, status):
        """N7: an aborted run (challenge, rate limit, too many failed calls) or a failed step (for example a
        store count change of more than 10 %). One message per 6 h. Push failures: run.push_data."""
        problems = []
        if status.get("aborted"):
            problems.append(f"run aborted: {status['aborted']}")
        for name, s in (status.get("steps") or {}).items():
            if s.get("lastAttempt") == iso(self.now) and not s.get("ok"):
                problems.append(f"{name} failed: {s.get('error')}")
        if problems:
            self.emit("failure", "failure:run", "; ".join(problems), priority="high", cooldown=FAILURE_COOLDOWN)

    # Emit and save

    def emit(self, kind, key, text, url=None, webcode=None, store_id=None, priority=None, cooldown=None, title=None):
        """Records and sends one alert. False when `key` is inside its cooldown."""
        if key and cooldown:
            last = self.state["cooldowns"].get(key)
            if last and self.now - parse_time(last) < cooldown:
                return False
        title = title or TITLES[kind]
        sent = bool(self.ntfy.send(title, text, click=url, tags=TAGS[kind], priority=priority))
        item = {
            "id": ":".join(p for p in (iso(self.now), kind, webcode or key, store_id) if p),
            "time": iso(self.now),
            "kind": kind,
            "webcode": webcode,
            "storeId": store_id,
            "title": title,
            "text": text,
            "url": url,
            "sent": sent,
        }
        self.items.append(item)
        self.items = self.items[-KEEP:]
        self.raised.append(item["id"])
        if key and cooldown:
            self.state["cooldowns"][key] = iso(self.now)
        if not sent and getattr(self.ntfy, "enabled", True):
            error = self.ntfy.last_error() if hasattr(self.ntfy, "last_error") else "not sent"
            self.warnings.append(f"ntfy failed: {error}")
        return True

    def save(self):
        self.state["cooldowns"] = {k: t for k, t in self.state["cooldowns"].items()
                                   if self.now - parse_time(t) < COOLDOWN_KEEP}
        write_json(self.path, {"alerts": self.items, "state": self.state})


# Helpers

def effective(record):
    """The lower of the best shipped and the best pickup total, with its path and store."""
    best = record.get("best") or {}
    candidates = [(b["total"], path, b) for path, b in (("pickup", best.get("pickup")), ("shipped", best.get("shipped"))) if b]
    if not candidates:
        return None
    total, path, b = min(candidates, key=lambda c: c[0])
    return {"total": total, "path": path, "storeId": b["storeId"], "distanceKm": b.get("distanceKm"),
            "unknown": bool(b.get("unknown"))}


def thirty_day_low(history, today, now):
    """The lowest daily best of the 30 days before `today` (None without such days)."""
    start = (now - LOW_WINDOW).date().isoformat()
    values = [v for p in history if start <= p.get("date", "") < today.isoformat()
              for v in (p.get("shipped"), p.get("pickup")) if v is not None]
    return min(values) if values else None


def fmt_price(value):
    """`2095` → `2 095 €`, `2174.9` → `2 174,90 €` (plan.md §5 message format)."""
    if value is None:
        return "–"
    whole = int(value)
    cents = round((value - whole) * 100)
    if cents == 100:
        whole, cents = whole + 1, 0
    text = f"{whole:,}".replace(",", " ")
    return f"{text} €" if cents == 0 else f"{text},{cents:02d} €"


def store_text(store, distance_km):
    """`ESC Rangsdorf, 25 km` — name plus city when the name is generic (expert-api.md), then the distance."""
    if not store:
        return "unknown store"
    if store.get("online"):
        return "Online-Shop"
    name = store.get("name") or store.get("id")
    city = store.get("city")
    if city and city.lower() not in name.lower():
        name = f"{name} {city}"
    if distance_km is not None:
        name += f", {round(distance_km)} km"
    return name


def store_url(record, store_id):
    url = record.get("url")
    return f"{url}?branch_id={store_id}" if url and store_id else url
