CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, P, params, progress, unitsFor, lang, isTranslated, draftTag, toast } = CSFR;
  const C = window.CSFRCourse, K = window.CSFRContent, E = window.CSFREngine;
  const root = $('[data-unit-root]');
  const n = Number(params.get('m')) || 1;
  const catalog = await CSFR.loadCatalog();
  const cat = catalog.find((m) => m.n === n && m.kind === 'learning');
  if (!cat) { location.replace('404.html'); return; }
  const mod = await CSFR.loadModule(n);
  const units = unitsFor(cat);
  const uid = `m${n}:${params.get('u') || 'film'}`;
  const unit = units.find((u) => u.id === uid);
  if (!unit) { location.replace(`module.html?m=${n}`); return; }
  root.dataset.mod = String(n);
  const title = unit.kind === 'reading' ? tc(unit.title) : unit.title;
  document.title = `${title} · Module ${n} · CSFR`;

  const seq = C.sequence(cat); const pos = seq.findIndex((s) => s.id === uid);
  const prev = seq[pos - 1], next = seq[pos + 1];
  const kindLabel = { film: P('Film'), reading: P('Topic {0} of {1}', (unit.index ?? 0) + 1, cat.topics.length), handout: P('Handout'), check: P('Practice check'), practice: P('Practice quiz'), crossword: P('Practice') }[unit.kind];
  const translated = unit.kind === 'reading' && lang !== 'en' && isTranslated(unit.title);

  root.innerHTML = `
    <div class="reading-progress" data-read-progress aria-hidden="true" hidden></div>
    <div class="shell course">
      ${C.outline(cat, uid)}
      <article>
        <nav class="crumbs" aria-label="Breadcrumb" style="color:var(--ink-muted)"><a href="modules.html" style="color:var(--ink)">${esc(t('nav.modules'))}</a>${icon('chevron-right')}<a href="module.html?m=${n}" style="color:var(--ink)">${esc(t('c.module'))} ${n}</a>${icon('chevron-right')}<span aria-current="page">${esc(kindLabel)}</span></nav>
        <header class="unit-head">
          <p class="eyebrow" style="color:var(--m)">${esc(kindLabel)} · ${unit.minutes} ${esc(t('c.min'))}</p>
          <h1>${esc(title)} ${translated ? draftTag() : ''}</h1>
          ${unit.kind === 'film' ? `<p class="muted">${esc(P('{0}: a short introduction to the module.', tc(mod.overview.title)))}</p>` : ''}
        </header>
        <div data-unit-body></div>
        <div class="complete-bar" data-complete-bar>
          <span class="status" data-complete-status></span>
          <button class="btn btn-primary" type="button" data-mark>${icon('check')}${esc(t('unit.markComplete'))}</button>
        </div>
        <nav class="unit-nav" aria-label="Lesson navigation">
          ${prev ? `<a class="btn btn-ghost" href="${prev.href}">${icon('arrow-left')}<span><small class="muted" style="display:block;font-weight:500">${esc(t('c.previous'))}</small>${esc(prev.title)}</span></a>` : '<span></span>'}
          ${next ? `<a class="btn btn-outline" href="${next.href}"><span><small class="muted" style="display:block;font-weight:500">${esc(t('c.next'))}</small>${esc(next.title)}</span>${icon('arrow', 'icon-arrow')}</a>` : `<a class="btn btn-outline" href="module.html?m=${n}">${esc(t('c.module'))} ${n} ${icon('arrow')}</a>`}
        </nav>
      </article>
    </div>`;
  C.wireOutline(root);
  const bodyEl = $('[data-unit-body]', root);

  const markDone = (quiet) => {
    if (!progress.unitDone(uid)) { progress.markUnit(uid); if (!quiet) toast(`${t('c.completed')}: ${title}`); }
    const bar = $('[data-complete-bar]'); bar.classList.add('is-done');
    $('[data-complete-status]').innerHTML = `${icon('check-circle')}${esc(t('c.completed'))}`;
    $('[data-complete-status]').className = 'status status--done';
    $('[data-mark]').hidden = true;
    const link = $(`.outline a[aria-current="page"]`); if (link) { link.classList.add('is-done'); link.querySelector('use')?.setAttribute('href', '#i-check-circle'); }
  };
  const completeRule = { film: 'Completes at 80% watched', reading: 'Completes when you reach the end', handout: 'Completes when opened', check: 'Completes after one try', practice: 'Completes when submitted once', crossword: 'Completes when submitted once' }[unit.kind];
  $('[data-complete-status]').innerHTML = `${icon('info')}${esc(completeRule)}`;
  $('[data-mark]').addEventListener('click', () => markDone());

  /* ---------- Film: poster + timed narration captions + transcript ---------- */
  if (unit.kind === 'film') {
    const f = mod.film; const dur = f.duration || 90;
    const cap0 = (l) => (lang === 'hi' ? (l.hi || l.en) : tc(l.en));
    const langLabel = (CSFR.LANGS.find((x) => x.code === lang) || CSFR.LANGS[0]).label;
    bodyEl.innerHTML = `
      <div class="film">
        <div class="film__stage"><img src="${esc(f.poster)}" alt="" width="1280" height="720"><div class="film__shade"></div>
          <button class="film__play" type="button" data-play aria-label="Play preview">${icon('play')}</button>
          <p class="film__caption" aria-live="off" data-caption></p></div>
        <div class="film__controls">
          <button type="button" data-toggle aria-label="Play">${icon('play')}</button>
          <div class="film__track" role="progressbar" aria-label="Film progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" data-track><i></i></div>
          <span class="film__time" data-time>0:00 / ${K.fmtTime(dur)}</span>
        </div>
      </div>
      <div class="notice" style="margin-top:1rem">${icon('video')}<p>The film streams from the programme’s YouTube channel in privacy-enhanced mode, with an MP4 fallback where YouTube is blocked. This preview plays the narration as captions over the poster.</p></div>
      <h2 style="font-size:1.4rem;margin:2rem 0 .75rem">${esc(t('unit.transcript'))} <span class="badge badge--muted">${esc(langLabel)}</span></h2>
      <div class="transcript" data-transcript>${f.lines.map((l, i) => `<button type="button" data-line="${i}" data-t="${l.t0}"><time>${K.fmtTime(l.t0)}</time><span>${esc(cap0(l))}</span></button>`).join('')}</div>`;
    let tNow = 0, timer = null, maxSeen = 0;
    const cap = $('[data-caption]'), track = $('[data-track]'), time = $('[data-time]');
    const render = () => {
      const pct = Math.min(100, (tNow / dur) * 100);
      track.style.setProperty('--v', pct); track.setAttribute('aria-valuenow', String(Math.round(pct)));
      time.textContent = `${K.fmtTime(tNow)} / ${K.fmtTime(dur)}`;
      const idx = f.lines.findIndex((l) => tNow >= l.t0 && tNow <= l.t1 + 0.6);
      cap.textContent = idx >= 0 ? cap0(f.lines[idx]) : '';
      $$('[data-line]').forEach((b, i) => b.classList.toggle('is-on', i === idx));
      maxSeen = Math.max(maxSeen, tNow);
      if (maxSeen / dur >= 0.8) markDone();
    };
    const setPlaying = (on) => {
      clearInterval(timer); timer = null;
      $('[data-play]').hidden = on;
      $('[data-toggle]').innerHTML = icon(on ? 'pause' : 'play'); $('[data-toggle]').setAttribute('aria-label', on ? 'Pause' : 'Play');
      if (on) timer = setInterval(() => { tNow = Math.min(dur, tNow + 0.25); render(); if (tNow >= dur) setPlaying(false); }, 250);
    };
    $('[data-play]').addEventListener('click', () => { if (tNow >= dur) tNow = 0; setPlaying(true); });
    $('[data-toggle]').addEventListener('click', () => setPlaying(!timer));
    $$('[data-line]').forEach((b) => b.addEventListener('click', () => { tNow = Number(b.dataset.t); render(); }));
    render();
  }

  /* ---------- Reading: booklet topic, completes at the end ---------- */
  if (unit.kind === 'reading') {
    const topic = mod.topics[unit.index];
    bodyEl.innerHTML = `<div class="prose">${K.blocks(topic.blocks)}</div><div data-end-sentinel style="height:1px"></div>`;
    const bar = $('[data-read-progress]'); bar.hidden = false;
    const sentinel = $('[data-end-sentinel]');
    const onScroll = () => {
      const r = bodyEl.getBoundingClientRect(); const pct = Math.max(0, Math.min(100, ((innerHeight - r.top) / r.height) * 100)); bar.style.setProperty('--v', pct);
      if (sentinel.getBoundingClientRect().top < innerHeight) markDone();
    };
    addEventListener('scroll', onScroll, { passive: true });
    if ('IntersectionObserver' in window) new IntersectionObserver((en, obs) => { if (en[0].isIntersecting) { markDone(); obs.disconnect(); } }).observe(sentinel);
  }

  /* ---------- Handout: web text of the module PDF (pages 1–8) ---------- */
  if (unit.kind === 'handout') {
    bodyEl.innerHTML = `
      <div class="notice notice--teal" style="margin-bottom:1.5rem">${icon('file')}<div><h2 style="font-size:1.1rem">${esc(P('Module {0} handout', n))}</h2><p>Read it here, or download the PDF to keep. <button class="btn btn-sm btn-outline" type="button" aria-disabled="true" data-demo="The handout PDF is uploaded by the content team. It isn’t in this preview yet.">${icon('download')}PDF (coming soon)</button></p></div></div>
      <div class="prose">${K.handout(mod)}</div>`;
    markDone(true);
  }

  /* ---------- Myth or fact (learning check, not graded) ---------- */
  if (unit.kind === 'check') {
    const myths = mod.overview.myths || [];
    bodyEl.innerHTML = `<p class="muted" style="margin-bottom:1.25rem">Three quick statements from this module. Decide, then see the explanation. This is practice: nothing is recorded as a score.</p>
      <div class="stack">${myths.map(([s], i) => `<div class="myth" data-myth="${i}"><p class="eyebrow" style="margin:0">Statement ${i + 1}</p><p class="myth__statement">${esc(tc(s))}</p>
        <div class="row" role="group" aria-label="Your answer"><button class="btn btn-outline" type="button" data-pick="fact">${icon('check')}Fact</button><button class="btn btn-outline" type="button" data-pick="myth">${icon('x')}Myth</button></div><div data-verdict aria-live="polite"></div></div>`).join('')}</div>`;
    let tried = 0;
    $$('[data-myth]').forEach((card) => card.addEventListener('click', (e) => {
      const b = e.target.closest('[data-pick]'); if (!b || card.dataset.done) return;
      const [, isTrue, why] = myths[Number(card.dataset.myth)];
      const right = (b.dataset.pick === 'fact') === isTrue;
      card.dataset.done = '1'; $$('[data-pick]', card).forEach((x) => { x.disabled = true; });
      $('[data-verdict]', card).innerHTML = `<div class="myth__verdict">${icon(right ? 'check-circle' : 'info')}<div><strong>${isTrue ? 'Fact.' : 'Myth.'}</strong> ${right ? 'You got it.' : 'Not quite.'} <span class="muted">${esc(tc(why))}</span></div></div>`;
      tried++; if (tried === 1) markDone();
    }));
  }

  /* ---------- Practice quiz (practice pool, answers never in the page) ---------- */
  if (unit.kind === 'practice' || unit.kind === 'crossword') {
    const items = unit.kind === 'practice' ? mod.practice.map((q) => ({ ...q, type: 'mcq' })) : mod.interactive.questions;
    const draftKey = uid; const saved = progress.draft(draftKey) || {};
    bodyEl.innerHTML = `
      <div class="notice" style="margin-bottom:1.5rem">${icon('retry')}<p>${unit.kind === 'practice' ? `${items.length} practice questions from the module’s practice pool.` : `${items.length} crosswords. These used to be graded but are now practice only.`} It doesn’t count towards your result. In the live platform the server checks your practice answers straight away and explains each one.</p></div>
      ${lang !== 'en' ? `<p class="demo-note" style="margin-bottom:1rem">${icon('globe', 'icon--sm')}${esc(t('lang.assessEnglish'))}</p>` : ''}
      <div class="stack-lg" data-practice>${items.map((q, i) => `<section class="qcard" aria-labelledby="pq-${i}"><div class="qcard__meta"><span class="qcard__format">${icon(E.formatOf(q)[1])}${esc(E.formatOf(q)[0])}</span><span class="muted">${i + 1} / ${items.length}</span></div>
        <h2 id="pq-${i}">${esc(q.q || q.title)}</h2>${q.ask ? `<p class="qcard__ask">${esc(q.ask)}</p>` : ''}${q.scene ? `<div class="scene">${q.sceneLabel ? `<small>${esc(q.sceneLabel)}</small>` : ''}${esc(q.scene)}</div>` : ''}<div data-q="${i}"></div></section>`).join('')}</div>
      <div class="row" style="margin-top:1.5rem"><button class="btn btn-accent btn-lg" type="button" data-practice-submit>${icon('check')}Check my answers</button><span class="muted" data-practice-count></span></div>
      <div data-practice-result style="margin-top:1rem"></div>`;
    const answers = saved;
    const count = () => { const done = items.filter((q, i) => E.isAnswered(q, answers[i])).length; $('[data-practice-count]').textContent = `${done} of ${items.length} answered`; };
    items.forEach((q, i) => E.mount($(`[data-q="${i}"]`), q, answers[i], (a) => { answers[i] = a; progress.saveDraft(draftKey, answers); count(); }));
    count();
    $('[data-practice-submit]').addEventListener('click', () => {
      $('[data-practice-result]').innerHTML = `<div class="state-panel" style="--c:var(--teal)" role="status"><span class="big-icon">${icon('check-circle')}</span><h2 style="font-size:1.5rem">Practice saved</h2><p class="muted">In the live platform, the server now marks these practice questions and shows the full explanation for each, because practice questions never appear in graded assessments. This preview has no answers, so nothing is marked here.</p><a class="btn btn-primary" href="${C.partHref(n, 'mcq')}">Go to Part A ${icon('arrow')}</a></div>`;
      markDone();
    });
  }

  if (progress.unitDone(uid)) markDone(true);
});
