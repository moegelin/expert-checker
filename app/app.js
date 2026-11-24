/* expert-checker PWA (M2). Reads config/ and data/ of the repo from GitHub Pages and writes
   config/watchlist.json through the GitHub Contents API when a fine-grained token is stored
   on this phone (localStorage). No build step, no framework. Routes by hash:
   #liste | #p-<webcode> | #einstellungen. */
"use strict";

const APP_VERSION = "2026-11-24.2";
const REPO = "moegelin/expert-checker";
const BRANCH = "main";
const ROOT = new URL("../", location.href).href;        // repo root on Pages (data/, config/)
const ONLINE_ID = "e_2879130";
const STALE_HOURS = 4;                                  // the scanner runs every 2 h
const HISTORY_DAYS = 30;
const PENDING_MINUTES = 15;                             // how long a local write overrides a stale Pages copy
const EDIT_URL = `https://github.com/${REPO}/edit/${BRANCH}/config/watchlist.json`;
const DATA_URL = `https://github.com/${REPO}/tree/${BRANCH}/data`;
const TOKEN_URL = "https://github.com/settings/personal-access-tokens/new";

const state = {
  wlRaw: null, wl: null, status: null, stores: {}, products: {},
  loaded: false, error: null, loadedAt: 0,
  open: new Set(), openShip: new Set(), add: false,
  token: lsGet("gh-token") || "",
};

/* ===== Helpers ===== */
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
const eur = n => n == null ? "k. A." : new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) + " €";
const eur0 = n => n == null ? "k. A." : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(n) + " €";
const money = n => n == null ? "k. A." : (Math.abs(n % 1) > 0.001 ? eur(n) : eur0(n));
const km = d => d == null ? "" : `${Math.round(d)} km`;
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const round2 = n => Math.round(n * 100) / 100;
const todayISO = () => berlinDate(new Date());
function berlinDate(d) {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d);
  const g = t => p.find(x => x.type === t).value;
  return `${g("year")}-${g("month")}-${g("day")}`;
}
const fmtDate = iso => iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.` : "";
function ageText(iso) {
  const t = Date.parse(iso);
  if (isNaN(t)) return "unbekannt";
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return "gerade eben";
  if (m < 60) return `vor ${m} Min.`;
  const h = Math.floor(m / 60);
  if (h < 24) return `vor ${h} h${m % 60 ? ` ${m % 60} Min.` : ""}`;
  const d = Math.floor(h / 24);
  return d === 1 ? "vor 1 Tag" : `vor ${d} Tagen`;
}
const b64encode = s => btoa(Array.from(new TextEncoder().encode(s), b => String.fromCharCode(b)).join(""));
const b64decode = s => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), c => c.charCodeAt(0)));
const WEBCODE = /(\d{8,})/;
function parseWebcode(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (/^\d+$/.test(text)) return text;
  const m = WEBCODE.exec(text.split("?", 1)[0]);
  return m ? m[1] : null;
}

/* Icons: Tabler Icons (MIT), inline */
const ic = d => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const I = {
  check: ic('<path d="M5 12l5 5l10 -10"/>'),
  chev: ic('<path d="M6 9l6 6l6 -6"/>'),
  back: ic('<path d="M15 6l-6 6l6 6"/>'),
  plus: ic('<path d="M12 5l0 14"/><path d="M5 12l14 0"/>'),
  ext: ic('<path d="M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6"/><path d="M11 13l9 -9"/><path d="M15 4h5v5"/>'),
  info: ic('<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/><path d="M12 9h.01"/><path d="M11 12h1v4h1"/>'),
  warn: ic('<path d="M12 9v4"/><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z"/><path d="M12 16h.01"/>'),
  tv: ic('<path d="M3 7m0 2a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z"/><path d="M16 3l-4 4l-4 -4"/>'),
  cash: ic('<path d="M7 9m0 2a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v6a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2z"/><path d="M14 14m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/><path d="M17 9v-2a2 2 0 0 0 -2 -2h-10a2 2 0 0 0 -2 2v6a2 2 0 0 0 2 2h2"/>'),
  gear: ic('<path d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z"/><path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/>'),
  set: ic('<path d="M12 4l-8 4l8 4l8 -4l-8 -4"/><path d="M4 12l8 4l8 -4"/><path d="M4 16l8 4l8 -4"/>'),
  copy: ic('<path d="M7 7m0 2.667a2.667 2.667 0 0 1 2.667 -2.667h8.666a2.667 2.667 0 0 1 2.667 2.667v8.666a2.667 2.667 0 0 1 -2.667 2.667h-8.666a2.667 2.667 0 0 1 -2.667 -2.667z"/><path d="M4.012 16.737a2.005 2.005 0 0 1 -1.012 -1.737v-10c0 -1.1 .9 -2 2 -2h10c.75 0 1.158 .385 1.5 1"/>'),
  reload: ic('<path d="M19.933 13.041a8 8 0 1 1 -9.925 -8.788c3.899 -1 7.935 1.007 9.425 4.747"/><path d="M20 4v5h-5"/>'),
};
const tri = dir => `<svg class="i tri" viewBox="0 0 24 24" aria-hidden="true"><path d="${dir === "dn" ? "M6 9h12l-6 8z" : "M6 15h12l-6-8z"}" fill="currentColor" stroke="none"/></svg>`;

/* ===== Data: load from Pages ===== */
async function getJSON(path) {
  const r = await fetch(ROOT + path + "?v=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
/* Mirror of scanner/watchlist.py normalize(): defaults applied, duplicates dropped. */
function normalize(raw) {
  const loc = Object.assign({}, raw.location || {});
  const seen = new Set(), products = [];
  (raw.products || []).forEach(p => {
    const webcode = parseWebcode(p.webcode || p.url);
    if (!webcode || seen.has(webcode)) return;
    seen.add(webcode);
    products.push({ webcode, url: p.url || null, label: p.label || webcode, targetPrice: p.targetPrice == null ? null : +p.targetPrice,
      alertMode: p.alertMode || "every", watchSets: p.watchSets !== false, role: p.role || "watch" });
  });
  return {
    location: { zip: loc.zip || null, lat: loc.lat == null ? null : +loc.lat, lng: loc.lng == null ? null : +loc.lng, maxDistanceKm: +(loc.maxDistanceKm || 50) },
    brands: raw.brands || [], notify: raw.notify || {}, products,
  };
}
/* A write of this app is visible on Pages only after the build (about a minute). Until then the local copy wins. */
function applyPending(fetched) {
  let pending = null;
  try { pending = JSON.parse(lsGet("wl-pending") || "null"); } catch (e) { pending = null; }
  if (!pending) return fetched;
  const fresh = Date.now() - pending.t < PENDING_MINUTES * 60000;
  if (!fresh || JSON.stringify(pending.wl) === JSON.stringify(fetched)) { lsSet("wl-pending", null); return fetched; }
  return pending.wl;
}
async function load(silent) {
  try {
    const [wlRaw, status, stores] = await Promise.all([
      getJSON("config/watchlist.json"),
      getJSON("data/status.json").catch(() => null),
      getJSON("data/stores.json").catch(() => null),
    ]);
    state.wlRaw = applyPending(wlRaw);
    state.wl = normalize(state.wlRaw);
    state.status = status;
    state.stores = {};
    ((stores && stores.stores) || []).forEach(s => { state.stores[s.id] = s; });
    const recs = await Promise.all(state.wl.products.map(p => getJSON(`data/products/${p.webcode}.json`).catch(() => null)));
    state.products = {};
    recs.forEach((r, i) => { if (r) state.products[state.wl.products[i].webcode] = r; });
    state.loaded = true; state.error = null; state.loadedAt = Date.now();
    if (silent) toast("Aktualisiert");
  } catch (e) {
    state.error = e.message || String(e);
    if (!state.loaded) state.loadedAt = Date.now();
  }
  route();
}

/* ===== Stores ===== */
function storeOf(id) {
  return state.stores[id] || { id, name: id === ONLINE_ID ? "Online-Shop" : "Markt", city: null, zip: null, street: null, online: id === ONLINE_ID, distanceKm: null };
}
const cityOf = s => (s.city || "").split("/")[0].trim();
function storeName(s) {
  if (s.online) return "expert Online-Shop";
  const city = cityOf(s);
  if (!city) return s.name || s.id;
  const first = city.split(/[\s-]/)[0].toLowerCase();
  return (s.name || "").toLowerCase().includes(first) ? s.name : `${s.name} ${city}`;
}
const productUrl = p => p.url || (p.rec && p.rec.url) || `https://www.expert.de/shop/${p.webcode}.html`;
const storeUrl = (p, storeId) => storeId && storeId !== ONLINE_ID ? `${productUrl(p)}?branch_id=${storeId}` : productUrl(p);

/* ===== Per product: offers, best paths, history, verdict ===== */
function splitTop(s) {
  const out = []; let d = 0, cur = "";
  for (const c of s) { if (c === "(") d++; if (c === ")") d--; if (c === "," && d === 0) { out.push(cur.trim()); cur = ""; } else cur += c; }
  if (cur.trim()) out.push(cur.trim());
  return out;
}
function subtitle(rec, title) {
  const h = rec.headline || "", i = h.indexOf("(");
  const feats = i >= 0 ? splitTop(h.slice(i + 1, h.lastIndexOf(")") > i ? h.lastIndexOf(")") : h.length)) : [];
  const used = new Set(title.toLowerCase().replace(/["″]/g, "").split(/\s+/));
  const rest = (rec.name || "").split(/\s+/).filter(w => !used.has(w.toLowerCase())).join(" ");
  return [rest, ...feats.slice(0, 2).map(f => f.replace(/\s*\([^)]*\)/g, ""))].filter(Boolean).join(" · ");
}
function titleOf(cfg, rec) {
  if (cfg.label && cfg.label !== cfg.webcode) return cfg.label;
  if (rec && (rec.brand || rec.name)) return `${rec.brand || ""} ${rec.name || ""}`.trim();
  return `Produkt ${cfg.webcode}`;
}
function enrich(cfg) {
  const rec = state.products[cfg.webcode] || null;
  const radius = state.wl.location.maxDistanceKm;
  const name = titleOf(cfg, rec);
  if (!rec) return { ...cfg, rec, name, sub: "wird beim nächsten Scan aufgenommen", image: null, pending: true, radius };
  const offers = (rec.offers || []).map(o => {
    const s = storeOf(o.storeId);
    const inRange = !s.online && o.distanceKm != null && o.distanceKm <= radius;
    return { ...o, s, inRange, shipped: o.onlineStock > 0 && o.totalShipped != null ? o.totalShipped : null, pickup: inRange && o.storeStock > 0 ? o.price : null };
  });
  const byTotal = k => (a, b) => a[k] - b[k] || (a.unknown ? 1 : 0) - (b.unknown ? 1 : 0) || (a.distanceKm == null ? 1e9 : a.distanceKm) - (b.distanceKm == null ? 1e9 : b.distanceKm);
  const ship = offers.filter(o => o.shipped != null).sort(byTotal("shipped"))[0] || null;
  const pick = offers.filter(o => o.pickup != null).sort(byTotal("pickup"))[0] || null;
  const cb = 0, off = null;                      // manufacturer cashback comes with M4
  const shipEff = ship ? round2(ship.shipped - cb) : null, pickEff = pick ? round2(pick.pickup - cb) : null;
  const bestKind = !pick ? "ship" : !ship ? "pick" : (pickEff <= shipEff ? "pick" : "ship");
  const bestOff = bestKind === "pick" ? pick : ship;
  const gross = bestOff ? (bestKind === "pick" ? bestOff.pickup : bestOff.shipped) : null;
  const best = gross != null ? round2(gross - cb) : null;
  // history: one point per Berlin day, the lower of best shipped and best pickup; the last 30 days
  const cutoff = new Date(Date.now() - HISTORY_DAYS * 86400000).toISOString().slice(0, 10);
  const hist = (rec.history || []).filter(h => h.date >= cutoff);
  const series = hist.map(h => { const v = [h.shipped, h.pickup].filter(x => x != null); return v.length ? Math.min(...v) : null; });
  const vals = series.filter(v => v != null);
  const min30 = vals.length ? Math.min(...vals) : null, max30 = vals.length ? Math.max(...vals) : null;
  const li = series.length - 1;
  const today = li >= 0 && series[li] != null ? series[li] : best, yday = li >= 1 ? series[li - 1] : null;
  const delta = today != null && yday != null ? round2(today - yday) : null;
  const chg30 = vals.length >= 2 && today != null ? round2(today - vals[0]) : null;
  const good = best != null && vals.length >= 2 && best <= min30 && (max30 - best) / max30 >= 0.03;
  const target = cfg.targetPrice == null ? null : cfg.targetPrice;
  return {
    ...cfg, rec, name, sub: subtitle(rec, name), image: rec.image || null, radius, pending: false,
    off, cb, offers, ship, pick, shipEff, pickEff, bestKind, bestOff, gross, best, good, target,
    aboveLow: best != null && min30 != null ? round2(best - min30) : null,
    atTarget: target != null && best != null && best <= target,
    toTarget: target != null && best != null ? round2(best - target) : null,
    delta, chg30, min30, max30, series, hist,
    inR: offers.filter(o => o.inRange).sort((a, b) => a.distanceKm - b.distanceKm),
    far: offers.filter(o => !o.s.online && !o.inRange && o.shipped != null).sort(byTotal("shipped")),
    on: offers.find(o => o.s.online) || null,
    sets: rec.sets || [],
    scan: rec.scan || {},
  };
}
const setEff = (p, x) => { const tv = p.offers.find(o => o.storeId === x.storeId); return tv && x.promoted != null ? round2(x.promoted - tv.price) : null; };
const setName = x => x.accessory || x.name || x.title || "Zubehör";
const dispBadge = o => o && o.displayType ? `<span class="badge b-aus">${esc(o.displayType)}</span>` : "";
const unknownNote = o => o && o.unknown ? ", Preis vom letzten Scan" : "";
function codeName(o) { const m = /\b([A-Z]{3,}\d{1,3})\b/.exec(o.codeTitle || ""); return m ? `Code ${m[1]}` : (o.codeTitle || "Gutscheincode"); }
function codeLine(o) { return o.codeDiscount ? `, ${esc(codeName(o))} −${eur0(o.codeDiscount)}` : ""; }

/* ===== Receipt rows, trend, sparkline ===== */
function ledger(p, big) {
  const lr = (l, s, v, cls) => `<div class="lr ${cls || ""}"><div class="l">${l}${s ? `<small>${s}</small>` : ""}</div>${v ? `<div class="v">${v}</div>` : ""}</div>`;
  const label = k => k === "pick" ? "Abholung" : "Versand";
  const sub = (o, k) => k === "pick"
    ? `${esc(storeName(o.s))}, ${km(o.distanceKm)}, ${o.storeStock} im Markt${unknownNote(o)}`
    : (o.s.online ? `Online-Shop, ${o.shipping ? `${money(o.price)} + ${eur(o.shipping)}` : "versandkostenfrei"}${codeLine(o)}${unknownNote(o)}`
      : `${esc(storeName(o.s))}, ${money(o.price)} + ${eur(o.shipping)} Versand${codeLine(o)}${unknownNote(o)}`);
  const rows = [], o = p.bestOff, k = p.bestKind;
  if (!o) rows.push(lr("Kein Angebot", `weder Versand noch ein Markt im Umkreis von ${p.radius} km`, "", "alt"));
  else if (p.cb) {
    rows.push(lr(`${I.check}${label(k)}${dispBadge(o)}`, `${sub(o, k)}, ohne Cashback`, money(p.gross), "first"));
    rows.push(lr(`${esc(p.off.brand)} Cashback`, `Kauf bis ${p.off.to}, registrieren bis ${p.off.regBy}`, `− ${eur0(p.cb)}`, "cash"));
    rows.push(lr("Dein Preis inkl. Cashback", big ? `${label(k)} bei ${esc(storeName(o.s))}` : "", money(p.best), `main ${p.good ? "ok" : ""}`));
  } else rows.push(lr(`${I.check}${label(k)}${dispBadge(o)}`, `${sub(o, k)}, kein Cashback`, money(p.best), `main ${p.good ? "ok" : ""}`));
  const ak = k === "pick" ? "ship" : "pick", a = ak === "ship" ? p.ship : p.pick;
  if (a) rows.push(lr(`${label(ak)}${dispBadge(a)}`, `${sub(a, ak)}${p.cb ? `, mit Cashback ${money(ak === "ship" ? p.shipEff : p.pickEff)}` : ""}`, money(ak === "ship" ? a.shipped : a.pickup), "alt"));
  else if (o) rows.push(lr(label(ak), ak === "ship" ? "niemand verschickt gerade" : `kein Markt im Umkreis von ${p.radius} km`, "", "alt"));
  (big ? p.sets : p.sets.slice(0, 1)).forEach(x => {
    const eff = setEff(p, x), s = storeOf(x.storeId);
    rows.push(lr(`Set mit ${esc(setName(x))}`, `nicht im Preis: im selben Warenkorb bei ${esc(storeName(s))}${eff != null ? ` kostet das Zubehör ${money(eff)} statt ${money(eff + (x.discount || 0))}` : ""}${big && x.validTo ? `, bis ${esc(x.validTo)}` : ""}`, x.discount ? `− ${eur0(x.discount)}` : "", "set"));
  });
  return `<div class="led">${rows.join("")}</div>`;
}
function spark(p) {
  const W = 88, H = 30, pad = 3, s = p.series, n = s.length, li = n - 1;
  const vals = s.filter(v => v != null);
  if (!vals.length) return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><circle cx="${W / 2}" cy="${H / 2}" r="3" fill="${p.good ? "var(--green)" : "var(--fg)"}"/></svg>`;
  let min = Math.min(...vals, p.best == null ? Infinity : p.best), max = Math.max(...vals); if (max === min) max = min + 1;
  const x = i => pad + (n > 1 ? i / li : 0.5) * (W - 2 * pad), y = v => pad + (1 - (v - min) / (max - min)) * (H - 2 * pad);
  let d = "", open = false;
  s.forEach((v, i) => { if (v == null) { open = false; return; } d += (open ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; open = true; });
  const endV = p.best != null ? Math.min(p.best, s[li] == null ? Infinity : s[li]) : s[li];
  return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">${n > 1 ? `<path d="${d} L${x(li).toFixed(1)} ${H} L${x(0).toFixed(1)} ${H} Z" fill="var(--muted)" opacity=".12"/><path d="${d}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-linejoin="round"/>` : ""}${p.cb ? `<line x1="${x(li).toFixed(1)}" x2="${x(li).toFixed(1)}" y1="${y(s[li]).toFixed(1)}" y2="${y(endV).toFixed(1)}" stroke="var(--amber)" stroke-width="1.5" stroke-dasharray="2 2"/>` : ""}<circle cx="${x(li).toFixed(1)}" cy="${y(endV).toFixed(1)}" r="3" fill="${p.good ? "var(--green)" : "var(--fg)"}"/></svg>`;
}
function trend(p, withSpark) {
  const d = p.delta, c = p.chg30, days = p.hist.length;
  let l1;
  if (days < 2) l1 = p.hist.length && p.hist[0].date === todayISO() ? "erster Scan heute" : "noch kein Verlauf";
  else l1 = d != null && d < 0 ? `<span class="dn">${tri("dn")}${money(-d)}</span> seit gestern` : d != null && d > 0 ? `<span class="up">${tri("up")}${money(d)}</span> seit gestern`
    : c != null && c < 0 ? `<span class="dn">${tri("dn")}${money(-c)}</span> in ${days} Tagen` : c != null && c > 0 ? `<span class="up">${tri("up")}${money(c)}</span> in ${days} Tagen` : `unverändert seit ${days} Tagen`;
  let v = p.best == null ? "kein Angebot" : days < 2 ? "30-Tage-Vergleich ab morgen" : p.good ? `Tiefstpreis seit ${days} Tagen${p.cb ? ", nach Cashback" : ""}`
    : p.aboveLow > 0 ? `${money(p.aboveLow)} über dem ${days}-Tage-Tief von ${money(p.min30)}` : `kaum Bewegung in ${days} Tagen`;
  if (p.target != null && p.best != null) v += p.atTarget ? `, Zielpreis ${eur0(p.target)} erreicht` : `, noch ${money(p.toTarget)} bis zum Zielpreis ${eur0(p.target)}`;
  return `<div class="tr">${withSpark ? `<div class="spark">${spark(p)}</div>` : ""}<div class="tt"><div class="t1">${l1}</div><div class="t2 ${p.good ? "ok" : ""}">${v}</div></div></div>`;
}

/* ===== Expanded area of a list card ===== */
function extOf(p) {
  const stores = p.inR.map(o => `<div class="xr"><div><div class="n">${esc(storeName(o.s))}${dispBadge(o)}</div><div class="s">${esc(o.s.zip || "")} ${esc(cityOf(o.s))} · ${km(o.distanceKm)}, ${o.storeStock > 0 ? `${o.storeStock} im Markt` : "nicht im Markt"}${unknownNote(o)}</div></div><div class="p">${money(o.pickup != null ? o.pickup : o.shipped != null ? o.shipped : o.price)}<small>${o.pickup != null ? "Abholung" : o.shipped != null ? "nur Versand" : "kein Bestand"}</small></div></div>`).join("");
  const shippers = p.offers.filter(o => o.shipped != null).sort((a, b) => a.shipped - b.shipped).slice(0, 3).map(o => `<div class="xr"><div><div class="n">${esc(storeName(o.s))}${dispBadge(o)}</div><div class="s">${o.s.online ? `${o.shipping ? `${money(o.price)} + ${eur(o.shipping)}` : "versandkostenfrei"}${codeLine(o)}` : `${money(o.price)} + ${eur(o.shipping)} Versand, ${km(o.distanceKm)}`}${unknownNote(o)}</div></div><div class="p">${money(o.shipped)}<small>Versand</small></div></div>`).join("");
  const sets = p.sets.map(x => { const eff = setEff(p, x), s = storeOf(x.storeId); return `<div class="xd set">${I.set}<span><b>Set-Deal bei ${esc(storeName(s))}:</b> ${esc(setName(x))} im selben Warenkorb${eff != null ? ` für ${money(eff)} statt ${money(eff + (x.discount || 0))}` : x.discount ? ` mit ${eur0(x.discount)} Rabatt` : ""}${x.validTo ? `, bis ${esc(x.validTo)}` : ""}. Nicht im Preis oben.</span></div>`; }).join("");
  return `${stores ? `<div class="xh">Märkte im Umkreis von ${p.radius} km${p.cb ? ", Preise ohne Cashback" : ""}</div>${stores}` : `<div class="xh">Kein Markt im Umkreis von ${p.radius} km hat das Gerät.</div>`}
    <div class="xh">Versand, günstigste zuerst${p.cb ? ", ohne Cashback" : ""}</div>${shippers || `<div class="xr"><div class="s">niemand verschickt gerade</div></div>`}
    ${sets ? `<div class="xh">Aktionen</div>${sets}` : ""}
    <div class="xact"><button class="btn small" onclick="go('p-${p.webcode}')">Alle Details und Preisverlauf</button></div>`;
}

/* ===== 30-day chart ===== */
function chart(p, H) {
  const W = 420, L = 50, Rr = 10, T = 12, B = 28, hist = p.hist, n = hist.length;
  const a = hist.map(h => h.shipped == null ? null : h.shipped), b = hist.map(h => h.pickup == null ? null : h.pickup);
  const all = [...a, ...b].filter(v => v != null).concat(p.target != null ? [p.target] : []);
  if (!n || !all.length) return `<div class="note" style="border-top:0;padding:4px 0 8px">Noch kein Preisverlauf.</div>`;
  let min = Math.min(...all), max = Math.max(...all); const pad = (max - min || 100) * .12; min -= pad; max += pad;
  const x = i => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - Rr), y = v => T + (1 - (v - min) / (max - min)) * (H - T - B);
  const path = arr => { let d = "", open = false; arr.forEach((v, i) => { if (v == null) { open = false; return; } d += (open ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; open = true; }); return d; };
  const ticks = [0, 1, 2, 3].map(k => { const v = min + pad + (max - min - 2 * pad) * k / 3; return `<text x="${L - 6}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end" font-size="12" fill="var(--muted)">${eur0(v).replace(" €", "")}</text><line x1="${L}" x2="${W - Rr}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)"/>`; }).join("");
  const last = arr => { for (let k = arr.length - 1; k >= 0; k--) if (arr[k] != null) return k; return -1; };
  const la = last(a), lb = last(b);
  const left = fmtDate(hist[0].date), right = hist[n - 1].date === todayISO() ? "heute" : fmtDate(hist[n - 1].date);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Preisverlauf ${n} Tage">
    ${ticks}
    ${p.target != null ? `<line x1="${L}" x2="${W - Rr}" y1="${y(p.target).toFixed(1)}" y2="${y(p.target).toFixed(1)}" stroke="var(--line-2)" stroke-dasharray="4 3"/>` : ""}
    ${la >= 0 && n > 1 ? `<path d="${path(a)} L${x(la).toFixed(1)} ${(H - B).toFixed(1)} L${x(0).toFixed(1)} ${(H - B).toFixed(1)} Z" fill="var(--blue)" opacity=".08"/><path d="${path(a)}" fill="none" stroke="var(--blue)" stroke-width="2" stroke-linejoin="round"/>` : ""}
    ${lb >= 0 && n > 1 ? `<path d="${path(b)}" fill="none" stroke="var(--green)" stroke-width="2" stroke-linejoin="round"/>` : ""}
    ${lb >= 0 ? `<circle cx="${x(lb).toFixed(1)}" cy="${y(b[lb]).toFixed(1)}" r="3.5" fill="var(--green)"/>` : ""}
    ${la >= 0 ? `<circle cx="${x(la).toFixed(1)}" cy="${y(a[la]).toFixed(1)}" r="3.5" fill="var(--blue)"/>` : ""}
    <text x="${L}" y="${H - 6}" font-size="12" fill="var(--muted)">${n > 1 ? left : "heute"}</text>${n > 1 ? `<text x="${W - Rr}" y="${H - 6}" font-size="12" fill="var(--muted)" text-anchor="end">${right}</text>` : ""}
  </svg>`;
}

/* ===== Shell: top bar, tabs, toast, router ===== */
function scanInfo() {
  const st = state.status;
  if (!st || !st.lastRun) return { text: "unbekannt", warn: true, detail: "Kein Status gefunden." };
  const h = (Date.now() - Date.parse(st.lastRun)) / 3600000;
  const prices = (st.steps && st.steps.prices) || {};
  const problems = [];
  if (st.aborted) problems.push(`Lauf abgebrochen: ${st.aborted}`);
  if (prices.ok === false) problems.push(`Preise fehlgeschlagen: ${prices.error || "unbekannt"}`);
  if ((prices.incomplete || []).length) problems.push(`unvollständig: ${prices.incomplete.join(", ")}`);
  if (h > STALE_HOURS) problems.push(`Letzter Lauf ist älter als ${STALE_HOURS} Stunden.`);
  return { text: ageText(st.lastRun), warn: problems.length > 0, detail: problems.join(" ") };
}
function metaBlock() {
  const loc = state.wl ? state.wl.location : null, s = scanInfo();
  return `<button class="meta" onclick="load(true)" aria-label="Daten neu laden" title="Daten neu laden">${loc ? `PLZ ${esc(loc.zip || "?")} · ${loc.maxDistanceKm} km<br>` : ""}Scan <b class="${s.warn ? "warn" : ""}">${esc(s.text)}</b></button>`;
}
function setTop(title, back, extra) {
  const t = document.getElementById("top");
  t.className = "top" + (back ? " detail" : "");
  t.innerHTML = (back ? `<button class="back" aria-label="Zurück" onclick="go('${back}')">${I.back}</button>` : "") + `<h1>${esc(title)}</h1>${extra == null ? metaBlock() : extra}`;
}
function setTabs(active) {
  const t = [["liste", "Beobachten", I.tv], ["einstellungen", "Einstellungen", I.gear]];
  document.getElementById("tabs").innerHTML = t.map(([id, l, svg]) => `<button class="tab" ${active === id ? 'aria-current="page"' : ""} onclick="go('${id}')">${svg}<span>${l}</span></button>`).join("");
}
function toast(m, long) { const t = document.getElementById("toast"); t.textContent = m; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => { t.hidden = true; }, long ? 5000 : 2400); }
function go(r) { if (location.hash.replace("#", "") === r) route(); else location.hash = r; }
function toggle(wc) {
  if (state.open.has(wc)) state.open.delete(wc); else state.open.add(wc);
  const b = document.getElementById("f-" + wc), x = document.getElementById("x-" + wc);
  if (b) { b.setAttribute("aria-expanded", state.open.has(wc)); b.querySelector(".mo").firstChild.textContent = state.open.has(wc) ? "Weniger" : "Mehr"; }
  if (x) x.hidden = !state.open.has(wc);
}
function screen(html) { document.getElementById("screen").innerHTML = html; }
function renderError() {
  setTop("Beobachten", null, ""); setTabs("liste");
  screen(`<div class="card err"><b>Daten konnten nicht geladen werden.</b><div class="s">${esc(state.error)}</div><div class="s">Die App liest die Dateien des Scanners von GitHub Pages. Ohne Netz oder vor dem ersten Lauf gibt es nichts zu zeigen.</div><div><button class="btn" onclick="load()">${I.reload}Noch einmal laden</button></div></div>`);
}

/* ===== Screen 1: Beobachten ===== */
function renderList() {
  setTop("Beobachten", null, metaBlock() + `<button class="plus" aria-label="Produkt hinzufügen" aria-expanded="${state.add}" onclick="toggleAdd()">${I.plus}</button>`);
  setTabs("liste");
  const ps = state.wl.products.map(enrich);
  const cards = ps.map(p => {
    const open = state.open.has(p.webcode);
    const thumb = p.image ? `<img class="thumb" src="${esc(p.image)}" alt="" loading="lazy">` : `<div class="thumb"></div>`;
    if (p.pending) return `<article class="card pcard">
      <div class="head">${thumb}<div class="nm"><div class="name">${esc(p.name)}</div><div class="sub">Webcode ${esc(p.webcode)}</div></div></div>
      <div class="pend"><b>Wird beim nächsten Scan aufgenommen</b>, spätestens in 2 Stunden. Dann erscheinen Name, Bild und Preise.</div></article>`;
    return `<article class="card pcard">
      <button class="head" onclick="go('p-${p.webcode}')" aria-label="${esc(p.name)}, Details">${thumb}<div class="nm"><div class="name">${esc(p.name)}</div><div class="sub">${esc(p.sub)}</div></div></button>
      ${ledger(p, false)}
      <button class="frow" id="f-${p.webcode}" aria-expanded="${open}" aria-controls="x-${p.webcode}" onclick="toggle('${p.webcode}')">${trend(p, true)}<span class="mo">${open ? "Weniger" : "Mehr"}${I.chev}</span></button>
      <div class="ext" id="x-${p.webcode}" ${open ? "" : "hidden"}>${extOf(p)}</div>
    </article>`;
  }).join("");
  const addCard = state.add ? `<div class="card add"><div class="row"><input id="addurl" type="url" inputmode="url" placeholder="Produktlink von expert.de einfügen" aria-label="Produktlink" onkeydown="if(event.key==='Enter')addProduct()"><button class="btn primary" onclick="addProduct()">Beobachten</button></div><div class="s">Der nächste Scan (spätestens in 2 Stunden) holt Name, Bild und die Preise aller Märkte.${state.token ? "" : " Ohne GitHub-Token zeigt die App dir die Datei zum Einfügen."}</div></div>` : "";
  const s = scanInfo();
  screen(`${addCard}${s.warn && s.detail ? `<div class="card cond warn" style="border-top:0">${I.warn}<span>${esc(s.detail)} <a href="#einstellungen">Details</a></span></div>` : ""}
    <div class="sec"><h2>${ps.length === 1 ? "1 Produkt" : `${ps.length} Produkte`}</h2><span class="hint">Umkreis ${state.wl.location.maxDistanceKm} km</span></div>
    ${cards || `<div class="card note">Noch kein Produkt. Tippe oben auf +, füge einen Produktlink von expert.de ein.</div>`}
    <p class="foot">Grün heißt: tiefster Preis seit 30 Tagen${ps.some(p => p.cb) ? ", Cashback schon abgezogen" : ""}. Preise aller 348 expert-Märkte und des Online-Shops, alle 2 Stunden.</p>`);
  if (state.add) { const i = document.getElementById("addurl"); if (i) i.focus(); }
}
function toggleAdd() { state.add = !state.add; renderList(); }
async function addProduct() {
  const input = document.getElementById("addurl"), url = (input.value || "").trim();
  const webcode = parseWebcode(url);
  if (!webcode) { toast("Kein Webcode im Link gefunden (die Zahl vor dem Produktnamen)"); input.focus(); return; }
  if (state.wl.products.some(p => p.webcode === webcode)) { toast("Dieses Produkt ist schon auf der Liste"); return; }
  const entry = { webcode, url: /^https?:\/\//.test(url) ? url.split("?")[0] : undefined, targetPrice: null, alertMode: "every", watchSets: true };
  const ok = await saveWatchlist(wl => { wl.products = wl.products || []; if (!wl.products.some(p => parseWebcode(p.webcode || p.url) === webcode)) wl.products.push(entry); }, `config: watch ${webcode}`);
  if (ok) { state.add = false; toast("Gespeichert. Der nächste Scan holt die Preise."); renderList(); }
}

/* ===== Screen 2: Produkt ===== */
function renderProduct(wc) {
  const cfg = state.wl.products.find(x => x.webcode === wc);
  const p = enrich(cfg);
  setTop(p.name, "liste"); setTabs("liste");
  if (p.pending) {
    screen(`<div class="card"><div class="hero2"><h2>${esc(p.name)}</h2><div class="sub">Webcode ${esc(p.webcode)}</div><div class="links"><a href="${esc(productUrl(p))}" target="_blank" rel="noopener">Bei expert.de öffnen ${I.ext}</a></div></div>
      <div class="cond info">${I.info}<span>Noch kein Scan. Der Scanner läuft alle 2 Stunden auf dem Handy und nimmt das Produkt beim nächsten Lauf auf.</span></div></div>
      ${alertCard(p)}<div class="card"><button class="btn danger" style="margin:12px 14px" onclick="removeProduct('${p.webcode}')">Nicht mehr beobachten</button></div>`);
    return;
  }
  const storeCard = (o, mode) => {
    const s = o.s, isBestPick = mode === "pick" && p.pick && p.pick.storeId === o.storeId, isBestShip = mode === "ship" && p.ship && p.ship.storeId === o.storeId;
    const price = mode === "pick" ? o.pickup : o.shipped; const ok = (isBestPick || isBestShip) && p.good;
    const shown = price != null ? price : o.price;
    return `<div class="card scard"><div class="h"><div class="n">${(isBestPick || isBestShip) ? I.check : ""}${esc(storeName(s))}${dispBadge(o)}</div><div class="p ${ok && !p.cb ? "ok" : ""}">${money(shown)}<small>${p.cb ? "ohne Cashback" : price == null ? "nicht abholbar" : mode === "pick" ? "Abholung" : (o.shipping ? "inkl. Versand" : "versandkostenfrei")}</small></div></div>
      <div class="a"><b>${esc(s.zip || "")} ${esc(cityOf(s))}</b>${s.street ? `, ${esc(s.street)}` : ""}${o.distanceKm != null ? ` · ${km(o.distanceKm)}` : ""}${mode === "ship" && o.shipping ? `<br>${money(o.price)} + ${eur(o.shipping)} Versand${codeLine(o)}` : ""}</div>
      <div class="a">${o.storeStock > 0 ? `${o.storeStock} im Markt` : "nicht im Markt"}${o.onlineStock > 0 ? `, ${o.onlineStock} versandbereit${mode === "pick" && o.shipped != null ? ` (Versand ${money(o.shipped)})` : ""}` : ", kein Versand"}${o.unknown ? "<br>Preis vom letzten Scan, der Markt hat nicht geantwortet" : ""}${p.cb ? `<br><span style="color:var(--amber-ink)">mit ${eur0(p.cb)} Cashback ${money(shown - p.cb)}</span>` : ""}</div>
      <div class="act"><a class="btn small" href="${esc(storeUrl(p, o.storeId))}" target="_blank" rel="noopener">Im Markt öffnen ${I.ext}</a>${s.zip ? `<button class="btn small" onclick="copyZip('${esc(s.zip)}')">${I.copy}PLZ ${esc(s.zip)}</button>` : ""}</div></div>`;
  };
  const on = p.on;
  const onlineCard = on ? `<div class="card scard"><div class="h"><div class="n">${p.ship && p.ship.storeId === ONLINE_ID ? I.check : ""}expert Online-Shop${dispBadge(on)}</div><div class="p ${p.ship && p.ship.storeId === ONLINE_ID && p.good && !p.cb ? "ok" : ""}">${money(on.shipped != null ? on.shipped : on.price)}<small>${p.cb ? "ohne Cashback" : on.shipped == null ? "nicht lieferbar" : on.shipping ? "inkl. Versand" : "versandkostenfrei"}</small></div></div>
      <div class="a">${on.shipping ? `${money(on.price)} + ${eur(on.shipping)} Versand. ` : ""}Zentrallager, ${on.onlineStock > 0 ? `${on.onlineStock} versandbereit` : "nicht versandbereit"}${on.codeDiscount ? `. <b>${esc(codeName(on))}</b> (−${eur0(on.codeDiscount)}) gilt nur hier, schon abgezogen.` : ""}${on.unknown ? "<br>Preis vom letzten Scan." : ""}${p.cb ? `<br><span style="color:var(--amber-ink)">mit ${eur0(p.cb)} Cashback ${money(on.shipped - p.cb)}</span>` : ""}</div>
      <div class="act"><a class="btn small" href="${esc(productUrl(p))}" target="_blank" rel="noopener">Im Online-Shop öffnen ${I.ext}</a></div></div>` : "";
  const farOpen = state.openShip.has(p.webcode), farShown = farOpen ? p.far : p.far.slice(0, 1), farRest = p.far.length - farShown.length;
  const sets = p.sets.map(x => { const eff = setEff(p, x), s = storeOf(x.storeId);
    return `<div class="setrow"><div><div class="n">${esc(setName(x))}</div><div class="d">im Warenkorb mit dem TV bei <b>${esc(storeName(s))}</b>${s.distanceKm != null ? ` (${km(s.distanceKm)})` : ""}${x.unpromoted != null && x.promoted != null ? `<br>Set <span class="was">${money(x.unpromoted)}</span> → ${money(x.promoted)}` : ""}${x.validTo ? `, bis ${esc(x.validTo)}` : ""}</div></div><div class="e">${eff != null ? money(eff) : x.discount ? "−" + eur0(x.discount) : ""}<small>${eff != null ? "Zubehör effektiv" : "Rabatt"}</small></div></div>`; }).join("");
  const nAkt = (p.cb ? 1 : 0) + p.sets.length;
  const setCard = sets ? `<div class="card"><div class="chd">Set-Deal: TV + Zubehör im selben Warenkorb</div>${sets}<div class="note">Zubehör effektiv = Setpreis − TV-Preis desselben Markts. Sets gibt es nur bei manchen Märkten.</div></div>` : "";
  const sc = p.scan || {};
  const scanNote = sc.incomplete ? `<div class="cond warn">${I.warn}<span>Der letzte Scan war unvollständig: mehr als die Hälfte der Märkte hat nicht geantwortet. Die Preise können veraltet sein.</span></div>` : "";
  screen(`
    <div class="card">
      <div class="hero2">${p.image ? `<img class="thumb" src="${esc(p.image)}" alt="">` : ""}<h2>${esc(p.name)}</h2><div class="sub">${esc(p.sub)}</div><div class="links"><a href="${esc(productUrl(p))}" target="_blank" rel="noopener">Bei expert.de öffnen ${I.ext}</a></div></div>
      <div class="sum2">${ledger(p, true)}<div class="trow">${trend(p, false)}</div></div>
      ${p.cb ? `<div class="cond">${I.cash}<span>Du zahlst im Markt ${money(p.gross)} und bekommst <b>${eur0(p.cb)}</b> von ${esc(p.off.brand)} nach der Registrierung bis ${p.off.regBy} zurück.</span></div>` : ""}
      ${scanNote}
    </div>
    <div class="sec"><h2>Aktionen</h2><span class="hint">${nAkt ? `${nAkt} für dieses Gerät` : "keine zurzeit"}</span></div>
    ${setCard}${nAkt ? "" : `<div class="card note">Zurzeit keine Aktion für dieses Gerät. Set-Deals kommen mit dem nächsten Ausbau des Scanners, Cashback danach.</div>`}
    ${alertCard(p)}
    <div class="sec"><h2>Preisverlauf</h2><span class="hint">${p.hist.length} ${p.hist.length === 1 ? "Tag" : "Tage"}, bester Preis je Weg${p.cb ? ", ohne Cashback" : ""}</span></div>
    <div class="card chart">${chart(p, 160)}<div class="leg"><span><i style="background:var(--blue)"></i>Versand</span><span><i style="background:var(--green)"></i>Abholung ≤ ${p.radius} km</span>${p.target != null ? `<span><i style="background:var(--line-2);height:1px"></i>Zielpreis ${eur0(p.target)}</span>` : ""}</div></div>
    <div class="sec"><h2>Abholung im Umkreis</h2><span class="hint">${p.inR.length ? `${p.inR.length} ${p.inR.length === 1 ? "Markt" : "Märkte"}, nach Entfernung` : `${p.radius} km`}</span></div>
    <div class="grp">${p.inR.map(o => storeCard(o, "pick")).join("") || `<div class="card note">Kein Markt im Umkreis von ${p.radius} km hat das Gerät.</div>`}</div>
    <p class="foot left">Auf expert.de wählst du den Markt mit der <b>PLZ</b>; der Link öffnet die Produktseite direkt mit diesem Markt.</p>
    <div class="sec"><h2>Versand</h2><span class="hint">günstigster zuerst</span></div>
    <div class="grp">${onlineCard}${farShown.map(o => storeCard(o, "ship")).join("")}${farRest > 0 ? `<button class="btn small" style="justify-self:start" onclick="state.openShip.add('${p.webcode}');renderProduct('${p.webcode}')">${farRest} weitere Versender anzeigen ${I.chev}</button>` : ""}${!on && !p.far.length ? `<div class="card note">Niemand verschickt das Gerät gerade.</div>` : ""}</div>
    <p class="foot left">Der Online-Shop ist expert zentral: eigene Preise, eigener Bestand, eigene Codes. Märkte verschicken selbst, meist per Spedition.</p>
    <div class="sec"><h2>Scan</h2><span class="hint">${sc.time ? ageText(sc.time) : ""}</span></div>
    <div class="card"><div class="set"><div class="k">Märkte mit Angebot<small>von ${sc.stores || 349} abgefragten</small></div><div class="v"><b>${sc.withOffer != null ? sc.withOffer : "–"}</b></div></div>${sc.unknown ? `<div class="set"><div class="k">Ohne Antwort<small>alter Preis bis zu 24 h behalten</small></div><div class="v"><b>${sc.unknown}</b></div></div>` : ""}
      <div class="set"><div class="k">Nicht mehr beobachten<small>entfernt das Produkt aus der Liste</small></div><div class="v"><button class="btn small danger" onclick="removeProduct('${p.webcode}')">Entfernen</button></div></div></div>`);
}
function alertCard(p) {
  return `<div class="card"><div class="alert"><div class="k">Benachrichtigung<small>wann die App dich anstupst</small></div>
      <select aria-label="Benachrichtigung" onchange="setAlert('${p.webcode}', this.value)"><option value="every" ${p.alertMode === "every" ? "selected" : ""}>bei jeder Senkung</option><option value="low30" ${p.alertMode === "low30" ? "selected" : ""}>nur bei neuem 30-Tage-Tief</option><option value="target" ${p.alertMode === "target" ? "selected" : ""}>nur unter Zielpreis</option></select></div>
    <div class="alert"><div class="k">Zielpreis<small>optional${p.cb ? ", gilt für den Preis nach Cashback" : ""}</small></div><input type="number" inputmode="decimal" step="1" min="0" value="${p.targetPrice == null ? "" : p.targetPrice}" placeholder="keiner" aria-label="Zielpreis in Euro" onchange="setTarget('${p.webcode}', this.value)"></div></div>`;
}
async function setAlert(wc, mode) {
  const ok = await saveWatchlist(wl => { const p = (wl.products || []).find(x => parseWebcode(x.webcode || x.url) === wc); if (p) p.alertMode = mode; }, `config: alert mode ${mode} for ${wc}`);
  if (ok) toast("Gespeichert");
  renderProduct(wc);
}
async function setTarget(wc, value) {
  const t = value === "" ? null : Math.round(+value);
  if (t != null && !(t > 0)) { toast("Zielpreis muss größer als 0 sein"); renderProduct(wc); return; }
  const ok = await saveWatchlist(wl => { const p = (wl.products || []).find(x => parseWebcode(x.webcode || x.url) === wc); if (p) p.targetPrice = t; }, `config: target ${t == null ? "cleared" : t + " €"} for ${wc}`);
  if (ok) toast(t == null ? "Zielpreis entfernt" : `Zielpreis ${eur0(t)} gespeichert`);
  renderProduct(wc);
}
async function removeProduct(wc) {
  const cfg = state.wl.products.find(x => x.webcode === wc);
  if (!confirm(`„${titleOf(cfg, state.products[wc])}“ nicht mehr beobachten? Der Preisverlauf bleibt im Repo, bis der Scanner die Datei aufräumt.`)) return;
  const ok = await saveWatchlist(wl => { wl.products = (wl.products || []).filter(x => parseWebcode(x.webcode || x.url) !== wc); }, `config: stop watching ${wc}`);
  if (ok) { toast("Entfernt"); go("liste"); }
}
function copyZip(z) { const done = () => toast("PLZ " + z + " kopiert"); if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(z).then(done, () => toast("PLZ: " + z)); else toast("PLZ: " + z); }

/* ===== Screen 3: Einstellungen ===== */
function renderSettings() {
  setTop("Einstellungen", null, ""); setTabs("einstellungen");
  const loc = state.wl.location, st = state.status || {}, steps = st.steps || {}, pr = steps.prices || {}, so = steps.stores || {}, s = scanInfo();
  const brands = (state.wl.brands || []).join(", ") || "keine";
  screen(`
    <div class="sec"><h2>Standort</h2><span class="hint">für Entfernung und Abhol-Umkreis</span></div>
    <div class="card"><div class="set"><div class="k">Postleitzahl<small>Koordinaten über api.zippopotam.us</small></div><div class="v"><input id="zip" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="5" value="${esc(loc.zip || "")}" aria-label="Postleitzahl"></div></div>
      <div class="set"><div class="k">Abhol-Umkreis<small>Märkte bis zu dieser Entfernung zählen als Abholung</small></div><div class="v"><input id="radius" type="number" inputmode="numeric" min="1" max="500" step="1" value="${loc.maxDistanceKm}" aria-label="Umkreis in km"> km</div></div>
      <div class="set col"><div class="act"><button class="btn primary" onclick="saveLocation()">Standort speichern</button></div></div></div>
    <div class="sec"><h2>Benachrichtigungen</h2></div>
    <div class="card"><div class="set"><div class="k">Standard für neue Produkte<small>je Produkt umschaltbar: neues 30-Tage-Tief oder Zielpreis</small></div><div class="v"><b>bei jeder Senkung</b></div></div>
      <div class="set"><div class="k">Preisanstiege<small>werden in der App angezeigt</small></div><div class="v">keine Nachricht</div></div>
      <div class="set"><div class="k">Push-Kanal<small>ntfy-App; das Thema liegt nur auf dem Handy in Termux</small></div><div class="v"><b>ntfy</b></div></div>
      <div class="set"><div class="k">Scanfenster</div><div class="v">06–22 Uhr, alle 2 h</div></div>
      <div class="set"><div class="k">Cashback-Marken<small>für spätere Cashback-Meldungen</small></div><div class="v"><b>${esc(brands)}</b></div></div></div>
    <div class="sec"><h2>Scanner</h2><span class="hint">läuft auf dem Handy in Termux</span></div>
    <div class="card"><div class="set"><div class="k">Letzter Lauf<small>${esc(st.berlinTime || "")}${st.event ? ` · ${esc(st.event)}` : ""}${st.network ? ` · ${esc(st.network)}` : ""}</small></div><div class="v ${s.warn ? "warn" : ""}"><b>${esc(s.text)}</b></div></div>
      ${s.detail ? `<div class="cond warn">${I.warn}<span>${esc(s.detail)}</span></div>` : ""}
      ${(st.warnings || []).length ? `<div class="cond info">${I.info}<span>${esc(st.warnings.join(" "))}</span></div>` : ""}
      <div class="set"><div class="k">Preise<small>${pr.lastRun ? ageText(pr.lastRun) : "noch nie"}${pr.products != null ? ` · ${pr.products} Produkte, ${pr.withOffer} Angebote` : ""}${pr.unknown ? `, ${pr.unknown} ohne Antwort` : ""}</small></div><div class="v"><b class="${pr.ok === false ? "" : "ok"}">${pr.ok == null ? "–" : pr.ok ? "ok" : "Fehler"}</b></div></div>
      <div class="set"><div class="k">Märkte<small>${so.lastRun ? ageText(so.lastRun) : "noch nie"}${so.stores != null ? ` · ${so.stores} Märkte, ${so.withinRadius} im Umkreis` : ""}</small></div><div class="v"><b class="${so.ok === false ? "" : "ok"}">${so.ok == null ? "–" : so.ok ? "ok" : "Fehler"}</b></div></div>
      <div class="set"><div class="k">Letzter Lauf<small>Aufrufe und Dauer</small></div><div class="v">${st.calls != null ? `${st.calls} Aufrufe` : ""}${st.durationS != null ? `, ${Math.round(st.durationS)} s` : ""}</div></div>
      <div class="set"><div class="k">Jetzt scannen<small>kein Knopf: ein Lauf außer der Reihe startet in Termux</small></div><div class="v"><a href="${DATA_URL}" target="_blank" rel="noopener">Daten auf GitHub ${I.ext}</a></div></div>
      <div class="set col"><code class="cmd">bash ~/expert-checker/phone/run.sh manual</code></div></div>
    <div class="sec"><h2>GitHub-Zugang</h2><span class="hint">zum Schreiben der Beobachtungsliste</span></div>
    <div class="card"><div class="set"><div class="k">Token<small>fein abgestimmt, nur dieses Repo, Contents: Lesen und Schreiben. Bleibt nur auf diesem Handy.</small></div><div class="v"><b class="${state.token ? "ok" : ""}">${state.token ? "gespeichert" : "keins"}</b></div></div>
      <div class="set col"><input id="token" type="password" autocomplete="off" placeholder="${state.token ? "neues Token einfügen" : "github_pat_…"}" aria-label="GitHub-Token"><div class="act"><button class="btn primary" onclick="saveToken()">Prüfen und speichern</button>${state.token ? `<button class="btn" onclick="testToken()">Prüfen</button><button class="btn danger" onclick="clearToken()">Entfernen</button>` : ""}<a class="btn" href="${TOKEN_URL}" target="_blank" rel="noopener">Token anlegen ${I.ext}</a></div></div>
      <div class="note">Ohne Token zeigt die App jede Änderung als Datei an, die du auf GitHub in <b>config/watchlist.json</b> einfügst.</div></div>
    <div class="sec"><h2>App</h2></div>
    <div class="card"><div class="set"><div class="k">Version</div><div class="v"><b>${APP_VERSION}</b></div></div>
      <div class="set"><div class="k">Daten<small>geladen ${ageText(new Date(state.loadedAt).toISOString())}</small></div><div class="v"><button class="btn small" onclick="load(true)">${I.reload}Neu laden</button></div></div>
      <div class="set"><div class="k">Startbildschirm<small>Chrome-Menü → „Zum Startbildschirm hinzufügen“</small></div><div class="v"><button class="btn small" onclick="hardReload()">App aktualisieren</button></div></div></div>`);
}
async function saveLocation() {
  const zip = (document.getElementById("zip").value || "").trim(), radius = Math.round(+document.getElementById("radius").value);
  if (!/^\d{5}$/.test(zip)) { toast("Postleitzahl: 5 Ziffern"); return; }
  if (!(radius >= 1 && radius <= 500)) { toast("Umkreis: 1 bis 500 km"); return; }
  let lat = state.wl.location.lat, lng = state.wl.location.lng, source = state.wlRaw.location && state.wlRaw.location.source;
  if (zip !== state.wl.location.zip || lat == null || lng == null) {
    toast("Suche Koordinaten …");
    try {
      const r = await fetch(`https://api.zippopotam.us/de/${zip}`);
      if (!r.ok) throw new Error(String(r.status));
      const j = await r.json(), pl = j.places && j.places[0];
      if (!pl) throw new Error("leer");
      lat = Math.round(+pl.latitude * 10000) / 10000; lng = Math.round(+pl.longitude * 10000) / 10000; source = `api.zippopotam.us/de/${zip}`;
      toast(`${zip} ${pl["place name"]}: ${lat}, ${lng}`);
    } catch (e) { toast(`Postleitzahl ${zip} nicht gefunden (${e.message})`, true); return; }
  }
  const ok = await saveWatchlist(wl => { wl.location = { ...(wl.location || {}), zip, lat, lng, maxDistanceKm: radius, source }; }, `config: location ${zip}, ${radius} km`);
  if (ok) { toast("Standort gespeichert. Der nächste Scan rechnet die Entfernungen neu."); renderSettings(); }
}
async function saveToken() {
  const v = (document.getElementById("token").value || "").trim();
  if (!v) { toast("Kein Token eingegeben"); return; }
  const old = state.token; state.token = v;
  const r = await ghTest();
  if (!r.ok) { state.token = old; toast(r.text, true); return; }
  lsSet("gh-token", v); toast(r.text); renderSettings();
}
async function testToken() { const r = await ghTest(); toast(r.text, !r.ok); }
function clearToken() { if (!confirm("GitHub-Token von diesem Handy entfernen?")) return; state.token = ""; lsSet("gh-token", null); toast("Token entfernt"); renderSettings(); }
async function ghTest() {
  try {
    const r = await gh(`contents/config/watchlist.json?ref=${BRANCH}`);
    if (r.status === 401) return { ok: false, text: "Token ungültig (401 Unauthorized)" };
    if (r.status === 403 || r.status === 404) return { ok: false, text: `Token hat keinen Zugriff auf ${REPO} (${r.status})` };
    if (!r.ok) return { ok: false, text: `GitHub antwortet ${r.status}` };
    return { ok: true, text: "Token gültig, Lesen klappt. Schreiben prüft die erste Änderung." };
  } catch (e) { return { ok: false, text: `Keine Verbindung zu GitHub (${e.message})` }; }
}
function hardReload() {
  if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) navigator.serviceWorker.getRegistrations().then(rs => Promise.all(rs.map(r => r.update()))).finally(() => location.reload());
  else location.reload();
}

/* ===== Writing config/watchlist.json ===== */
function gh(path, opts) {
  opts = opts || {};
  return fetch(`https://api.github.com/repos/${REPO}/${path}`, { ...opts, headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${state.token}`, "X-GitHub-Api-Version": "2022-11-28", ...(opts.headers || {}) } });
}
/* mutate(wl) edits the raw watchlist object in place. With a token the edit is applied to the current file
   on GitHub (fresh sha, retried once on 409 (Conflict)); without one the app shows the resulting file to paste. */
async function saveWatchlist(mutate, message) {
  if (!state.token) { showJson(mutate); return false; }
  toast("Speichere …");
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const r = await gh(`contents/config/watchlist.json?ref=${BRANCH}`);
      if (r.status === 401 || r.status === 403) throw new Error(`Token ungültig oder ohne Zugriff (${r.status})`);
      if (!r.ok) throw new Error(`Lesen fehlgeschlagen (${r.status})`);
      const file = await r.json();
      const remote = JSON.parse(b64decode(file.content));
      mutate(remote);
      const body = JSON.stringify(remote, null, 2) + "\n";
      const put = await gh("contents/config/watchlist.json", { method: "PUT", body: JSON.stringify({ message: `${message}\n\nWritten by the PWA.`, content: b64encode(body), sha: file.sha, branch: BRANCH }) });
      if (put.status === 409 && attempt === 0) continue;
      if (put.status === 401 || put.status === 403) throw new Error(`Token darf nicht schreiben (${put.status}); Contents: Lesen und Schreiben nötig`);
      if (!put.ok) throw new Error(`Schreiben fehlgeschlagen (${put.status})`);
      state.wlRaw = remote; state.wl = normalize(remote);
      lsSet("wl-pending", JSON.stringify({ t: Date.now(), wl: remote }));
      return true;
    }
    throw new Error("Datei hat sich zweimal geändert, bitte noch einmal");
  } catch (e) { toast(e.message, true); return false; }
}
function showJson(mutate) {
  const wl = JSON.parse(JSON.stringify(state.wlRaw || { products: [] }));
  mutate(wl);
  const body = JSON.stringify(wl, null, 2) + "\n";
  const old = document.getElementById("modal"); if (old) old.remove();
  const m = document.createElement("div"); m.className = "modal"; m.id = "modal";
  m.innerHTML = `<div class="card" role="dialog" aria-labelledby="mh"><h3 id="mh">Ohne GitHub-Token: Datei selbst einfügen</h3><p>Kopiere den Inhalt und ersetze damit <b>config/watchlist.json</b> auf GitHub. Der nächste Scan übernimmt die Änderung. Mit einem Token unter Einstellungen schreibt die App selbst.</p><textarea readonly aria-label="watchlist.json">${esc(body)}</textarea><div class="act"><button class="btn" onclick="document.getElementById('modal').remove()">Schließen</button><button class="btn" onclick="copyText(this.parentNode.parentNode.querySelector('textarea').value)">${I.copy}Kopieren</button><a class="btn primary" href="${EDIT_URL}" target="_blank" rel="noopener">Auf GitHub öffnen ${I.ext}</a></div></div>`;
  m.addEventListener("click", e => { if (e.target === m) m.remove(); });
  document.body.appendChild(m);
}
function copyText(t) { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(() => toast("Kopiert"), () => toast("Kopieren nicht möglich, bitte markieren")); else toast("Kopieren nicht möglich, bitte markieren"); }

/* ===== Router and startup ===== */
function route() {
  const h = location.hash.replace("#", "") || "liste";
  const modal = document.getElementById("modal"); if (modal) modal.remove();
  window.scrollTo(0, 0);
  if (!state.loaded) return state.error ? renderError() : null;
  if (h === "liste") return renderList();
  if (h === "einstellungen") return renderSettings();
  if (h.startsWith("p-")) return state.wl.products.some(p => p.webcode === h.slice(2)) ? renderProduct(h.slice(2)) : renderList();
  renderList();
}
window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && state.loaded && Date.now() - state.loadedAt > 5 * 60000) load(); });
if ("serviceWorker" in navigator && location.protocol === "https:") {
  let hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (hadController) location.reload(); hadController = true; });
  navigator.serviceWorker.register("sw.js").catch(() => { /* offline shell is optional */ });
}
load();
