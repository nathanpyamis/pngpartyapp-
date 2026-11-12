/* Field agent UI. Plain DOM: no framework to download or cache. */
(function () {
  'use strict';

  const S = window.AgentSync;
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  const state = { lookup: null, photoBlob: null, editingId: null, previewUrl: null };

  // ---------------------------------------------------------------- views --

  function show(view) {
    for (const v of ['login', 'register', 'outbox', 'history']) {
      $(`#view-${v}`).hidden = v !== view;
    }
    document.querySelectorAll('nav [data-view]').forEach((b) =>
      b.classList.toggle('active', b.dataset.view === view));
    if (view === 'outbox') renderOutbox();
    if (view === 'history') renderHistory();
  }

  function toast(msg, kind = 'info') {
    const t = $('#toast');
    t.textContent = msg;
    t.className = `toast ${kind}`;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, 4000);
  }

  // ------------------------------------------------------------ status bar --

  async function renderStatus() {
    const c = await S.counts();
    const online = navigator.onLine;
    const last = await S.getMeta('last_sync_at');
    const needsLogin = await S.getMeta('needs_login', false);
    $('#net').textContent = online ? 'Online' : 'Offline';
    $('#net').className = `pill ${online ? 'on' : 'off'}`;
    $('#waiting').textContent = c.waiting;
    $('#rejected-badge').textContent = c.rejected;
    $('#rejected-badge').hidden = !c.rejected;
    $('#last-sync').textContent = last ? `Last sync ${new Date(last).toLocaleString()}` : 'Never synced';
    $('#login-banner').hidden = !needsLogin;
    $('#sync-btn').disabled = S.isSyncing() || c.waiting === 0;
    $('#sync-btn').textContent = S.isSyncing() ? 'Syncing…' : `Sync now (${c.waiting})`;
  }

  // ---------------------------------------------------------------- login --

  async function onLogin(e) {
    e.preventDefault();
    const btn = $('#login-btn');
    btn.disabled = true;
    $('#login-error').textContent = '';
    try {
      await S.login($('#username').value.trim(), $('#password').value);
      $('#password').value = '';
      state.lookup = await S.getLookup();
      fillElectorates();
      toast('Logged in. You can now register members offline.', 'ok');
      show('register');
      S.syncNow({ reason: 'login' });
    } catch (err) {
      $('#login-error').textContent = navigator.onLine
        ? err.message
        : 'You need signal to log in the first time.';
    } finally {
      btn.disabled = false;
      renderStatus();
    }
  }

  // ---------------------------------------------------- registration form --

  function fillElectorates() {
    const sel = $('#electorate');
    const L = state.lookup;
    if (!L) return;
    const provinces = new Map(L.provinces.map((p) => [p.id, p]));
    let list = L.electorates;
    if (L.role === 'AGENT') list = list.filter((e) => e.id === L.assigned_electorate_id);
    else if (L.role === 'COORDINATOR') list = list.filter((e) => e.province_id === L.assigned_province_id);

    const groups = new Map();
    for (const e of list) {
      const p = provinces.get(e.province_id);
      const key = p ? p.name : 'Other';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    }
    sel.innerHTML = '<option value="">Select electorate…</option>' +
      [...groups.entries()].sort().map(([prov, items]) =>
        `<optgroup label="${esc(prov)}">` +
        items.map((e) => `<option value="${e.id}">${esc(e.name)}${e.electorate_type === 'PROVINCIAL' ? ' (Provincial)' : ''}</option>`).join('') +
        '</optgroup>').join('');
    if (L.assigned_electorate_id) sel.value = String(L.assigned_electorate_id);
    sel.disabled = L.role === 'AGENT';
  }

  async function onPhoto(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    $('#photo-status').textContent = 'Compressing…';
    try {
      state.photoBlob = await S.compressPhoto(file);
      setPreview(state.photoBlob);
      $('#photo-status').textContent = `Photo ready (${Math.round(state.photoBlob.size / 1024)} KB)`;
    } catch (err) {
      state.photoBlob = null;
      $('#photo-status').textContent = err.message;
    }
    e.target.value = '';  // allow retaking the same shot
  }

  function setPreview(blob) {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = blob ? URL.createObjectURL(blob) : null;
    $('#photo-preview').src = state.previewUrl || '';
    $('#photo-preview').hidden = !blob;
  }

  function readForm() {
    const f = $('#member-form');
    const v = (name) => (f.elements[name].value || '').trim();
    return {
      full_name: v('full_name'),
      gender: (f.querySelector('input[name="gender"]:checked') || {}).value || '',
      date_of_birth: v('date_of_birth') || null,
      nid_number: v('nid_number'),
      phone_number: v('phone_number'),
      electorate: Number($('#electorate').value) || null,
      llg_ward: v('llg_ward'),
      village_or_street: v('village_or_street'),
    };
  }

  function resetForm() {
    const f = $('#member-form');
    const keepElectorate = $('#electorate').value;
    const keepWard = f.elements.llg_ward.value;
    f.reset();
    $('#electorate').value = keepElectorate;   // agents register many people in one place
    f.elements.llg_ward.value = keepWard;
    state.photoBlob = null;
    state.editingId = null;
    setPreview(null);
    $('#photo-status').textContent = 'No photo yet';
    $('#form-title').textContent = 'Register member';
    $('#form-errors').innerHTML = '';
  }

  async function onSave(e) {
    e.preventDefault();
    const data = readForm();
    const problems = [];
    if (data.full_name.length < 3) problems.push('Enter the full name.');
    if (!data.gender) problems.push('Select gender.');
    if (!data.electorate) problems.push('Select electorate.');
    if (!state.photoBlob && !state.editingId) problems.push('Take a photo.');
    if (!data.nid_number && !data.phone_number) problems.push('Enter an NID or phone number.');
    if (problems.length) {
      $('#form-errors').innerHTML = problems.map((p) => `<li>${esc(p)}</li>`).join('');
      return;
    }
    await S.queueMember(data, state.photoBlob, state.editingId);
    const c = await S.counts();
    toast(`Saved on this phone. ${c.waiting} waiting to sync.`, 'ok');
    resetForm();
    window.scrollTo(0, 0);
  }

  // --------------------------------------------------------------- outbox --

  const STATUS_LABEL = {
    pending: 'Waiting', syncing: 'Sending…', failed: 'Retrying', rejected: 'Needs fixing', synced: 'Sent',
  };

  async function renderOutbox() {
    const rows = await S.listOutbox();
    const el = $('#outbox-list');
    if (!rows.length) {
      el.innerHTML = '<p class="muted">No registrations on this phone yet.</p>';
      return;
    }
    el.innerHTML = rows.map((r) => {
      let extra = '';
      if (r.status === 'rejected' && r.errors) {
        const msgs = Object.entries(r.errors).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`);
        extra = `<ul class="errs">${msgs.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>
                 <button class="small" data-fix="${r.id}">Fix &amp; resend</button>`;
      } else if (r.status === 'failed' && r.last_error) {
        extra = `<div class="muted">${esc(r.last_error)} · attempt ${r.attempts}</div>`;
      } else if (r.flag_message) {
        extra = `<div class="muted">Sent · flagged for review: ${esc(r.flag_message)}</div>`;
      }
      return `<div class="item ${r.status}">
        <div class="row"><strong>${esc(r.data.full_name)}</strong>
          <span class="status">${STATUS_LABEL[r.status] || r.status}</span></div>
        <div class="muted">${new Date(r.created_at).toLocaleString()}</div>${extra}</div>`;
    }).join('');
  }

  async function onFix(id) {
    const row = (await S.listOutbox()).find((r) => r.id === id);
    if (!row) return;
    const f = $('#member-form');
    for (const k of ['full_name', 'date_of_birth', 'nid_number', 'phone_number', 'llg_ward', 'village_or_street']) {
      f.elements[k].value = row.data[k] || '';
    }
    const g = f.querySelector(`input[name="gender"][value="${row.data.gender}"]`);
    if (g) g.checked = true;
    $('#electorate').value = String(row.data.electorate || '');
    state.editingId = id;
    state.photoBlob = row.photo || null;
    setPreview(row.photo);
    $('#photo-status').textContent = row.photo ? 'Existing photo kept' : 'No photo';
    $('#form-title').textContent = 'Fix registration';
    show('register');
  }

  // -------------------------------------------------------------- history --

  async function renderHistory() {
    const el = $('#history-list');
    if (!navigator.onLine) { el.innerHTML = '<p class="muted">Connect to see your sync history.</p>'; return; }
    el.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const h = await S.fetchHistory();
      el.innerHTML = `<p><strong>${h.total_registered}</strong> members registered by you on the server.</p>` +
        (h.batches.length ? h.batches.map((b) => `<div class="item">
          <div class="row"><span>${new Date(b.received_at).toLocaleString()}</span>
          <span>${b.created} new</span></div>
          <div class="muted">${b.already_synced} repeat · ${b.flagged} flagged · ${b.rejected} rejected</div></div>`).join('')
          : '<p class="muted">No uploads yet.</p>');
    } catch (err) {
      el.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
    }
  }

  // ----------------------------------------------------------------- boot --

  async function boot() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/agent/sw.js', { scope: '/agent/' }).catch(() => {});
    }
    $('#login-form').addEventListener('submit', onLogin);
    $('#member-form').addEventListener('submit', onSave);
    $('#photo-input').addEventListener('change', onPhoto);
    $('#cancel-edit').addEventListener('click', resetForm);
    $('#sync-btn').addEventListener('click', async () => {
      const r = await S.syncNow({ force: true, reason: 'manual' });
      if (r.needsLogin) { toast('Log in to sync.', 'warn'); show('login'); }
      else if (r.error) toast(r.error, 'warn');
      else if (r.sent || r.rejected) toast(`Sent ${r.sent}.${r.rejected ? ` ${r.rejected} need fixing.` : ''}`, r.rejected ? 'warn' : 'ok');
    });
    $('#logout-btn').addEventListener('click', async () => { await S.logout(); show('login'); renderStatus(); });
    document.querySelectorAll('nav [data-view]').forEach((b) =>
      b.addEventListener('click', () => show(b.dataset.view)));
    $('#outbox-list').addEventListener('click', (e) => {
      const id = e.target.dataset && e.target.dataset.fix;
      if (id) onFix(id);
    });
    $('#login-banner').addEventListener('click', () => show('login'));

    window.addEventListener('outbox-changed', () => {
      renderStatus();
      if (!$('#view-outbox').hidden) renderOutbox();
    });
    window.addEventListener('sync-state', renderStatus);
    window.addEventListener('online', renderStatus);
    window.addEventListener('offline', renderStatus);

    state.lookup = await S.getLookup();
    const username = await S.getMeta('username');
    if (state.lookup && username) {
      $('#who').textContent = username;
      fillElectorates();
      show('register');
    } else {
      show('login');   // first run must be online to download electorates
    }
    await S.start();
    renderStatus();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
