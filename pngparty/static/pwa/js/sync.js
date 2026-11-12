/*
 * Field agent data layer: auth, photo compression, outbox queue, sync engine.
 * No UI code here. The UI listens for the `outbox-changed` and `sync-state`
 * events on window.
 */
(function () {
  'use strict';

  const { db, getMeta, setMeta, delMeta } = window.AgentDB;

  const CONFIG = {
    batchSize: 5,
    requestTimeoutMs: 60000,     // generous: rural 3G/EDGE
    autoSyncIntervalMs: 90000,
    photo: { size: 300, targetBytes: 35 * 1024, startQuality: 0.75, minQuality: 0.4 },
    keepSyncedDays: 30,
    maxBackoffMs: 30 * 60 * 1000,
  };

  const API = {
    token: '/api/auth/token/',
    refresh: '/api/auth/token/refresh/',
    lookup: '/api/geo/electorates/',
    sync: '/api/members/sync/',
    history: '/api/members/sync/history/',
  };

  const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------

  function uuid4() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }

  async function fetchWithTimeout(url, opts = {}, ms = CONFIG.requestTimeoutMs) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await fetch(url, { ...opts, signal: ctrl.signal, cache: 'no-store' });
    } finally {
      clearTimeout(t);
    }
  }

  // Ask the browser not to evict our IndexedDB when the phone runs low on
  // space; unsynced registrations live only here.
  async function requestPersistentStorage() {
    try {
      if (navigator.storage && navigator.storage.persist) {
        return await navigator.storage.persist();
      }
    } catch (_) { /* not fatal */ }
    return false;
  }

  // -------------------------------------------------------------------------
  // Auth (SimpleJWT). Login needs signal once; the 30-day refresh token then
  // lets the agent sync for a month without re-entering a password.
  // -------------------------------------------------------------------------

  async function login(username, password) {
    const res = await fetchWithTimeout(API.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (res.status === 401) throw new Error('Wrong username or password.');
    if (!res.ok) throw new Error(`Login failed (${res.status}).`);
    const { access, refresh } = await res.json();
    await setMeta('tokens', { access, refresh, refreshed_at: Date.now() });
    await setMeta('username', username);
    await setMeta('needs_login', false);
    await refreshLookup();
    return true;
  }

  async function logout() {
    // Unsynced records are kept: they belong to the party, not the session.
    await delMeta('tokens');
    await setMeta('needs_login', true);
  }

  async function refreshAccessToken() {
    const tokens = await getMeta('tokens');
    if (!tokens || !tokens.refresh) return null;
    const res = await fetchWithTimeout(API.refresh, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: tokens.refresh }),
    }, 30000);
    if (res.status === 401) {
      await setMeta('needs_login', true);   // refresh expired after 30 days
      return null;
    }
    if (!res.ok) throw new Error(`Token refresh failed (${res.status})`);
    const data = await res.json();
    const updated = { ...tokens, access: data.access, refreshed_at: Date.now() };
    if (data.refresh) updated.refresh = data.refresh;  // if rotation is ever enabled
    await setMeta('tokens', updated);
    return updated.access;
  }

  class AuthRequired extends Error {}

  async function authFetch(url, opts = {}) {
    let tokens = await getMeta('tokens');
    if (!tokens) throw new AuthRequired('Please log in.');
    const call = (access) => fetchWithTimeout(url, {
      ...opts,
      headers: { ...(opts.headers || {}), Authorization: `Bearer ${access}` },
    });
    let res = await call(tokens.access);
    if (res.status === 401) {
      const access = await refreshAccessToken();
      if (!access) throw new AuthRequired('Session expired. Log in again to sync.');
      res = await call(access);
    }
    return res;
  }

  async function refreshLookup() {
    const res = await authFetch(API.lookup);
    if (!res.ok) throw new Error('Could not download electorate list.');
    const data = await res.json();
    await db.lookup.put({ key: 'geo', value: data, fetched_at: Date.now() });
    return data;
  }

  async function getLookup() {
    const row = await db.lookup.get('geo');
    return row ? row.value : null;
  }

  // -------------------------------------------------------------------------
  // Photo compression: centre-crop square -> 300x300 JPEG, ~30 KB.
  // Pure <canvas>; no third-party library to vendor or cache.
  // -------------------------------------------------------------------------

  async function loadBitmap(file) {
    if ('createImageBitmap' in window) {
      try {
        // Applies EXIF orientation so portrait phone shots aren't sideways
        return await createImageBitmap(file, { imageOrientation: 'from-image' });
      } catch (_) { /* fall through (older Safari) */ }
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read photo.')); };
      img.src = url;
    });
  }

  function canvasToBlob(canvas, type, quality) {
    return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
  }

  async function compressPhoto(file) {
    const { size, targetBytes, startQuality, minQuality } = CONFIG.photo;
    const src = await loadBitmap(file);
    const w = src.width, h = src.height;
    const side = Math.min(w, h);
    // Bias crop slightly upward: faces sit in the upper part of portrait shots
    const sx = (w - side) / 2;
    const sy = h > w ? Math.max(0, (h - side) * 0.35) : 0;

    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(src, sx, sy, side, side, 0, 0, size, size);
    if (src.close) src.close();

    let q = startQuality;
    let blob = await canvasToBlob(canvas, 'image/jpeg', q);
    while (blob && blob.size > targetBytes && q > minQuality) {
      q = Math.max(minQuality, q - 0.1);
      blob = await canvasToBlob(canvas, 'image/jpeg', q);
    }
    if (!blob) throw new Error('Photo compression failed.');
    return blob;
  }

  // -------------------------------------------------------------------------
  // Outbox
  // -------------------------------------------------------------------------

  /**
   * Save a registration locally. Works with zero signal.
   * `existingId` re-queues a rejected record after the agent fixes it
   * (same UUID, so the server still sees one person).
   */
  async function queueMember(fields, photoBlob, existingId = null) {
    const id = existingId || uuid4();
    const prev = existingId ? await db.outbox.get(existingId) : null;
    const data = {
      ...fields,
      id,
      client_created_at: prev ? prev.data.client_created_at : new Date().toISOString(),
    };
    await db.outbox.put({
      id,
      data,
      photo: photoBlob || (prev && prev.photo) || null,
      status: 'pending',
      attempts: 0,
      next_attempt_at: 0,
      errors: null,
      created_at: prev ? prev.created_at : Date.now(),
      agent: await getMeta('username'),
    });
    emit('outbox-changed');
    // Opportunistic: if there happens to be signal right now, send it.
    if (navigator.onLine) setTimeout(() => syncNow({ reason: 'queued' }), 500);
    return id;
  }

  async function counts() {
    const [pending, failed, rejected, synced] = await Promise.all([
      db.outbox.where('status').anyOf('pending', 'syncing').count(),
      db.outbox.where('status').equals('failed').count(),
      db.outbox.where('status').equals('rejected').count(),
      db.outbox.where('status').equals('synced').count(),
    ]);
    return { waiting: pending + failed, rejected, synced };
  }

  async function listOutbox() {
    return db.outbox.orderBy('created_at').reverse().toArray();
  }

  // -------------------------------------------------------------------------
  // Sync engine
  // -------------------------------------------------------------------------

  let syncing = false;

  function backoffMs(attempts) {
    // 30 s, 1 min, 2 min, 4 min ... capped at 30 min, with jitter
    const base = Math.min(CONFIG.maxBackoffMs, 30000 * 2 ** Math.max(0, attempts - 1));
    return base * (0.75 + Math.random() * 0.5);
  }

  async function nextBatch(force) {
    const now = Date.now();
    const rows = await db.outbox
      .where('status').anyOf('pending', 'failed')
      .sortBy('created_at');
    return rows
      .filter((r) => force || !r.next_attempt_at || r.next_attempt_at <= now)
      .slice(0, CONFIG.batchSize);
  }

  function buildForm(batch) {
    const form = new FormData();
    form.append('records', JSON.stringify(batch.map((r) => r.data)));
    for (const r of batch) {
      if (r.photo) form.append(`photo_${r.id}`, r.photo, `${r.id}.jpg`);
    }
    return form;
  }

  // Strip personal data from the phone once the server has the record.
  function syncedStub(row, result) {
    return {
      id: row.id,
      data: {
        id: row.id,
        full_name: row.data.full_name,
        electorate: row.data.electorate,
        client_created_at: row.data.client_created_at,
      },
      photo: null,
      status: 'synced',
      server_status: result.status,
      flag_message: result.message || null,
      synced_at: Date.now(),
      created_at: row.created_at,
      attempts: row.attempts,
      next_attempt_at: 0,
      agent: row.agent,
    };
  }

  async function applyResults(batch, results) {
    const byId = new Map(results.map((r) => [String(r.id), r]));
    await db.transaction('rw', db.outbox, async () => {
      for (const row of batch) {
        const r = byId.get(row.id);
        if (!r) {
          // Server didn't mention it (shouldn't happen): retry later
          await db.outbox.update(row.id, { status: 'failed', next_attempt_at: Date.now() + 60000 });
        } else if (r.status === 'rejected') {
          await db.outbox.update(row.id, { status: 'rejected', errors: r.errors || {} });
        } else {
          // created | already_synced | flagged -> server owns it now
          await db.outbox.put(syncedStub(row, r));
        }
      }
    });
  }

  async function markBatchFailed(batch, message) {
    await db.transaction('rw', db.outbox, async () => {
      for (const row of batch) {
        const attempts = (row.attempts || 0) + 1;
        await db.outbox.update(row.id, {
          status: 'failed',
          attempts,
          last_error: message,
          next_attempt_at: Date.now() + backoffMs(attempts),
        });
      }
    });
  }

  /**
   * Upload the outbox in small batches. Stops at the first network failure
   * (no point hammering a dead link); everything already sent stays sent.
   * `force` ignores backoff (manual "Sync Now" button).
   */
  async function syncNow({ force = false, reason = 'auto' } = {}) {
    if (syncing) return { skipped: 'already-running' };
    if (!(await getMeta('tokens'))) return { needsLogin: true };
    syncing = true;
    emit('sync-state', { running: true, reason });

    const summary = { sent: 0, rejected: 0, error: null, needsLogin: false };
    try {
      for (;;) {
        const batch = await nextBatch(force);
        if (!batch.length) break;

        await db.transaction('rw', db.outbox, () =>
          Promise.all(batch.map((r) => db.outbox.update(r.id, { status: 'syncing' }))));
        emit('outbox-changed');

        let res;
        try {
          res = await authFetch(API.sync, { method: 'POST', body: buildForm(batch) });
        } catch (err) {
          if (err instanceof AuthRequired) {
            await Promise.all(batch.map((r) => db.outbox.update(r.id, { status: 'pending' })));
            summary.needsLogin = true;
            summary.error = err.message;
          } else {
            await markBatchFailed(batch, err.name === 'AbortError' ? 'Timed out' : 'No connection');
            summary.error = 'Connection lost. Will retry automatically.';
          }
          break;
        }

        if (res.status === 200) {
          const body = await res.json();
          await applyResults(batch, body.results || []);
          summary.sent += (body.summary && (body.summary.created + body.summary.already_synced + body.summary.flagged)) || 0;
          summary.rejected += (body.summary && body.summary.rejected) || 0;
          await setMeta('last_sync_at', Date.now());
        } else if (res.status === 400 || res.status === 413) {
          // Whole batch refused (e.g. too large). Retry one-by-one next time.
          CONFIG.batchSize = 1;
          await markBatchFailed(batch, `Server refused batch (${res.status})`);
          summary.error = 'Server refused a batch; retrying smaller.';
          break;
        } else {
          await markBatchFailed(batch, `Server error ${res.status}`);
          summary.error = `Server error ${res.status}. Will retry.`;
          break;
        }
        emit('outbox-changed');
      }
    } finally {
      syncing = false;
      emit('outbox-changed');
      emit('sync-state', { running: false, summary });
    }
    return summary;
  }

  async function fetchHistory() {
    const res = await authFetch(API.history);
    if (!res.ok) throw new Error('Could not load history.');
    return res.json();
  }

  async function purgeOldSynced() {
    const cutoff = Date.now() - CONFIG.keepSyncedDays * 86400000;
    const old = await db.outbox.where('status').equals('synced')
      .filter((r) => (r.synced_at || 0) < cutoff).primaryKeys();
    if (old.length) await db.outbox.bulkDelete(old);
  }

  // A sync interrupted by closing the app leaves rows stuck in `syncing`.
  async function recoverStuck() {
    await db.outbox.where('status').equals('syncing').modify({ status: 'pending' });
  }

  // -------------------------------------------------------------------------
  // Triggers
  // -------------------------------------------------------------------------

  async function start() {
    await recoverStuck();
    await purgeOldSynced();
    requestPersistentStorage();

    window.addEventListener('online', () => syncNow({ reason: 'online' }));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && navigator.onLine) syncNow({ reason: 'resume' });
    });
    // navigator.onLine is unreliable (true on captive Wi-Fi / no-data SIMs),
    // so keep trying on an interval; backoff limits the cost.
    setInterval(() => { if (navigator.onLine) syncNow({ reason: 'interval' }); }, CONFIG.autoSyncIntervalMs);
    if (navigator.onLine) syncNow({ reason: 'startup' });
  }

  window.AgentSync = {
    start, login, logout, syncNow, queueMember, compressPhoto,
    counts, listOutbox, getLookup, refreshLookup, fetchHistory,
    isSyncing: () => syncing,
    getMeta,
  };
})();
