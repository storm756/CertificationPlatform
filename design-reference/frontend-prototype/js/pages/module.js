CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, params, progress, unitsFor, partsFor, moduleCompletion, isTranslated, draftTag } = CSFR;
  const C = window.CSFRCourse;
  const root = $('[data-module-root]');
  const n = Number(params.get('m')) || 1;
  const catalog = await CSFR.loadCatalog();
  const cat = catalog.find((m) => m.n === n);
  if (!cat) { location.replace('404.html'); return; }
  root.dataset.mod = String(n);
  document.title = `${cat.title} · Module ${n} · CSFR`;

  /* ---------- Capstone: content slot ---------- */
  if (cat.kind === 'capstone') {
    root.innerHTML = `
      <section class="band band--mod"><div class="shell">
        <nav class="crumbs" aria-label="Breadcrumb"><a href="modules.html">${esc(t('nav.modules'))}</a>${icon('chevron-right')}<span aria-current="page">Module 10</span></nav>
        <p class="eyebrow eyebrow--cyan">Module 10 · Capstone</p><h1>${esc(tc(cat.title))}</h1>
        <p class="lede">${esc(cat.tagline)}</p>
        <div class="band-meta"><span>${icon('clock')}≈ ${cat.hours} h</span><span>${icon('users')}Run in the classroom with your mentor</span><span>${icon('info')}Learning module, not graded</span></div>
      </div></section>
      <section class="shell section stack-lg" style="max-width:52rem">
        <div class="notice notice--plum">${icon('flag')}<div><h2 style="font-size:1.3rem">What the capstone is</h2><p>A realistic case that uses every module: identify the incident, triage it, preserve evidence, report it and support the person. It doesn’t count towards your result, but it is the best preparation for the final.</p></div></div>
        <p class="slot">Content slot: the capstone brief, case material and handout (m10 PDF) from the content team go here.</p>
        <div class="row"><a class="btn btn-accent" href="assessment.html?part=mock">${icon('retry')}Try the practice mock</a><a class="btn btn-outline" href="final.html">${icon('flag')}See the final exam</a></div>
      </section>`;
    return;
  }

  const mod = await CSFR.loadModule(n);
  const o = mod.overview;
  const units = unitsFor(cat), parts = partsFor(cat), comp = moduleCompletion(cat);
  const next = units.find((u) => !progress.unitDone(u.id));
  const nextHref = next ? C.unitHref(n, next.id) : C.partHref(n, 'mcq');
  const prevMod = catalog.find((m) => m.n === n - 1), nextMod = catalog.find((m) => m.n === n + 1);

  const unitRow = (u) => {
    const done = progress.unitDone(u.id);
    const title = u.kind === 'reading' ? `${t('c.topic')} ${u.index + 1} · ${tc(u.title)}` : u.title;
    return `<a class="unit-row" href="${C.unitHref(n, u.id)}"><span class="unit-row__icon">${icon(C.KIND_ICON[u.kind])}</span>
      <span><h4>${esc(title)}</h4><small>${u.kind === 'film' ? `${CSFR.P('Film')} · ${Math.round((mod.film?.duration || 90) / 60 * 10) / 10} ${t('c.min')} · ${CSFR.P('transcript in English and हिन्दी')}` : `${u.minutes} ${t('c.min')}`}</small></span>
      <span class="status status--${done ? 'done' : 'todo'}">${icon(done ? 'check-circle' : 'circle')}<span class="sr-only">${done ? t('c.completed') : t('c.notStarted')}</span></span></a>`;
  };
  const group = (key, num, list) => list.length ? `<div class="unit-group"><h3><span>${num}</span>${esc(t(key))}</h3><div class="unit-list">${list.map(unitRow).join('')}</div></div>` : '';
  const partCard = (p) => {
    const s = C.partStatus(p); const atts = progress.attempts(p.id);
    const isInt = p.part === 'int';
    const meta = isInt ? mod.interactive : null;
    return `<article class="part-card">
      <div class="part-card__head"><div><p class="eyebrow" style="margin-bottom:.3rem">${isInt ? esc(meta.gameTitle || 'Interactive') : 'Multiple choice'}</p><h3 style="font-size:1.35rem">${esc(p.title)}</h3></div>
        <span class="status status--${s.cls}">${icon(s.icon)}${esc(s.label)}</span></div>
      ${isInt && meta.story ? `<p class="muted">${esc(meta.story)}</p>` : ''}
      ${p.pending ? `<div class="notice notice--mustard">${icon('clock')}<p>This module’s graded interactive set is being replaced. The crosswords are now practice only, and about six new challenges are being written. Until they arrive, practise with the <a class="link" href="${C.unitHref(n, `m${n}:xw`)}">crossword</a>.</p></div>` : `
      <dl><div><dt>Marks</dt><dd>${p.marks} of 100</dd></div><div><dt>${isInt ? 'Challenges' : 'Questions'}</dt><dd>${p.count}</dd></div><div><dt>Time</dt><dd>${isInt ? `about ${meta.minutes} ${t('c.min')}` : 'count-up, not enforced'}</dd></div><div><dt>Attempts</dt><dd>Unlimited · best counts</dd></div><div><dt>Best</dt><dd>${atts.length ? 'Scored on the server' : '—'}</dd></div></dl>
      <div class="row"><a class="btn ${atts.length ? 'btn-outline' : 'btn-primary'}" href="${C.partHref(n, p.part)}">${icon(atts.length ? 'retry' : 'arrow')}${atts.length ? t('c.retake') : t('c.start')}</a><span class="muted" style="font-size:.9rem">Pass mark 50%. Answer every question so it counts towards unlocking the final.</span></div>`}
    </article>`;
  };

  root.innerHTML = `
    <section class="band band--mod"><div class="shell">
      <nav class="crumbs" aria-label="Breadcrumb"><a href="index.html">${esc(t('nav.home'))}</a>${icon('chevron-right')}<a href="modules.html">${esc(t('nav.modules'))}</a>${icon('chevron-right')}<span aria-current="page">${esc(t('c.module'))} ${n}</span></nav>
      <div class="dash-hero">
        <div>
          <p class="eyebrow eyebrow--cyan">${esc(t('c.module'))} ${n} of 9</p>
          <h1>${esc(tc(o.title))} ${isTranslated(o.title) ? draftTag() : ''}</h1>
          <p class="lede">${esc(o.tagline)}</p>
          <div class="band-meta"><span>${icon('clock')}${esc(CSFR.P('≈ {0} h · {1} theory + {2} practical', cat.hours, cat.theory, cat.practical))}</span><span>${icon('book')}${esc(CSFR.P('{0} topics', cat.topics.length))}</span><span>${icon('video')}${esc(CSFR.P('1 film'))}</span><span>${icon('award')}100 ${esc(t('c.marks'))}</span></div>
          <div class="row" style="margin-top:1.5rem"><a class="btn btn-accent btn-lg" href="${nextHref}">${comp.done ? t('c.continue') : t('c.start')} ${icon('arrow', 'icon-arrow')}</a><a class="btn btn-ghost-dark" href="#assess" data-tab-link="assess">${esc(t('mod.assessments'))}</a></div>
        </div>
        <div class="ring" style="--v:${comp.pct}" role="img" aria-label="${comp.pct}% of this module complete"><div><strong style="color:#fff">${comp.pct}%</strong><small>${esc(CSFR.P('{0}/{1} units', comp.done, comp.total))}</small></div></div>
      </div>
    </div></section>

    <div class="shell course">
      ${C.outline(cat, null)}
      <div>
        <div class="tabs" role="tablist" aria-label="Module sections">
          <button class="tab" role="tab" id="tab-overview" aria-controls="panel-overview" aria-selected="true" data-tab="overview">${esc(t('mod.overview'))}</button>
          <button class="tab" role="tab" id="tab-content" aria-controls="panel-content" aria-selected="false" tabindex="-1" data-tab="content">${esc(t('mod.content'))}</button>
          <button class="tab" role="tab" id="tab-assess" aria-controls="panel-assess" aria-selected="false" tabindex="-1" data-tab="assess">${esc(t('mod.assessments'))}</button>
        </div>

        <section class="stack-lg" role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
          <div class="prose"><h2 style="margin-top:0">What is it?</h2><p>${esc(tc(o.what))}</p></div>
          <div class="card"><h3 style="font-size:1.3rem;margin-bottom:.9rem">${esc(t('mod.outcomes'))}</h3><ul class="outcomes">${(o.outcomes || []).map((x) => `<li>${icon('check-circle')}<span>${esc(tc(x))}</span></li>`).join('')}</ul></div>
          ${o.callout ? `<aside class="callout callout--key">${icon('shield-alert')}<span class="callout__label">Key rule</span><p>${esc(tc(o.callout))}</p></aside>` : ''}
          <div><h3 style="font-size:1.3rem;margin-bottom:.9rem">Topics in this module</h3><ol class="unit-list">${cat.topics.map((tt, i) => `<li><a class="unit-row" href="${C.unitHref(n, `m${n}:t${i + 1}`)}"><span class="unit-row__icon"><strong>${i + 1}</strong></span><span><h4>${esc(tc(tt))}</h4></span>${icon('chevron-right')}</a></li>`).join('')}</ol></div>
          ${o.stop ? `<div><h3 style="font-size:1.3rem;margin-bottom:.9rem">Stop · Save · Report</h3>${window.CSFRContent.ssr(o.stop, o.save || [], o.report || [])}</div>` : ''}
        </section>

        <section role="tabpanel" id="panel-content" aria-labelledby="tab-content" hidden>
          ${group('mod.watch', 1, units.filter((u) => u.group === 'watch'))}
          ${group('mod.read', 2, units.filter((u) => u.group === 'read'))}
          ${group('mod.handout', 3, units.filter((u) => u.group === 'handout'))}
          ${group('mod.practise', 4, units.filter((u) => u.group === 'practise'))}
        </section>

        <section role="tabpanel" id="panel-assess" aria-labelledby="tab-assess" hidden class="stack-lg">
          <div class="notice">${icon('info')}<p>Your module score is <strong>Part A (50 marks) + Part B (50 marks)</strong>, using your best attempt at each. You see your score, which questions to revisit and a hint for each, but never the correct option.</p></div>
          ${parts.map(partCard).join('')}
          ${mod.interactive.revise ? `<p class="muted">${icon('lightbulb')} ${esc(mod.interactive.revise)}</p>` : ''}
        </section>

        <nav class="unit-nav" aria-label="Other modules">
          ${prevMod ? `<a class="btn btn-ghost" href="module.html?m=${prevMod.n}">${icon('arrow-left')}${esc(t('c.module'))} ${prevMod.n}</a>` : '<span></span>'}
          ${nextMod ? `<a class="btn btn-outline" href="module.html?m=${nextMod.n}">${esc(t('c.module'))} ${nextMod.n} ${icon('arrow', 'icon-arrow')}</a>` : ''}
        </nav>
      </div>
    </div>`;
  C.wireOutline(root);

  const tabs = $$('[data-tab]', root);
  const select = (name, focus) => {
    tabs.forEach((tb) => { const on = tb.dataset.tab === name; tb.setAttribute('aria-selected', String(on)); tb.tabIndex = on ? 0 : -1; if (on && focus) tb.focus(); });
    ['overview', 'content', 'assess'].forEach((p) => { $(`#panel-${p}`).hidden = p !== name; });
    history.replaceState(null, '', `${location.pathname}?m=${n}${name === 'overview' ? '' : `#${name}`}`);
  };
  tabs.forEach((tb, i) => {
    tb.addEventListener('click', () => select(tb.dataset.tab));
    tb.addEventListener('keydown', (e) => { const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key]; if (d) { e.preventDefault(); select(tabs[(i + d + tabs.length) % tabs.length].dataset.tab, true); } });
  });
  $$('[data-tab-link]', root).forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); select(a.dataset.tabLink); $('.tabs', root).scrollIntoView({ behavior: CSFR.reduceMotion ? 'auto' : 'smooth' }); }));
  const hash = location.hash.replace('#', '');
  if (['content', 'assess'].includes(hash)) select(hash);
});
