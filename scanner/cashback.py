"""Step `cashback` (docs/plan.md §3, §4; M4): `promotions/getIndex` of the online shop every 6 h →
`data/cashbacks.json` (the promotions that matter: manufacturer cashback, free extras, and anything that
touches a watched product), `data/articles.json` (article cache) and, per watched product,
`promotionIds` and a `cashback` block in `data/products/<webcode>.json`.

Discovery: `globalPromotions` of type `CASHBACK` (the type expert uses for everything that is not a set or a
direct discount, expert-api.md "Promotions"). `indexed` (article → modification ids) inverted gives the
articles of a promotion. Kinds by title and description: `cashback` (money back), `extra` (game, streaming,
warranty, trial, voucher), `other` (PayPal, PAYBACK, marketing pills). A promotion is kept when it names a
watched brand or touches a watched product; `other` only when it touches one.

Amounts are not in expert data. For a `cashback` of a watched brand the Teilnahmebedingungen PDF on
`cdn.expert.de` is downloaded once per URL and parsed with pypdf: Samsung layout (`Modell-Code / Zoll /
EEK / Cashback`) and Sony layout (`Bezeichnung / SAP Nummer / Cashback / Double-Cashback` plus a soundbar
table). Other layouts, or no pypdf, leave `amountSource: unknown`; `config/cashback-overrides.json` fills
amounts, devices and conditions by hand. Qualifying devices come from `indexed` and `search/article`
(cached, at most 50 new lookups per run); soundbar candidates from the PDF are matched against the
accessories named in set-deal descriptions of the same brand. Device prices are the online shop's
(`pricepds`, one call per device); a device on the watch list shows its full best price in the app.
"""

import html
import re
import urllib.request
from datetime import date, datetime, timedelta

from .expert_api import ONLINE_SHOP, ChallengeError, ExpertApiError, RateLimitedError
from .jsonfile import read_json, write_json
from .probe import berlin, iso, parse_time
from . import prices, watchlist

try:  # pypdf is a pip package (phone/setup.sh); without it amounts stay unknown
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

FILE = "cashbacks.json"
ARTICLES_FILE = "articles.json"
OVERRIDES_FILE = "cashback-overrides.json"
KEEP_ENDED = timedelta(days=30)
PDF_MAX_AGE = timedelta(days=7)
ARTICLE_LOOKUPS = 50   # new `search/article` calls per run
PRICE_LOOKUPS = 40     # `pricepds` calls per run for devices and soundbars
TEXT_CHARS = 1500
PDF_TIMEOUT = 60
PDF_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36"

WEBCODE_IN_TEXT = re.compile(r"\(\s*Webcode:\s*(\d{8,})\s*\)")
DATE = r"(\d{1,2}\.\d{1,2}\.(?:\d{4})?)"
DATE_FULL = r"(\d{1,2}\.\d{1,2}\.\d{4})"
RANGE = re.compile(DATE + r"\s*(?:–|-|—|bis(?:\s+zum)?|und)\s*(?:zum\s+)?" + DATE_FULL)
BUY_UNTIL = re.compile(r"[Kk]auf\w*[^.]{0,80}?bis\s+(?:spätestens\s+)?(?:zum\s+)?" + DATE_FULL)
REGISTER = re.compile(r"[Rr]egistr", re.IGNORECASE)
REG_UNTIL = re.compile(r"bis\s+(?:spätestens\s+)?(?:zum\s+)?" + DATE_FULL)


class MissingPdfLibrary(Exception):
    """pypdf is not installed (phone/setup.sh installs it)."""


def pdf_text(url):
    """The text of the PDF on cdn.expert.de (not the API host: no retries, one try per run)."""
    import io
    if PdfReader is None:
        raise MissingPdfLibrary("pypdf is not installed")
    req = urllib.request.Request(url, headers={"User-Agent": PDF_USER_AGENT})
    with urllib.request.urlopen(req, timeout=PDF_TIMEOUT) as resp:
        raw = resp.read()
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


PDF_TEXT = pdf_text  # tests replace it


def step(ctx):
    try:
        wl = watchlist.load(ctx.config)
    except watchlist.WatchlistError as e:
        raise ExpertApiError(str(e)) from e
    brands = {b.lower() for b in wl["brands"]}
    previous = read_json(ctx.data / FILE) or {}
    data = {"promotions": dict(previous.get("promotions") or {}), "pdfs": dict(previous.get("pdfs") or {})}
    overrides = read_json(ctx.config / OVERRIDES_FILE) or {}
    records = {}
    for product in wl["products"]:
        rec = read_json(prices.product_path(ctx.data, product["webcode"]))
        if rec and rec.get("articleId"):
            records[product["webcode"]] = rec
    watched = {rec["articleId"]: rec for rec in records.values()}
    for rec in records.values():
        if rec.get("brand"):
            brands.add(rec["brand"].lower())

    index = ctx.api.promotion_index(ONLINE_SHOP)
    parsed = parse_index(index)
    accessories = accessory_candidates(parsed)
    articles = ArticleCache(ctx, budget=ARTICLE_LOOKUPS)
    pricer = Pricer(ctx, budget=PRICE_LOOKUPS)
    warnings = []
    promotions = {}
    for pid, p in parsed.items():
        if p["type"] != "CASHBACK":
            continue
        touches = [aid for aid in p["articleIds"] if aid in watched]
        brand = brand_in_text(p["title"] + " " + p["text"], brands)
        if brand is None and touches and p["kind"] != "other":
            brand = watched[touches[0]].get("brand")
        if p["kind"] == "other" and not touches:
            continue
        if not touches and not brand:
            continue
        if p["kind"] == "extra" and not touches and not TV_WORDS.search(p["title"] + " " + p["text"]):
            continue  # a watched brand's extra for other product groups (vacuum, watch, …)
        old = data["promotions"].get(pid) or {}
        entry = {
            "id": pid, "kind": p["kind"], "title": p["title"], "text": p["text"][:TEXT_CHARS], "url": p["url"],
            "pdfUrl": p["pdfUrl"], "brand": brand, "buyFrom": p["buyFrom"], "buyTo": p["buyTo"],
            "registerFrom": p["registerFrom"], "registerBy": p["registerBy"], "articleCount": len(p["articleIds"]),
            "watched": sorted(watched[aid]["webcode"] for aid in touches),
            "firstSeen": old.get("firstSeen") or iso(ctx.now), "lastSeen": iso(ctx.now), "active": True,
            "sameInvoice": None, "amountSource": "none", "devices": [], "soundbars": [],
        }
        if p["kind"] == "cashback":
            pdf = parsed_pdf(data["pdfs"], p["pdfUrl"], ctx.now, warnings) if p["pdfUrl"] else None
            fill_devices(entry, pdf, p["articleIds"], articles, pricer, watched, accessories, ctx.now)
        apply_override(entry, overrides.get(pid))
        promotions[pid] = entry
    for pid, old in data["promotions"].items():
        if pid in promotions:
            continue
        last = parse_time(old.get("lastSeen")) if old.get("lastSeen") else None
        if last and ctx.now - last < KEEP_ENDED:
            promotions[pid] = {**old, "active": False}
    articles.save()
    for webcode, rec in records.items():
        rec["promotionIds"] = sorted(promotion_ids(index, rec["articleId"]))
        rec["cashback"] = cashback_block(rec, promotions, ctx.now)
        write_json(prices.product_path(ctx.data, webcode), rec)
    used = {p["pdfUrl"] for p in promotions.values() if p.get("pdfUrl")}
    write_json(ctx.data / FILE, {
        "updated": iso(ctx.now),
        "promotions": dict(sorted(promotions.items())),
        "pdfs": {u: v for u, v in data["pdfs"].items() if u in used},
        "warnings": warnings,
    })
    active = [p for p in promotions.values() if p["active"]]
    return {
        "indexed": sum(1 for g in (index.get("globalPromotions") or {}).values() if g.get("type") == "CASHBACK"),
        "kept": len(promotions),
        "cashbacks": sum(1 for p in active if p["kind"] == "cashback"),
        "extras": sum(1 for p in active if p["kind"] == "extra"),
        "devices": sum(len(p["devices"]) for p in active),
        "articleLookups": articles.lookups,
        "priceLookups": pricer.lookups,
        "warnings": warnings,
    }


# ---- index

def parse_index(index):
    """`globalPromotions` with plain text, links, kind, dates and the articles of each promotion."""
    globals_ = index.get("globalPromotions") or {}
    compact = index.get("compactPromotionData") or {}
    by_promotion = {}
    for article_id, mods in (index.get("indexed") or {}).items():
        for mod in mods or []:
            pid = (compact.get(mod) or {}).get("promotionId") or mod.rsplit("_", 1)[0]
            by_promotion.setdefault(pid, set()).add(article_id)
    out = {}
    for pid, g in globals_.items():
        lp = g.get("localizedProperties") or {}
        title = (lp.get("title") or "").strip()
        description = lp.get("description") or ""
        text = plain_text(description)
        links = re.findall(r'href="([^"]+)"', description)
        pdf = next((l for l in links if "cdn.expert.de" in l and ".pdf" in l.lower()), None)
        url = next((l for l in links if l != pdf and "expert.de" not in l), None) or next((l for l in links if l != pdf), None)
        if not url:
            bare = re.search(r"(?<![\w/])((?:www\.)?[a-z0-9-]+\.(?:de|com|at|eu|net)/[\w/.-]+)", text)
            url = "https://" + bare.group(1) if bare else None
        dates = parse_dates(text)
        out[pid] = {"id": pid, "type": g.get("type"), "title": title, "text": text, "links": links, "pdfUrl": pdf,
                    "url": url, "kind": classify(title, text), "articleIds": sorted(by_promotion.get(pid, ())), **dates}
    return out


def promotion_ids(index, article_id):
    compact = index.get("compactPromotionData") or {}
    return {(compact.get(m) or {}).get("promotionId") or m.rsplit("_", 1)[0] for m in (index.get("indexed") or {}).get(article_id) or []}


def plain_text(markup):
    text = re.sub(r"<[^>]+>", " ", html.unescape(markup or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


OTHER = re.compile(r"payback|paypal|finanzierung|°punkte|altger[äa]t|made in germany|b-ware|gewährleistung|zertifi|"
                   r"saphirmatt|black weeks|hyrox|e-scooter|design|kompetenz|wero", re.IGNORECASE)
TRIAL = re.compile(r"\d+\s*tage\s*(geld|testen|zufrieden)|geld.?zur[üu]ck.?garantie", re.IGNORECASE)
CASHBACK = re.compile(r"cashback|bonus|geld.?zur[üu]ck|€\s*zur[üu]ck|rückerstattung", re.IGNORECASE)
TV_WORDS = re.compile(r"\btv\b|fernseher|soundbar|bravia|oled|qled|ambilight|streaming|heimkino|lautsprecher", re.IGNORECASE)
EXTRA = re.compile(r"gratis|geschenkt|inklusive|inkl\.|dazu|kostenlos|gutschein|garantie|testen|abonnement|sichern|"
                   r"monate|vorrat|voucher|gewinnspiel|zugabe|set\b|kapseln|content", re.IGNORECASE)


def classify(title, text=""):
    """`cashback` (money back), `extra` (something on top), `other` (payment, points, marketing)."""
    if OTHER.search(title):
        return "other"
    if TRIAL.search(title):
        return "extra"
    if CASHBACK.search(title):
        return "cashback"
    if EXTRA.search(title):
        return "extra"
    if TRIAL.search(text):
        return "extra"
    if CASHBACK.search(text) and not OTHER.search(text):
        return "cashback"
    if EXTRA.search(text):
        return "extra"
    return "other"


def brand_in_text(text, brands):
    """The first watched brand named in the text (case-insensitive, whole word), in its config spelling."""
    low = text.lower()
    for brand in sorted(brands, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(brand) + r"(?![a-z0-9])", low):
            return brand.capitalize() if brand.islower() else brand
    return None


def parse_dates(text):
    """buyFrom/buyTo from the first date range, registerFrom/registerBy from the sentence about registration."""
    out = {"buyFrom": None, "buyTo": None, "registerFrom": None, "registerBy": None}
    reg = REGISTER.search(text)
    head = text[:reg.start()] if reg else text
    tail = text[reg.start():] if reg else ""
    m = RANGE.search(head) or (RANGE.search(text) if not reg else None)
    if m:
        out["buyTo"] = iso_date(m.group(2))
        out["buyFrom"] = iso_date(m.group(1), out["buyTo"])
    else:
        m = BUY_UNTIL.search(head)
        if m:
            out["buyTo"] = iso_date(m.group(1))
    if tail:
        m = RANGE.search(tail)
        if m:
            out["registerBy"] = iso_date(m.group(2))
            out["registerFrom"] = iso_date(m.group(1), out["registerBy"])
        else:
            m = REG_UNTIL.search(tail)
            if m:
                out["registerBy"] = iso_date(m.group(1))
    return out


def iso_date(text, partner=None):
    """`10.01.2027` → `2027-01-10`; `12.11.` takes the partner's year, one earlier when it lies after it."""
    parts = text.strip(".").split(".")
    if len(parts) < 2:
        return None
    try:
        day, month = int(parts[0]), int(parts[1])
        if len(parts) >= 3 and parts[2]:
            year = int(parts[2])
        elif partner:
            year = int(partner[:4])
            if month > int(partner[5:7]) or (month == int(partner[5:7]) and day > int(partner[8:10])):
                year -= 1
        else:
            return None
        return date(year, month, day).isoformat()
    except ValueError:
        return None


# ---- PDFs

def parsed_pdf(cache, url, now, warnings):
    """The parsed PDF from the cache (`data/cashbacks.json`), downloaded and parsed when missing or old."""
    entry = cache.get(url)
    if entry and entry.get("parsed") and now - parse_time(entry["parsed"]) < PDF_MAX_AGE:
        return entry
    try:
        text = PDF_TEXT(url)
    except MissingPdfLibrary:
        warnings.append("pypdf is not installed: cashback amounts stay unknown")
        return cache.setdefault(url, {"parsed": None, "layout": "no-pypdf", "tvs": [], "bars": [], "sameInvoice": None})
    except Exception as e:  # noqa: BLE001 — a PDF problem must not stop the scan
        warnings.append(f"PDF {url.rsplit('/', 1)[-1]}: {type(e).__name__}: {e}")
        return entry or cache.setdefault(url, {"parsed": None, "layout": "error", "tvs": [], "bars": [], "sameInvoice": None})
    parsed = parse_pdf_text(text)
    parsed["parsed"] = iso(now)
    cache[url] = parsed
    return parsed


SONY_TV = re.compile(r"(\d{2})\s*[\"“”″]\s*(BRAVIA\s+\d+(?:\s+II)?)\s+K\s*-\s*([A-Z0-9]+)\s+([A-Z0-9]+)\.CE[IL]?\s+(\d+)\s*€\s+(\d+)\s*€")
SONY_BAR = re.compile(r"HT\s*-\s*([A-Z0-9]+)\s+([A-Z0-9]+)\.CEL")
SAMSUNG_ROW = re.compile(r"\b(GQ[A-Z0-9]{6,})\s+(\d{2})\s+\S+\s+(\d+)\s*€")


def parse_pdf_text(text):
    """Model codes and amounts from the Teilnahmebedingungen text (expert-api.md, "Amounts are in the PDF")."""
    flat = re.sub(r"\s+", " ", text)
    out = {"layout": "unknown", "tvs": [], "bars": [], "sameInvoice": None}
    if "SAP Nummer" in flat and "Double" in flat:
        out["layout"] = "sony"
        for inch, series, short, sap, single, double in SONY_TV.findall(flat):
            out["tvs"].append({"modelCode": f"K-{short}", "sap": sap, "label": f"{inch}\" {series}", "inch": int(inch),
                               "amount": int(single), "amountDouble": int(double)})
        last = 0
        bars_text = flat[flat.find("SOUNDBAR"):] if "SOUNDBAR" in flat else flat
        for m in SONY_BAR.finditer(bars_text):
            label = bars_text[last:m.start()].strip()
            label = re.sub(r".*(?:SAP Nummer|Bezeichnung)\s*", "", label).strip() or m.group(2)
            out["bars"].append({"modelCode": f"HT-{m.group(1)}", "sap": m.group(2), "label": label})
            last = m.end()
        out["sameInvoice"] = bool(re.search(r"derselben Rechnung|selben Rechnung|einer Rechnung", flat))
    elif "Modell-Code" in flat:
        out["layout"] = "samsung"
        for code, inch, amount in SAMSUNG_ROW.findall(flat):
            out["tvs"].append({"modelCode": code, "sap": code, "label": f"{inch}\"", "inch": int(inch), "amount": int(amount),
                               "amountDouble": None})
        out["sameInvoice"] = False
    return out


def norm(code):
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def match_tv(name, tvs):
    """The PDF row whose SAP number or model code is the start of the article name (`K-65XR8M25B BRAVIA…`)."""
    n = norm(name)
    best = None
    for tv in tvs:
        for code in (tv.get("sap"), tv.get("modelCode")):
            c = norm(code)
            if c and (n.startswith(c) or c in n) and (best is None or len(c) > best[0]):
                best = (len(c), tv)
    return best[1] if best else None


# ---- devices and prices

class ArticleCache:
    """`data/articles.json`: article id → name, webcode, brand, link; new lookups capped per run."""

    def __init__(self, ctx, budget=ARTICLE_LOOKUPS):
        self.ctx = ctx
        self.path = ctx.data / ARTICLES_FILE
        self.items = (read_json(self.path) or {}).get("articles") or {}
        self.budget = budget
        self.lookups = 0

    def get(self, article_id=None, webcode=None):
        key = article_id or f"wc:{webcode}"
        if key in self.items:
            return self.items[key]
        if self.lookups >= self.budget:
            return None
        self.lookups += 1
        try:
            if article_id:
                article = self.ctx.api.get_json("/api/search/article", articleId=article_id) or {}
            else:
                article = self.ctx.api.search_article(webcode) or {}
        except (ChallengeError, RateLimitedError):
            raise
        except ExpertApiError:
            return None
        name = article.get("name") or article.get("title")
        if not name:
            return None
        entry = {"articleId": article.get("articleId") or article_id, "webcode": article.get("webcode") or webcode,
                 "name": name, "brand": prices.brand_from(article.get("headline"), name),
                 "link": prices.EXPERT_URL + article["link"] if article.get("link") else None, "fetched": iso(self.ctx.now)}
        self.items[key] = entry
        if entry["articleId"]:
            self.items[entry["articleId"]] = entry
        return entry

    def save(self):
        write_json(self.path, {"updated": iso(self.ctx.now), "articles": self.items})


class Pricer:
    """Online-shop price of a device (`pricepds` at the online shop), capped per run."""

    def __init__(self, ctx, budget=PRICE_LOOKUPS):
        self.ctx = ctx
        self.budget = budget
        self.lookups = 0

    def get(self, webcode):
        if not webcode or self.lookups >= self.budget:
            return None
        self.lookups += 1
        try:
            payload = self.ctx.api.pricepds(webcode, ONLINE_SHOP)
        except (ChallengeError, RateLimitedError):
            raise
        except ExpertApiError:
            return None
        if not isinstance(payload, dict) or ((payload.get("price") or {}).get("bruttoPrice")) is None:
            return None
        offer = prices.parse_offer(payload, {"id": ONLINE_SHOP, "distanceKm": None}, self.ctx.now, 0)
        return {"price": offer["price"], "totalShipped": offer["totalShipped"], "onlineStock": offer["onlineStock"]}


def device_type(name):
    low = (name or "").lower()
    if "soundbar" in low or "sound" in low or "theatre" in low or "theater" in low:
        return "soundbar"
    if re.search(r"\btv\b|fernseher|oled|qled", low):
        return "tv"
    return "other"


def fill_devices(entry, pdf, article_ids, articles, pricer, watched, accessories, now):
    tvs = (pdf or {}).get("tvs") or []
    bars = (pdf or {}).get("bars") or []
    entry["sameInvoice"] = (pdf or {}).get("sameInvoice")
    entry["pdfLayout"] = (pdf or {}).get("layout")
    for aid in article_ids:
        art = articles.get(article_id=aid)
        if not art:
            entry["devices"].append({"articleId": aid, "webcode": None, "name": None, "type": "tv", "amount": None,
                                     "amountDouble": None, "source": "index", "watched": aid in watched})
            continue
        row = match_tv(art["name"], tvs)
        device = {"articleId": aid, "webcode": art["webcode"], "name": art["name"], "brand": art.get("brand"),
                  "type": device_type(art["name"]), "modelCode": (row or {}).get("modelCode") or art["name"].split()[0],
                  "amount": (row or {}).get("amount"), "amountDouble": (row or {}).get("amountDouble"),
                  "source": "pdf" if row else "index", "url": art.get("link"), "watched": aid in watched}
        if aid in watched:
            best = (watched[aid].get("best") or {})
            device["price"] = (best.get("pickup") or best.get("shipped") or {}).get("total")
            device["priceSource"] = "watchlist"
        else:
            price = pricer.get(art["webcode"])
            device.update({"price": price["totalShipped"] if price else None, "priceSource": "online" if price else None})
        entry["devices"].append(device)
    brand_key = (entry.get("brand") or "").lower()
    codes = sorted({norm(b["sap"]) for b in bars} | {norm(b["modelCode"]) for b in bars}, key=len, reverse=True)
    for bar in bars:
        own = {norm(bar["sap"]), norm(bar["modelCode"])}
        longer = [c for c in codes if c not in own and any(o and o in c for o in own)]
        candidate = next((c for c in accessories.get(brand_key, [])
                          if any(o and o in norm(c["text"]) for o in own) and not any(l in norm(c["text"]) for l in longer)), None)
        soundbar = {"modelCode": bar["modelCode"], "label": bar["label"], "webcode": None, "name": None, "price": None,
                    "priceSource": None, "url": None}
        if candidate:
            art = articles.get(webcode=candidate["webcode"])
            soundbar.update({"webcode": candidate["webcode"], "name": (art or {}).get("name") or candidate["text"][-80:],
                             "url": (art or {}).get("link")})
            price = pricer.get(candidate["webcode"])
            if price:
                soundbar.update({"price": price["totalShipped"], "priceSource": "online"})
        entry["soundbars"].append(soundbar)
    if entry["devices"] and any(d.get("amount") is not None for d in entry["devices"]):
        entry["amountSource"] = "pdf"
    elif entry["devices"]:
        entry["amountSource"] = "unknown"


def accessory_candidates(parsed):
    """Articles named in set-deal descriptions, by brand (first word of the chunk before `(Webcode: …)`)."""
    out = {}
    for p in parsed.values():
        if p["type"] != "PRODUCT_SET":
            continue
        text = p["text"]
        last = 0
        for m in WEBCODE_IN_TEXT.finditer(text):
            chunk = text[last:m.start()].strip()
            last = m.end()
            chunk = chunk.rsplit(")", 1)[-1].strip() if ")" in chunk else chunk
            words = chunk.split()
            if not words:
                continue
            brand = next((w for w in words if w[:1].isupper() and w.isalpha()), words[0]).lower()
            for key in {brand, words[-1].lower()}:
                out.setdefault(key, []).append({"webcode": m.group(1), "text": chunk, "promotionId": p["id"]})
            # a chunk such as "… in Kombination mit Sony BRAVIA Theatre Bar 6 …" names the brand mid-way
            for w in words:
                if w[:1].isupper() and w.isalpha() and w.lower() != brand:
                    out.setdefault(w.lower(), []).append({"webcode": m.group(1), "text": chunk, "promotionId": p["id"]})
    return out


def apply_override(entry, override):
    """`config/cashback-overrides.json`: amounts, devices and conditions by hand (plan.md §4)."""
    if not override:
        return
    for key in ("kind", "brand", "buyFrom", "buyTo", "registerFrom", "registerBy", "sameInvoice", "url", "title"):
        if override.get(key) is not None:
            entry[key] = override[key]
    devices = override.get("devices") or []
    if devices:
        by_code = {norm(d.get("modelCode") or d.get("webcode")): d for d in devices}
        for device in entry["devices"]:
            o = by_code.get(norm(device.get("modelCode"))) or by_code.get(norm(device.get("webcode"))) or \
                next((d for c, d in by_code.items() if c and c in norm(device.get("name"))), None)
            if o:
                device.update({k: o[k] for k in ("amount", "amountDouble", "type") if k in o})
                device["source"] = "override"
        known = {norm(d.get("modelCode")) for d in entry["devices"]} | {norm(d.get("webcode")) for d in entry["devices"]}
        known.discard("")
        for d in devices:
            if norm(d.get("modelCode")) in known or norm(d.get("webcode")) in known:
                continue
            target = entry["soundbars"] if d.get("type") == "soundbar" else entry["devices"]
            target.append({"articleId": None, "webcode": d.get("webcode"), "name": d.get("name") or d.get("modelCode"),
                           "modelCode": d.get("modelCode"), "label": d.get("name") or d.get("modelCode"),
                           "type": d.get("type") or "tv", "amount": d.get("amount"), "amountDouble": d.get("amountDouble"),
                           "price": None, "priceSource": None, "source": "override", "url": None, "watched": False})
        entry["amountSource"] = "override"


def cashback_block(record, promotions, now):
    """The active cashback of a watched product for the price rules and the app (None without one)."""
    today = berlin(now).date().isoformat()
    best = None
    for p in promotions.values():
        if not p["active"] or p["kind"] != "cashback" or record["webcode"] not in p["watched"]:
            continue
        if p.get("buyTo") and p["buyTo"] < today:
            continue
        device = next((d for d in p["devices"] if d.get("articleId") == record["articleId"]), None)
        block = {"promotionId": p["id"], "title": p["title"], "brand": p["brand"],
                 "amount": (device or {}).get("amount"), "amountDouble": (device or {}).get("amountDouble"),
                 "buyFrom": p["buyFrom"], "buyTo": p["buyTo"], "registerBy": p["registerBy"], "url": p["url"],
                 "sameInvoice": p["sameInvoice"], "amountSource": p["amountSource"]}
        if best is None or (block["amount"] or 0) > (best["amount"] or 0):
            best = block
    return best
