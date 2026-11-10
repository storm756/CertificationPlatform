/* Course structure helpers shared by the catalogue, module, unit and assessment pages. */
window.CSFRCourse = (() => {
  const { esc, icon, tc, t, progress, unitsFor, partsFor, moduleCompletion } = CSFR;
  const KIND_ICON = { film: 'video', reading: 'book', handout: 'file', check: 'lightbulb', practice: 'retry', crossword: 'grid', mcq: 'square-check', int: 'layers' };
  const GROUPS = [['watch', 'mod.watch'], ['read', 'mod.read'], ['handout', 'mod.handout'], ['practise', 'mod.practise'], ['assess', 'mod.assess']];
  const unitHref = (n, id) => `unit.html?m=${n}&u=${encodeURIComponent(id.split(':')[1])}`;
  const partHref = (n, part) => `assessment.html?m=${n}&part=${part}`;

  const partStatus = (p) => {
    const atts = progress.attempts(p.id);
    if (p.pending) return { cls: 'todo', label: 'Challenges being written', icon: 'clock' };
    if (atts.some((a) => a.allAnswered)) return { cls: 'done', label: `Submitted · ${atts.length} attempt${atts.length > 1 ? 's' : ''}`, icon: 'check-circle' };
    if (progress.draft(p.id)) return { cls: 'progress', label: t('c.inProgress'), icon: 'circle-dot' };
    return { cls: 'todo', label: t('c.notStarted'), icon: 'circle' };
  };

  const outline = (mod, currentId) => {
    const units = unitsFor(mod); const parts = partsFor(mod); const c = moduleCompletion(mod);
    const items = (group) => units.filter((u) => u.group === group).map((u) => {
      const done = progress.unitDone(u.id);
      return `<li><a href="${unitHref(mod.n, u.id)}" class="${done ? 'is-done' : ''}"${u.id === currentId ? ' aria-current="page"' : ''}>${icon(done ? 'check-circle' : KIND_ICON[u.kind])}<span>${esc(u.kind === 'reading' ? `${u.index + 1}. ${tc(u.title)}` : u.title)}<small>${done ? t('c.completed') : `${u.minutes} ${t('c.min')}`}</small></span></a></li>`;
    }).join('');
    const assess = parts.map((p) => {
      const s = partStatus(p);
      return `<li><a href="${partHref(mod.n, p.part)}" class="${s.cls === 'done' ? 'is-done' : ''}"${p.id === currentId ? ' aria-current="page"' : ''}>${icon(s.cls === 'done' ? 'check-circle' : KIND_ICON[p.part])}<span>${esc(p.title)}<small>${esc(s.label)}</small></span></a></li>`;
    }).join('');
    return `<nav class="outline" aria-label="${esc(t('unit.outline'))}" data-outline>
      <button class="outline-toggle" type="button" aria-expanded="false" data-outline-toggle>${esc(t('unit.outline'))} · ${c.pct}% ${icon('chevron')}</button>
      <div class="outline__body">
        <div class="outline__head"><div class="ring" style="--v:${c.pct};--c:var(--m)"><strong>${c.pct}%</strong></div><div><p class="muted" style="font-size:.8rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase">${esc(t('c.module'))} ${mod.n}</p><h2><a href="module.html?m=${mod.n}" style="text-decoration:none">${esc(tc(mod.title))}</a></h2></div></div>
        ${GROUPS.map(([g, key]) => { const html = g === 'assess' ? assess : items(g); return html ? `<div class="outline__group"><p>${esc(t(key))}</p><ul>${html}</ul></div>` : ''; }).join('')}
      </div></nav>`;
  };
  const wireOutline = (scope = document) => {
    const btn = scope.querySelector('[data-outline-toggle]');
    btn?.addEventListener('click', () => { const nav = btn.closest('[data-outline]'); const open = !nav.classList.contains('is-open'); nav.classList.toggle('is-open', open); btn.setAttribute('aria-expanded', String(open)); });
  };
  const sequence = (mod) => [...unitsFor(mod).map((u) => ({ id: u.id, href: unitHref(mod.n, u.id), title: u.kind === 'reading' ? tc(u.title) : u.title })), ...partsFor(mod).filter((p) => !p.pending).map((p) => ({ id: p.id, href: partHref(mod.n, p.part), title: p.title }))];
  const nextUnfinished = (catalog) => {
    for (const mod of catalog.filter((m) => m.kind === 'learning')) {
      for (const u of unitsFor(mod)) if (!progress.unitDone(u.id)) return { mod, href: unitHref(mod.n, u.id), title: u.kind === 'reading' ? tc(u.title) : u.title };
      for (const p of partsFor(mod)) if (!p.pending && !progress.attempts(p.id).some((a) => a.allAnswered)) return { mod, href: partHref(mod.n, p.part), title: p.title };
    }
    return null;
  };
  /* Architecture §10.2: final unlocked = pre-test submitted AND every counted part of every counted module
     submitted with all questions answered. Module 8 Part B is being rewritten, so it is treated as not counted yet. */
  const finalStatus = (catalog) => {
    const items = [];
    items.push({ done: !!progress.all().pretest || progress.attempts('pretest').length > 0, text: 'Take the pre-test (one short attempt)', href: 'assessment.html?part=pretest' });
    catalog.filter((m) => m.kind === 'learning' && m.counted).forEach((m) => partsFor(m).filter((p) => !p.pending).forEach((p) => {
      items.push({ done: progress.attempts(p.id).some((a) => a.allAnswered), text: `Module ${m.n} · ${p.title}: submit with every question answered`, href: partHref(m.n, p.part) });
    }));
    return { unlocked: items.every((i) => i.done), items, remaining: items.filter((i) => !i.done).length };
  };
  return { finalStatus, KIND_ICON, GROUPS, unitHref, partHref, partStatus, outline, wireOutline, sequence, nextUnfinished };
})();
