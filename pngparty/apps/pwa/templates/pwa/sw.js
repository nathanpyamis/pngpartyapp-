{% load static %}/* PNG Party field agent service worker, shell v{{ version }} */
'use strict';

const SHELL_CACHE = 'agent-shell-v{{ version }}';
const DATA_CACHE = 'agent-data-v1';

// Hashed static URLs (WhiteNoise manifest): a new deploy means new URLs.
// CRITICAL files must all cache or install fails; OPTIONAL ones may miss.
const CRITICAL = [
  '/agent/',
  '{% static "pwa/vendor/dexie.min.js" %}',
  '{% static "pwa/js/db.js" %}',
  '{% static "pwa/js/sync.js" %}',
  '{% static "pwa/js/app.js" %}',
];
const OPTIONAL = [
  '/agent/manifest.webmanifest',
  '{% static "pwa/icons/icon-192.png" %}',
  '{% static "pwa/icons/icon-512.png" %}',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const c = await caches.open(SHELL_CACHE);
    await c.addAll(CRITICAL.map((u) => new Request(u, { cache: 'reload' })));
    await Promise.allSettled(OPTIONAL.map((u) => c.add(new Request(u, { cache: 'reload' }))));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith('agent-shell-') && k !== SHELL_CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Uploads, auth and history must always hit the network; the outbox in
  // IndexedDB (not the SW) is what makes registration work offline.
  if (req.method !== 'GET' || url.pathname.startsWith('/api/members/') || url.pathname.startsWith('/api/auth/')) {
    return;
  }

  // Electorate lookup: network-first, fall back to last good copy.
  if (url.pathname === '/api/geo/electorates/') {
    event.respondWith(networkFirst(req, DATA_CACHE));
    return;
  }

  // App navigation: always serve the cached shell instantly.
  if (req.mode === 'navigate' && url.pathname.startsWith('/agent')) {
    event.respondWith(
      caches.match('/agent/', { ignoreSearch: true }).then((hit) => hit || fetch(req))
    );
    return;
  }

  // Static shell files: cache-first.
  if (url.pathname.startsWith('/static/pwa/')) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (hit) return hit;
    throw err;
  }
}
