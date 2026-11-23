/* Panel Tracker web (PWA): aplikasi tetap terbuka saat tidak ada sinyal.
   - Data (panel, punch, foto) sudah disimpan aplikasi di IndexedDB; service worker ini hanya menyimpan "kulit" aplikasi.
   - Halaman: network-first (versi terbaru bila online), cadangan dari cache bila offline.
   - File build ber-hash (assets/*): cache-first.
   - Request ke Supabase (domain lain) TIDAK pernah disentuh / di-cache. */
const CACHE = "pt-web-v1.2.2";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("pt-web-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          // Supabase dll.: langsung ke jaringan

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy));
          return res;
        })
        .catch(() => caches.match("./index.html")),
    );
    return;
  }

  if (url.pathname.includes("/assets/")) {                  // nama file ber-hash → tidak pernah berubah
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      })),
    );
    return;
  }

  e.respondWith(                                              // lain-lain: cache dulu, perbarui di belakang
    caches.match(req).then((hit) => {
      const net = fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => hit);
      return hit || net;
    }),
  );
});
