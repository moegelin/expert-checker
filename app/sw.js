/* expert-checker service worker: the app shell is cached (offline start), data files are network-first
   with the last copy as the fallback, product images from cdn.expert.de are cached on first load. */
const VERSION = "2026-11-24.3";
const SHELL = `shell-${VERSION}`, DATA = "data-v1", IMG = "img-v1";
const SHELL_FILES = ["./", "./index.html", "./app.css", "./app.js", "./manifest.webmanifest", "./icon.svg", "./icon-192.png", "./icon-512.png", "./icon-maskable-512.png"];
const SCOPE = new URL("./", self.location.href).pathname;

self.addEventListener("install", e => {
  // cache: "reload" bypasses the HTTP cache (Pages serves max-age=600), so a new worker always gets new files
  e.waitUntil(caches.open(SHELL).then(c => Promise.all(SHELL_FILES.map(u => fetch(u, { cache: "reload" }).then(r => { if (!r.ok) throw new Error(u + " " + r.status); return c.put(u, r); })))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("shell-") && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin && url.pathname.startsWith(SCOPE)) {
    // app shell: cache first, then network
    const key = req.mode === "navigate" ? "./index.html" : url.pathname;
    e.respondWith(caches.open(SHELL).then(c => c.match(key).then(hit => hit || fetch(req).then(res => { if (res.ok) c.put(key, res.clone()); return res; }))));
    return;
  }
  if (url.origin === self.location.origin && (url.pathname.includes("/data/") || url.pathname.includes("/config/"))) {
    // scanner output: network first, cached copy when offline
    const key = url.origin + url.pathname;
    e.respondWith(fetch(req).then(res => { if (res.ok) { const copy = res.clone(); caches.open(DATA).then(c => c.put(key, copy)); } return res; })
      .catch(() => caches.open(DATA).then(c => c.match(key)).then(hit => hit || new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }))));
    return;
  }
  if (url.hostname === "cdn.expert.de") {
    e.respondWith(caches.open(IMG).then(c => c.match(req).then(hit => hit || fetch(req).then(res => { if (res.ok || res.type === "opaque") c.put(req, res.clone()); return res; }))));
  }
});
