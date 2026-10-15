/* Võrguta töö: rakenduse kest ja andmed vahemällu.
   Kest: kiire vastus vahemälust, taustal uuendus. Andmed: vahemälust; app.js kontrollib version.json kaudu uut versiooni. */
const SHELL = 'teatmik-shell-v6';
const DATA = 'teatmik-data-v1';
const ASSETS = ['./', 'index.html', 'app.js', 'style.css', 'fonts.css', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png',
  'fonts/ibm-plex-mono-latin-400-normal.woff2',
  'fonts/ibm-plex-mono-latin-500-normal.woff2',
  'fonts/ibm-plex-mono-latin-ext-400-normal.woff2',
  'fonts/ibm-plex-mono-latin-ext-500-normal.woff2',
  'fonts/ibm-plex-sans-condensed-latin-600-normal.woff2',
  'fonts/ibm-plex-sans-condensed-latin-ext-600-normal.woff2',
  'fonts/ibm-plex-sans-latin-400-normal.woff2',
  'fonts/ibm-plex-sans-latin-500-normal.woff2',
  'fonts/ibm-plex-sans-latin-600-normal.woff2',
  'fonts/ibm-plex-sans-latin-ext-400-normal.woff2',
  'fonts/ibm-plex-sans-latin-ext-500-normal.woff2',
  'fonts/ibm-plex-sans-latin-ext-600-normal.woff2'];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    await c.addAll(ASSETS);
    const d = await caches.open(DATA);
    try { const r = await fetch('data/data.json', { cache: 'no-store' }); if (r.ok) await d.put('data/data.json', r); } catch (err) { /* hiljem */ }
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keep = [SHELL, DATA];
    for (const k of await caches.keys()) if (!keep.includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin !== location.origin) return;

  if (url.pathname.endsWith('/data/version.json')) {
    e.respondWith(fetch(req).catch(() => new Response('{}', { headers: { 'Content-Type': 'application/json' } })));
    return;
  }
  if (url.pathname.endsWith('/data/data.json')) {
    e.respondWith((async () => {
      const c = await caches.open(DATA);
      if (url.search) {
        // app.js küsib uut versiooni: võrgust ja vahemällu
        const r = await fetch(req, { cache: 'no-store' });
        if (r.ok) await c.put('data/data.json', r.clone());
        return r;
      }
      const hit = await c.match('data/data.json');
      if (hit) return hit;
      const r = await fetch(req);
      if (r.ok) await c.put('data/data.json', r.clone());
      return r;
    })());
    return;
  }
  e.respondWith(staleWhileRevalidate(SHELL, req));
});

async function staleWhileRevalidate(name, req) {
  const c = await caches.open(name);
  const hit = await c.match(req, { ignoreSearch: true });
  const net = fetch(req).then((r) => { if (r.ok) c.put(req, r.clone()); return r; }).catch(() => null);
  if (hit) { net.catch(() => {}); return hit; }
  const r = await net;
  if (r) return r;
  if (req.mode === 'navigate') return (await c.match('index.html')) || Response.error();
  return Response.error();
}
