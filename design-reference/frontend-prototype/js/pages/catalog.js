CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, P, moduleCompletion } = CSFR;
  const catalog = await CSFR.loadCatalog();
  const learning = catalog.filter((m) => m.kind === 'learning');
  const totalHours = catalog.reduce((s, m) => s + (m.hours || 0), 0);
  const totalTopics = learning.reduce((s, m) => s + m.topics.length, 0);
  $('[data-cat-meta]').innerHTML = [
    ['layers', P('{0} counted modules + capstone', learning.length)], ['book', P('{0} readings', totalTopics)], ['video', P('{0} films', learning.filter((m) => m.hasFilm).length)],
    ['clock', P('≈ {0} hours of guided study', totalHours)], ['globe', 'English · हिन्दी · मराठी · ગુજરાતી'],
  ].map(([i, s]) => `<span>${icon(i)}${esc(s)}</span>`).join('');

  const FORMAT_NAMES = { mc: 'Quick verdict', spot: 'Spot the signs', chat: 'Conversation', pick: 'Evidence bag', build: 'Build the reply', crossword: 'Crossword', settings: 'Fix the settings' };
  const card = (m) => {
    const c = m.kind === 'learning' ? moduleCompletion(m) : { pct: 0, done: 0, total: 0 };
    const state = c.pct >= 100 ? 'done' : c.pct > 0 ? 'progress' : 'todo';
    const label = { done: t('c.completed'), progress: t('c.inProgress'), todo: t('c.notStarted') }[state];
    const fmt = (m.challengeFormats || []).map((f) => P(FORMAT_NAMES[f] || f)).join(', ');
    return `<a class="mod-card" href="module.html?m=${m.n}" data-mod="${m.n}" data-state="${state}" data-search="${esc([m.title, m.tagline, ...(m.topics || []), tc(m.title)].join(' ').toLowerCase())}">
      <div class="mod-card__top">
        ${m.hasFilm ? `<img class="mod-card__poster" src="assets/films/m${m.n}.jpg" alt="" loading="lazy" width="640" height="360">` : ''}
        <div style="position:relative"><p class="mod-card__kicker">${m.kind === 'capstone' ? 'Capstone' : `${esc(t('c.module'))}`}</p><p class="mod-card__num">${String(m.n).padStart(2, '0')}</p></div>
        <div style="position:relative;text-align:right">${m.kind === 'capstone' ? '<span class="badge" style="background:rgba(255,255,255,.2);color:#fff">Not graded</span>' : `<span class="badge" style="background:rgba(255,255,255,.2);color:#fff">100 ${esc(t('c.marks'))}</span>`}</div>
      </div>
      <div class="mod-card__body">
        <h3>${esc(tc(m.title))}</h3>
        <p>${esc(P(m.tagline))}</p>
        <div class="mod-card__meta">
          ${m.kind === 'learning' ? `<span>${icon('book', 'icon--sm')}${esc(P('{0} topics', m.topics.length))}</span><span>${icon('clock', 'icon--sm')}${esc(P('≈ {0} h', m.hours))}</span><span>${icon('square-check', 'icon--sm')}${esc(P('{0} MCQs', m.mcqCount))}</span><span>${icon('layers', 'icon--sm')}${esc(m.interactivePracticeOnly ? P('Crossword practice') : P('{0} challenges', m.challengeCount))}</span>` : `<span>${icon('clock', 'icon--sm')}${esc(P('≈ {0} h', m.hours))}</span><span>${icon('users', 'icon--sm')}${esc(P('Classroom simulation'))}</span>`}
        </div>
        ${fmt ? `<p style="font-size:.88rem"><strong>${esc(P('Interactive:'))}</strong> ${esc(fmt)}</p>` : ''}
      </div>
      ${m.kind === 'learning' ? `<div class="mod-card__foot"><div class="row"><span class="status status--${state}">${icon(state === 'done' ? 'check-circle' : state === 'progress' ? 'circle-dot' : 'circle', 'icon--sm')}${esc(label)}</span><span>${c.pct}%</span></div><div class="bar" style="--v:${c.pct}" role="img" aria-label="${c.pct}% complete"><i></i></div></div>` : '<div class="mod-card__foot"><p class="muted" style="font-size:.9rem">Content arriving from the programme team</p></div>'}
    </a>`;
  };
  const grid = $('[data-cat-grid]');
  grid.innerHTML = catalog.map(card).join('');

  let filter = 'all';
  const search = $('#cat-search');
  const apply = () => {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    $$('.mod-card', grid).forEach((el) => {
      const ok = (filter === 'all' || el.dataset.state === filter) && (!q || el.dataset.search.includes(q));
      el.hidden = !ok; if (ok) shown++;
    });
    $('[data-cat-empty]').hidden = shown > 0;
    $('[data-cat-count]').textContent = `${shown} modules shown`;
  };
  search.addEventListener('input', apply);
  $$('[data-filter]').forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter; $$('[data-filter]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); apply(); }));
});
