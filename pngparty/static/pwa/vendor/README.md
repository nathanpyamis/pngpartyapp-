# Vendored libraries

Served from our own domain (no CDN) so the service worker can precache them
and the app works with zero signal.

Required:

- `dexie.min.js`: Dexie 4.x
  `curl -L -o dexie.min.js https://unpkg.com/dexie@4/dist/dexie.min.js`

Icons expected in `../icons/`: `icon-192.png`, `icon-512.png` (party logo).
