/* IndexedDB schema (Dexie). Loaded after /static/pwa/vendor/dexie.min.js */
/* global Dexie */
(function () {
  'use strict';

  const db = new Dexie('pngparty_agent');

  db.version(1).stores({
    // status: pending | syncing | failed | rejected | synced
    outbox: 'id, status, created_at, next_attempt_at',
    meta: 'key',     // tokens, user profile, last sync time
    lookup: 'key',   // provinces + electorates for offline dropdowns
  });

  async function getMeta(key, fallback = null) {
    const row = await db.meta.get(key);
    return row ? row.value : fallback;
  }

  async function setMeta(key, value) {
    await db.meta.put({ key, value });
  }

  async function delMeta(key) {
    await db.meta.delete(key);
  }

  window.AgentDB = { db, getMeta, setMeta, delMeta };
})();
