/* Mentor dashboard. All learners and numbers are SAMPLE data. Mentors only ever see their own batches
   (batches.scoping.batches_for(user) on the server). */
CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, store, session, requireRole, toast, confirmDialog } = CSFR;
  if (!requireRole('mentor')) return;
  const root = $('[data-mentor-root]');
  const me = session.get();
  const catalog = await CSFR.loadCatalog();
  const learning = catalog.filter((m) => m.kind === 'learning');

  const batches = store.get('mentorBatches', [
    { id: 'sakec-3', name: 'SAKEC Mumbai · Community batch', open: true, opens: '2027-01-10', closes: '2027-02-28', seats: 60, used: 42, newSignups: 5, autoIssue: false },
    { id: 'ngo-1', name: 'Partner NGO · Weekend batch', open: false, opens: '', closes: '', seats: 40, used: 31, newSignups: 0, autoIssue: true },
  ]);
  const saveBatches = () => store.set('mentorBatches', batches);
  const NAMES = ['Asha Desai', 'Rahul Mehta', 'Fatima Shaikh', 'Kiran Patil', 'Meera Iyer', 'Arjun Nair', 'Sneha Joshi', 'Vikram Rao', 'Pooja Gupta', 'Imran Khan', 'Divya Kulkarni', 'Sanjay Verma'];
  // Deterministic sample scores: mostly passing, a few below 50 so the heatmap shows every state.
  const LOW = { '3,5': 44, '8,1': 47, '10,3': 38 };
  const score = (i, j) => LOW[`${i},${j}`] ?? Math.min(96, 54 + ((i * 7) % 30) + ((j * 13 + i * 5) % 14));
  const learners = NAMES.map((name, i) => {
    const reach = [9, 9, 9, 6, 9, 3, 9, 9, 7, 9, 5, 2][i];
    const mods = learning.map((m, j) => (j < reach ? score(i, j) : null));
    const done = mods.filter((x) => x !== null);
    const mean = done.length === 9 ? done.reduce((a, b) => a + b, 0) / 9 : null;
    const final = mean !== null && i !== 9 ? Math.min(95, Math.round(mean) - 6 + (i % 4) * 3) : null;
    const overall = mean !== null && final !== null ? Math.round((0.5 * mean + 0.5 * final) * 10) / 10 : null;
    const eligible = overall !== null && mods.every((x) => x >= 50) && final >= 50;
    const lastActive = [1, 2, 9, 0, 3, 12, 1, 4, 8, 2, 0, 15][i];
    const status = eligible ? (i % 2 ? 'Issued' : 'Awaiting approval') : i === 5 ? 'Pending guardian' : 'Active';
    return { id: `L${100 + i}`, name, batch: i < 8 ? 'sakec-3' : 'ngo-1', mods, final, overall, eligible, lastActive, status, belowAttempts: i === 3 ? 3 : 0 };
  });
  const cls = (v) => (v === null ? 'h--na' : v >= 60 ? 'h--hi' : v >= 50 ? 'h--mid' : 'h--lo');
  const sym = (v) => (v === null ? '–' : v >= 50 ? `${v}` : `${v}!`);

  let filterBatch = 'all', q = '';
  const render = () => {
    const list = learners.filter((l) => (filterBatch === 'all' || l.batch === filterBatch) && (!q || l.name.toLowerCase().includes(q)));
    const awaiting = learners.filter((l) => l.status === 'Awaiting approval');
    const issued = learners.filter((l) => l.status === 'Issued');
    const stuck = learners.filter((l) => l.lastActive >= 7 || l.belowAttempts >= 3);
    root.innerHTML = `
      <section class="band on-dark"><div class="shell">
        <p class="eyebrow eyebrow--cyan">${esc(t('nav.mentor'))}</p><h1>Hello, ${esc(me.name.split(' ')[0])}</h1>
        <p class="lede">You can see your own batches only. Every action here is logged.</p>
        <div class="band-meta"><span>${icon('users')}${learners.length} learners</span><span>${icon('layers')}${batches.length} batches</span><span>${icon('award')}${awaiting.length} awaiting approval</span></div>
      </div></section>
      <div class="shell section stack-lg">
        <p class="demo-note">${icon('eye', 'icon--sm')}${esc(t('c.demo'))} · <span>All learners and numbers below are sample data.</span></p>
        <div class="stat-grid">
          <div class="stat" style="--c:var(--teal)"><p class="kpi"><strong>${learners.filter((l) => l.status !== 'Pending guardian').length}</strong><span>Active learners</span></p></div>
          <div class="stat" style="--c:var(--mustard-deep)"><p class="kpi"><strong>${learners.filter((l) => l.eligible).length}</strong><span>Eligible for a certificate</span></p></div>
          <div class="stat" style="--c:var(--terracotta)"><p class="kpi"><strong>${stuck.length}</strong><span>Need a nudge</span></p></div>
          <div class="stat" style="--c:var(--plum)"><p class="kpi"><strong>${batches.reduce((s, b) => s + b.newSignups, 0)}</strong><span>New sign-ups this week</span></p></div>
        </div>

        <section aria-labelledby="b-title"><div class="section-title"><h2 id="b-title">Batches and registration</h2></div>
          <div class="grid-2">${batches.map((b, i) => `<article class="card card--edge" style="--m:${b.open ? 'var(--teal)' : 'var(--ink-soft)'}">
            <div class="row" style="justify-content:space-between;align-items:flex-start"><h3>${esc(b.name)}</h3><span class="badge ${b.open ? 'badge--teal' : 'badge--muted'}">${icon(b.open ? 'unlock' : 'lock', 'icon--sm')}${b.open ? 'Accepting sign-ups' : 'Registration closed'}</span></div>
            <p class="muted" style="margin:.4rem 0 .9rem">${b.open ? `Open ${b.opens ? `from ${b.opens}` : ''}${b.closes ? ` until ${b.closes}` : ''}` : 'Closed. New learners cannot register.'} · ${b.used} of ${b.seats} seats used</p>
            <div class="bar" style="--v:${Math.round((b.used / b.seats) * 100)};margin-bottom:1rem"><i></i></div>
            <div class="stack">
              <div class="row"><button class="btn btn-sm ${b.open ? 'btn-danger' : 'btn-primary'}" type="button" data-toggle-reg="${i}">${icon(b.open ? 'lock' : 'unlock')}${b.open ? 'Close registration' : 'Open registration'}</button>
                <button class="btn btn-sm btn-ghost" type="button" data-demo="A one-time registration link lets a learner join after the batch has closed.">${icon('link')}One-time registration link</button></div>
              <label class="switch"><input type="checkbox" data-auto="${i}" ${b.autoIssue ? 'checked' : ''}><span><strong>Auto-issue certificates</strong><br><span class="muted" style="font-size:.9rem">New eligible learners get their certificate straight away. Turning this on does <strong>not</strong> issue certificates to learners already waiting. Approve those below.</span></span></label>
            </div></article>`).join('')}</div></section>

        <section aria-labelledby="a-title" class="grid-2" style="align-items:start">
          <article class="card"><div class="section-title" style="margin-bottom:.75rem"><h2 id="a-title" style="font-size:1.4rem">Awaiting approval</h2>${awaiting.length ? `<button class="btn btn-sm btn-primary" type="button" data-approve-all>${icon('check')}Approve all ${awaiting.length}</button>` : ''}</div>
            <ul class="result-list">${awaiting.map((l) => `<li class="result-item"><span class="avatar" style="width:2rem;height:2rem;font-size:.8rem">${esc(l.name.split(' ').map((w) => w[0]).join(''))}</span><span><strong>${esc(l.name.toUpperCase())}</strong><br><span class="muted" style="font-size:.88rem">Overall ${l.overall}% · check the printed name</span></span><button class="btn btn-sm btn-outline" type="button" data-approve="${l.id}">Approve</button></li>`).join('') || '<li class="muted">No one is waiting.</li>'}</ul></article>
          <article class="card"><h2 style="font-size:1.4rem;margin-bottom:.75rem">Issued this week</h2><ul class="result-list">${issued.map((l) => `<li class="result-item"><span>${icon('award')}</span><span>${esc(l.name)}</span><span class="badge badge--teal">Issued</span></li>`).join('')}</ul></article>
        </section>

        <section aria-labelledby="s-title"><div class="section-title"><h2 id="s-title">Learners who may be stuck</h2><span class="muted">Inactive 7+ days, or below 50% after 3 attempts</span></div>
          <div class="grid-3">${stuck.map((l) => `<article class="card"><h3>${esc(l.name)}</h3><p class="muted">${l.belowAttempts >= 3 ? `Module 6 below 50% after ${l.belowAttempts} attempts` : `Last active ${l.lastActive} days ago`}</p><div class="row" style="margin-top:.75rem"><button class="btn btn-sm btn-outline" type="button" data-demo="Opens a message to ${esc(l.name)} from your own email.">${icon('mail')}Contact</button><button class="btn btn-sm btn-ghost" type="button" data-reset="${l.id}">${icon('retry')}Reset link</button></div></article>`).join('')}</div></section>

        <section aria-labelledby="r-title">
          <div class="section-title"><h2 id="r-title">Roster and module heatmap</h2><button class="btn btn-sm btn-outline" type="button" data-csv>${icon('download')}Export CSV</button></div>
          <div class="catalog-tools">
            <div class="search">${icon('search')}<label class="sr-only" for="m-search">Search learners</label><input class="input" id="m-search" type="search" placeholder="Search learners" value="${esc(q)}"></div>
            <div class="seg" role="group" aria-label="Batch">${[['all', 'All batches'], ...batches.map((b) => [b.id, b.name.split(' · ')[0]])].map(([id, label]) => `<button type="button" data-batch="${id}" aria-pressed="${filterBatch === id}">${esc(label)}</button>`).join('')}</div>
          </div>
          <p class="muted" style="font-size:.9rem;margin-bottom:.75rem">Module scores in %. Below 50 is marked with <strong>!</strong> and a red cell. A dash means not started.</p>
          <div class="table-wrap" tabindex="0" role="region" aria-label="Learner by module heatmap">
            <table class="table heat"><thead><tr><th scope="col">Learner</th>${learning.map((m) => `<th scope="col" title="${esc(m.title)}">M${m.n}</th>`).join('')}<th scope="col">Final</th><th scope="col">Overall</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
            <tbody>${list.map((l) => `<tr><th scope="row" style="font-weight:600">${esc(l.name)}</th>${l.mods.map((v, j) => `<td class="h ${cls(v)}" aria-label="Module ${j + 1}: ${v === null ? 'not started' : `${v}%${v < 50 ? ', below pass mark' : ''}`}">${sym(v)}</td>`).join('')}<td class="h ${cls(l.final)}">${sym(l.final)}</td><td><strong>${l.overall ?? '–'}</strong></td><td><span class="badge ${l.status === 'Issued' ? 'badge--teal' : l.status === 'Awaiting approval' ? 'badge--mustard' : l.status === 'Pending guardian' ? 'badge--plum' : 'badge--muted'}">${esc(l.status)}</span></td><td><button class="btn btn-sm btn-ghost" type="button" data-rename="${l.id}">${icon('user')}Name</button></td></tr>`).join('') || `<tr><td colspan="14" class="muted">No learners match.</td></tr>`}</tbody></table>
          </div>
        </section>
      </div>`;
    wire();
  };

  const wire = () => {
    $$('[data-toggle-reg]').forEach((btn) => btn.addEventListener('click', async () => {
      const b = batches[Number(btn.dataset.toggleReg)];
      const ok = await confirmDialog({ title: b.open ? 'Close registration?' : 'Open registration?', body: b.open ? `New learners won’t be able to join <strong>${esc(b.name)}</strong>. Anyone already registered keeps access.` : `Learners will be able to choose <strong>${esc(b.name)}</strong> when they register, until it closes or the ${b.seats} seats fill.`, confirm: b.open ? 'Close registration' : 'Open registration', danger: b.open });
      if (!ok) return; b.open = !b.open; saveBatches(); render(); toast(b.open ? 'Registration opened' : 'Registration closed');
    }));
    $$('[data-auto]').forEach((c) => c.addEventListener('change', async () => {
      const b = batches[Number(c.dataset.auto)];
      if (c.checked) { const ok = await confirmDialog({ title: 'Turn on auto-issue?', body: 'From now on, learners who become eligible get their certificate automatically. Learners already waiting are <strong>not</strong> issued. You still approve them yourself.', confirm: 'Turn on' }); if (!ok) { c.checked = false; return; } }
      b.autoIssue = c.checked; saveBatches(); toast(`Auto-issue ${b.autoIssue ? 'on' : 'off'} for ${b.name}`);
    }));
    $$('[data-approve]').forEach((b) => b.addEventListener('click', () => { const l = learners.find((x) => x.id === b.dataset.approve); l.status = 'Issued'; render(); toast(`Certificate issued to ${l.name}`); }));
    $('[data-approve-all]')?.addEventListener('click', async () => {
      const waiting = learners.filter((l) => l.status === 'Awaiting approval');
      if (await confirmDialog({ title: `Approve ${waiting.length} certificates?`, body: 'Check that each printed name is spelled correctly. Certificates are issued immediately.', confirm: 'Approve all' })) { waiting.forEach((l) => { l.status = 'Issued'; }); render(); toast(`${waiting.length} certificates issued`); }
    });
    $$('[data-reset]').forEach((b) => b.addEventListener('click', async () => {
      const l = learners.find((x) => x.id === b.dataset.reset);
      if (await confirmDialog({ title: `Create a reset link for ${l.name}?`, body: 'The link works once, for 1 hour. Hand it over in person. It signs the learner out everywhere, shows them a notice at next sign-in and blocks email changes for 7 days.', confirm: 'Create link' })) toast('One-time link created (preview). Hand it over in person.');
    }));
    $$('[data-rename]').forEach((b) => b.addEventListener('click', async () => {
      const l = learners.find((x) => x.id === b.dataset.rename);
      if (await confirmDialog({ title: 'Change certificate name?', body: `Current name: <strong>${esc(l.name.toUpperCase())}</strong>. Name changes are logged. Already-issued certificates don’t change.`, confirm: 'Continue' })) toast('Name editor opens here in the live platform.');
    }));
    $('[data-csv]').addEventListener('click', async () => { if (await confirmDialog({ title: 'Export roster as CSV?', body: 'The export contains personal data for your batches only. It is logged, and cells are made safe for spreadsheets. Store it securely and delete it when done.', confirm: 'Export' })) toast('CSV export is generated by the server in the live platform.'); });
    $('#m-search').addEventListener('input', (e) => { q = e.target.value.trim().toLowerCase(); const pos = e.target.selectionStart; render(); const s = $('#m-search'); s.focus(); s.setSelectionRange(pos, pos); });
    $$('[data-batch]').forEach((b) => b.addEventListener('click', () => { filterBatch = b.dataset.batch; render(); }));
  };
  render();
});
