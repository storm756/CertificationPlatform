/* Learner pages: My progress (dashboard), Final exam, Certificate.
   "Live" uses this device's real activity (completion + submissions; scores need the server).
   Other scenarios use the worked example from architecture §10.3 as clearly labelled sample data. */
CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, params, progress, store, session, unitsFor, partsFor, moduleCompletion, requireRole } = CSFR;
  const C = window.CSFRCourse;
  if (!requireRole('learner')) return;
  const root = $('[data-learner-root]');
  const pageId = document.body.dataset.page;
  const user = session.get();
  const catalog = await CSFR.loadCatalog();
  const learning = catalog.filter((m) => m.kind === 'learning');

  const round1 = (x) => Math.round((x + Number.EPSILON) * 10) / 10;
  const grade = (x) => (x >= 90 ? 'A+' : x >= 80 ? 'A' : x >= 60 ? 'B' : x >= 50 ? 'C' : 'Not yet');
  const WORKED = [72.0, 55.0, 64.2, 68.7, 51.0, 66.0, 70.0, 58.0, 62.0];
  const SCENARIOS = { live: 'Your activity', new: 'New learner', midway: 'Mid-way', ready: 'Final ready', certified: 'Certified' };
  let scenario = params.get('scenario') || store.get('scenario', 'live');
  if (!SCENARIOS[scenario]) scenario = 'live';
  store.set('scenario', scenario);

  /* ---------- View model ---------- */
  const build = () => {
    const sample = scenario !== 'live';
    const mods = learning.map((m, i) => {
      const comp = moduleCompletion(m);
      const base = { n: m.n, title: m.title, comp, parts: partsFor(m) };
      if (!sample) {
        const parts = base.parts.map((p) => ({ ...p, submitted: progress.attempts(p.id).some((a) => a.allAnswered), best: null }));
        return { ...base, parts, pct: null, state: comp.pct >= 100 ? 'done' : comp.pct > 0 ? 'progress' : 'todo' };
      }
      let score = null, mcq = null, int = null;
      const has = scenario === 'ready' || scenario === 'certified' || (scenario === 'midway' && i < 4);
      if (has) { score = WORKED[i]; mcq = i === 3 ? 73.3 : round1(score + 3); int = i === 3 ? 64.0 : round1(score - 3); }
      if (scenario === 'midway' && i === 4) { mcq = 58.0; }
      if (scenario === 'midway' && i === 5) { score = 44.0; mcq = 52.0; int = 36.0; }
      const parts = base.parts.map((p) => ({ ...p, submitted: p.part === 'mcq' ? mcq !== null : int !== null, best: p.part === 'mcq' ? mcq : int }));
      const pctDone = score !== null ? 100 : mcq !== null ? 55 : 0;
      return { ...base, comp: { ...comp, pct: pctDone }, parts, pct: score, state: score !== null ? 'done' : mcq !== null ? 'progress' : 'todo' };
    });
    const pretest = sample ? scenario !== 'new' : (!!progress.all().pretest || progress.attempts('pretest').length > 0);
    let blockers;
    if (sample) {
      const items = [{ done: pretest, text: 'Take the pre-test (one short attempt)', href: 'assessment.html?part=pretest' }];
      mods.forEach((m) => m.parts.filter((p) => !p.pending).forEach((p) => items.push({ done: p.submitted, text: `Module ${m.n} · ${p.title}: submit with every question answered`, href: C.partHref(m.n, p.part) })));
      blockers = { unlocked: items.every((x) => x.done), items, remaining: items.filter((x) => !x.done).length };
    } else blockers = C.finalStatus(catalog);
    const finalBest = scenario === 'certified' ? 61.0 : null;
    const finalAttempts = sample ? (scenario === 'certified' ? 2 : 0) : progress.attempts('final').length;
    const finalState = !blockers.unlocked ? 'locked' : finalBest !== null || finalAttempts ? 'completed' : progress.draft('final') ? 'inprogress' : 'ready';
    const scored = mods.filter((m) => m.pct !== null);
    const modMean = scored.length === 9 ? scored.reduce((s, m) => s + m.pct, 0) / 9 : null;
    const overall = modMean !== null && finalBest !== null ? round1(0.5 * modMean + 0.5 * finalBest) : null;
    const below = mods.filter((m) => m.pct !== null && m.pct < 50);
    const completion = Math.round(mods.reduce((s, m) => s + m.comp.pct, 0) / mods.length);
    const doneMinutes = learning.reduce((s, m) => s + unitsFor(m).filter((u) => progress.unitDone(u.id)).reduce((a, u) => a + u.minutes, 0), 0);
    const hours = sample ? { new: 0, midway: 7.5, ready: 13.5, certified: 15 }[scenario] : round1(doneMinutes / 60);
    const cert = scenario === 'certified' ? (store.get('certState', 'issued')) : 'unavailable';
    return { sample, mods, pretest, blockers, finalBest, finalAttempts, finalState, overall, grade: overall !== null ? grade(overall) : null, modMean, below, completion, hours, cert };
  };
  let vm = build();

  const scenarioBar = () => `<div class="scenario" role="group" aria-label="Preview scenario"><span class="badge badge--muted">${icon('eye', 'icon--sm')}${esc(t('c.demo'))}</span><span>Show:</span>
    <div class="seg">${Object.entries(SCENARIOS).map(([k, v]) => `<button type="button" data-scn="${k}" aria-pressed="${k === scenario}">${esc(v)}</button>`).join('')}</div>
    ${vm.sample ? `<span class="muted" style="font-size:.85rem">Scores are sample data (architecture §10.3).</span>` : `<span class="muted" style="font-size:.85rem">Real activity on this device. Scores need the server.</span>`}</div>`;
  const wireScenario = () => $$('[data-scn]').forEach((b) => b.addEventListener('click', () => { scenario = b.dataset.scn; store.set('scenario', scenario); vm = build(); render(); }));
  const pct = (x) => (x === null || x === undefined ? '—' : `${x.toFixed(1)}%`);
  const modTitle = (n) => tc(catalog.find((m) => m.n === n).title);

  /* ---------- Shared cards ---------- */
  const finalCard = () => {
    const s = vm.finalState;
    const map = {
      locked: ['lock', 'var(--ink-soft)', 'Final exam · locked', `${vm.blockers.remaining} step${vm.blockers.remaining === 1 ? '' : 's'} remain before your final unlocks.`, ['final.html', 'See what’s left']],
      ready: ['unlock', 'var(--teal)', 'You’re ready for the final assessment', 'About 60 minutes, 50 questions from every module. Attempts are unlimited.', ['final.html', 'Get ready']],
      inprogress: ['clock', 'var(--mustard-deep)', 'Final in progress', 'Your answers are saved. Resume on any device.', ['assessment.html?part=final', 'Resume the final']],
      completed: ['check-circle', 'var(--teal)', `Final · best ${pct(vm.finalBest)}`, 'See how you did in each module, or try again to improve.', ['final.html', 'View result']],
    }[s];
    return `<article class="card card--edge" style="--m:${map[1]}"><div class="row" style="gap:.6rem;margin-bottom:.5rem">${icon(map[0])}<h3 style="margin:0">${esc(map[2])}</h3></div><p class="muted">${esc(map[3])}</p><a class="btn ${s === 'locked' ? 'btn-outline' : 'btn-primary'} btn-sm" style="margin-top:.9rem" href="${map[4][0]}">${esc(map[4][1])} ${icon('arrow', 'icon-arrow')}</a></article>`;
  };
  const blockersCard = (limit = 6) => {
    if (vm.blockers.unlocked) return '';
    const items = [...vm.blockers.items.filter((i) => !i.done)];
    const doneCount = vm.blockers.items.length - items.length;
    const scoreBlock = vm.below.map((m) => `<li>${icon('alert')}<span><strong>Module ${m.n} is at ${m.pct.toFixed(1)}%.</strong> Your best MCQ is ${m.parts[0].best}%, your best Interactive is ${m.parts[1].best}%. <a class="link" href="module.html?m=${m.n}#assess">Retake</a></span></li>`).join('');
    return `<article class="card"><h3>${esc(t('dash.blockers'))}</h3><p class="muted" style="margin-bottom:.9rem">${doneCount} done · ${items.length} to go. Each one is something you can do now.</p>
      <ul class="blockers">${scoreBlock}${items.slice(0, limit).map((i) => `<li>${icon('circle')}<a class="link" href="${i.href}" style="font-weight:500">${esc(i.text)}</a></li>`).join('')}${items.length > limit ? `<li class="is-done">${icon('plus')}<span>${items.length - limit} more. <a class="link" href="final.html">See all</a></span></li>` : ''}
      ${vm.blockers.items.filter((i) => i.done).slice(0, 2).map((i) => `<li class="is-done">${icon('check-circle')}<span>${esc(i.text)}</span></li>`).join('')}</ul></article>`;
  };
  const certCard = () => {
    const s = vm.cert;
    const m = {
      unavailable: ['award', 'Certificate · not yet', 'Pass every module and the final with 50% or more to become eligible.', 'certificate.html', 'How it works'],
      awaiting: ['clock', 'Awaiting mentor approval', 'You’re eligible. Your mentor approves certificates for your batch.', 'certificate.html', 'View status'],
      issued: ['award', 'Certificate issued', 'Download it from the site. Anyone can check it with the QR code.', 'certificate.html', 'View and download'],
      revoked: ['x', 'Certificate revoked', 'Contact the programme team if you have questions.', 'certificate.html', 'Details'],
    }[s];
    return `<article class="card card--edge" style="--m:var(--mustard)"><div class="row" style="gap:.6rem;margin-bottom:.5rem">${icon(m[0])}<h3 style="margin:0">${esc(m[1])}</h3></div><p class="muted">${esc(m[2])}</p><a class="btn btn-outline btn-sm" style="margin-top:.9rem" href="${m[3]}">${esc(m[4])}</a></article>`;
  };

  /* ---------- Dashboard ---------- */
  const dashboard = async () => {
    const next = C.nextUnfinished(catalog);
    const firstName = user.name.split(' ')[0].replace(/^./, (c) => c.toUpperCase());
    let headline, sub, cta;
    if (scenario === 'certified') { headline = `Congratulations, ${firstName}!`; sub = 'You’re a certified Community Cyber First Responder.'; cta = ['certificate.html', 'Download your certificate']; }
    else if (vm.finalState === 'ready') { headline = 'You’re ready for the final assessment'; sub = 'Every module part is submitted. Take the final when you’re ready.'; cta = ['final.html', 'Go to the final']; }
    else if (!vm.pretest && (scenario === 'new' || (scenario === 'live' && !next?.mod?.n))) { headline = `Welcome, ${firstName}`; sub = 'Start with a short pre-test, then open Module 1. Nothing is locked.'; cta = ['module.html?m=1', 'Start Module 1']; }
    else if (scenario === 'midway') { headline = `${t('dash.welcome')}, ${firstName}`; sub = 'Module 5 is half done. Part B is next.'; cta = ['assessment.html?m=5&part=int', t('dash.continue')]; }
    else { headline = `${t('dash.welcome')}, ${firstName}`; sub = next ? `Next: ${next.title} (Module ${next.mod.n})` : 'Everything here is done.'; cta = [next ? next.href : 'final.html', next ? t('dash.continue') : 'Go to the final']; }
    if (params.get('welcome') && scenario === 'live') { headline = `Welcome, ${firstName}`; sub = 'Your account is ready. A short pre-test comes first, then dive into Module 1.'; }

    const ringV = vm.overall ?? vm.completion;
    const journey = [
      ['target', 'Pre-test', vm.pretest ? 'Done' : 'One short attempt', vm.pretest ? 'done' : 'current'],
      ['layers', 'Modules', `${vm.mods.filter((m) => m.state === 'done').length} of 9 complete`, vm.blockers.items.slice(1).every((i) => i.done) ? 'done' : vm.pretest ? 'current' : ''],
      ['retry', 'Practice mock', 'Optional, before the final', ''],
      ['flag', 'Final exam', { locked: 'Locked', ready: 'Unlocked', inprogress: 'In progress', completed: `Best ${pct(vm.finalBest)}` }[vm.finalState], vm.finalState === 'completed' ? 'done' : vm.finalState === 'locked' ? 'locked' : 'current'],
      ['award', 'Certificate', vm.cert === 'issued' ? 'Issued' : 'Not yet', vm.cert === 'issued' ? 'done' : 'locked'],
    ];
    const weakest = vm.mods.filter((m) => m.pct !== null).sort((a, b) => a.pct - b.pct).slice(0, 2);
    const weakMods = await Promise.all(weakest.map((m) => CSFR.loadModule(m.n)));
    const modRow = (m) => {
      const status = m.pct !== null ? (m.pct >= 50 ? ['done', 'check-circle', `${t('c.passed')} · ${m.pct.toFixed(1)}%`] : ['progress', 'retry', `${t('c.notYet')} · ${m.pct.toFixed(1)}%`]) : m.state === 'progress' ? ['progress', 'circle-dot', t('c.inProgress')] : m.state === 'done' ? ['done', 'check-circle', `${t('c.completed')} · score pending`] : ['todo', 'circle', t('c.notStarted')];
      return `<article class="card card-link" data-mod="${m.n}" style="border-left:6px solid var(--m)">
        <div class="row" style="justify-content:space-between;align-items:flex-start"><div><p class="muted" style="font-size:.8rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase">${esc(t('c.module'))} ${m.n}</p><h3><a href="module.html?m=${m.n}" style="text-decoration:none">${esc(modTitle(m.n))}</a></h3></div><span class="status status--${status[0]}">${icon(status[1])}${esc(status[2])}</span></div>
        <div class="bar" style="--v:${m.comp.pct};margin:.75rem 0" role="img" aria-label="${m.comp.pct}% complete"><i></i></div>
        <div class="row" style="justify-content:space-between;font-size:.92rem">${m.parts.map((p) => `<span>${esc(p.part === 'mcq' ? 'Part A' : 'Part B')}: <strong>${p.pending ? 'pending content' : p.best !== null ? `${p.best}%` : p.submitted ? 'submitted' : '—'}</strong></span>`).join('')}
        <a class="btn btn-sm ${m.pct !== null && m.pct < 50 ? 'btn-accent' : 'btn-ghost'}" href="${m.pct !== null && m.pct < 50 ? `module.html?m=${m.n}#assess` : `module.html?m=${m.n}`}">${m.pct !== null && m.pct < 50 ? t('c.retake') : m.state === 'todo' ? t('c.start') : t('c.continue')}</a></div></article>`;
    };
    root.innerHTML = `
      <section class="band on-dark"><div class="shell"><div class="dash-hero">
        <div><p class="eyebrow eyebrow--cyan">${esc(t('nav.progress'))}</p><h1>${esc(headline)}</h1><p class="lede">${esc(sub)}</p>
          <div class="row" style="margin-top:1.5rem"><a class="btn btn-accent btn-lg" href="${cta[0]}">${esc(cta[1])} ${icon('arrow', 'icon-arrow')}</a>${!vm.pretest ? '<a class="btn btn-ghost-dark" href="assessment.html?part=pretest">Take the pre-test</a>' : ''}</div></div>
        <div class="ring" style="--v:${ringV}" role="img" aria-label="${vm.overall !== null ? `Overall ${vm.overall}%, grade ${vm.grade}` : `${vm.completion}% of the programme complete`}"><div><strong style="color:#fff">${vm.overall !== null ? vm.overall.toFixed(1) : vm.completion}%</strong><small>${vm.overall !== null ? `Overall · Grade ${vm.grade}` : esc(t('dash.overall'))}</small></div></div>
      </div></div></section>
      <div class="shell section stack-lg">
        ${scenarioBar()}
        ${!vm.pretest ? `<div class="notice notice--plum">${icon('target')}<div><h2 style="font-size:1.2rem">Before you begin: a short pre-test</h2><p>It shows where you’re starting from, so the programme can measure what you learn. You get one attempt, which you can pause and resume. You can postpone it, but the final stays locked until it’s done.</p><div class="row" style="margin-top:.75rem"><a class="btn btn-primary btn-sm" href="assessment.html?part=pretest">Take it now</a><button class="btn btn-ghost btn-sm" type="button" data-later>Remind me later</button></div></div></div>` : ''}
        <section aria-labelledby="j-title"><div class="section-title"><h2 id="j-title">${esc(t('dash.journey'))}</h2></div>
          <ol class="journey-map">${journey.map(([ic, ti, sm, s]) => `<li class="journey-step ${s ? `is-${s}` : ''}">${icon(s === 'done' ? 'check-circle' : s === 'locked' ? 'lock' : ic)}<strong>${esc(ti)}</strong><small>${esc(sm)}</small></li>`).join('')}</ol></section>
        <div class="dash-grid">
          <section aria-labelledby="m-title"><div class="section-title"><h2 id="m-title">${esc(t('dash.modules'))}</h2><a class="link" href="modules.html">All modules</a></div><div class="stack">${vm.mods.map(modRow).join('')}</div></section>
          <div class="stack">
            ${finalCard()}${blockersCard()}${certCard()}
            ${weakest.length ? `<article class="card"><h3>${esc(t('dash.weakest'))}</h3><p class="muted" style="margin-bottom:.75rem">Based on your lowest module scores.</p><ul class="stack" style="gap:.75rem">${weakest.map((m, i) => `<li><strong>Module ${m.n}</strong> · ${esc(modTitle(m.n))}<br><span class="muted" style="font-size:.95rem">${esc(weakMods[i].interactive.revise || '')}</span></li>`).join('')}</ul></article>` : ''}
            <article class="card"><h3>Study time</h3><p class="kpi"><strong>${vm.hours} h</strong><span>${user.minor ? 'Counted from the units you’ve completed (no time tracking for under-18s)' : 'Engaged time (estimated)'}</span></p></article>
          </div>
        </div>
      </div>`;
    $('[data-later]')?.addEventListener('click', (e) => { e.target.closest('.notice').hidden = true; CSFR.toast('We’ll remind you next time. The final stays locked until the pre-test is done.'); });
    wireScenario();
  };

  /* ---------- Final page ---------- */
  const finalPage = () => {
    const s = vm.finalState;
    const bands = ['Strong', 'OK', 'Strong', 'Needs work', 'OK', 'Strong', 'OK', 'Needs work', 'Strong'];
    root.innerHTML = `
      <section class="band on-dark"><div class="shell"><nav class="crumbs" aria-label="Breadcrumb"><a href="dashboard.html">${esc(t('nav.progress'))}</a>${icon('chevron-right')}<span aria-current="page">${esc(t('nav.final'))}</span></nav>
        <p class="eyebrow eyebrow--cyan">Final exam · Modules 1–9</p><h1>${{ locked: 'Your final is almost within reach', ready: 'You’re ready for the final assessment', inprogress: 'Your final is in progress', completed: 'Your final result' }[s]}</h1>
        <p class="lede">${{ locked: `${vm.blockers.remaining} step${vm.blockers.remaining === 1 ? '' : 's'} remain before your final unlocks. Here’s exactly what’s done and what’s left.`, ready: 'Everything is in place. Read how it works, then start when you have about an hour.', inprogress: 'Your answers are saved. Pick up where you left off.', completed: 'Your best attempt counts. You can try again to improve it.' }[s]}</p></div></section>
      <div class="shell section stack-lg" style="max-width:64rem">
        ${scenarioBar()}
        <div class="grid-2">
          <article class="part-card" style="--m:var(--plum)"><div class="part-card__head"><div><p class="eyebrow" style="margin-bottom:.3rem">Step 1</p><h2 style="font-size:1.4rem">Pre-test</h2></div><span class="status status--${vm.pretest ? 'done' : 'todo'}">${icon(vm.pretest ? 'check-circle' : 'circle')}${vm.pretest ? t('c.completed') : t('c.notStarted')}</span></div>
            <p class="muted">A short set of questions taken once, before you learn much, so the programme can measure your progress. You see your score only.</p>
            ${vm.pretest ? '' : `<a class="btn btn-primary" href="assessment.html?part=pretest">${icon('target')}Take the pre-test</a>`}</article>
          <article class="part-card" style="--m:var(--teal)"><div class="part-card__head"><div><p class="eyebrow" style="margin-bottom:.3rem">Step 2</p><h2 style="font-size:1.4rem">Final exam</h2></div><span class="status status--${s === 'locked' ? 'locked' : s === 'completed' ? 'done' : 'progress'}">${icon(s === 'locked' ? 'lock' : s === 'completed' ? 'check-circle' : 'unlock')}${{ locked: t('c.locked'), ready: t('c.ready'), inprogress: t('c.inProgress'), completed: `Best ${pct(vm.finalBest)}` }[s]}</span></div>
            <dl><div><dt>Questions</dt><dd>50, from all 9 modules</dd></div><div><dt>Time</dt><dd>About 60 min (a guide)</dd></div><div><dt>Attempts</dt><dd>Unlimited · best counts</dd></div><div><dt>Weight</dt><dd>50% of your result</dd></div></dl>
            ${s === 'locked' ? `<button class="btn btn-outline" type="button" aria-disabled="true" disabled>${icon('lock')}Unlocks when every step is done</button>` : `<a class="btn btn-accent" href="assessment.html?part=final">${icon(s === 'inprogress' ? 'retry' : 'arrow')}${s === 'inprogress' ? 'Resume the final' : s === 'completed' ? 'Try again' : 'Start the final'}</a>`}</article>
        </div>
        ${s === 'locked' ? `<section class="card"><h2 style="font-size:1.4rem;margin-bottom:.4rem">What unlocks the final</h2><p class="muted" style="margin-bottom:1rem">The pre-test, plus every counted part of every module submitted with all questions answered. Your scores don’t need to be above 50% yet. That matters for the certificate.</p>
          <ul class="blockers">${vm.blockers.items.map((i) => `<li class="${i.done ? 'is-done' : ''}">${icon(i.done ? 'check-circle' : 'circle')}${i.done ? `<span>${esc(i.text)}</span>` : `<a class="link" href="${i.href}" style="font-weight:500">${esc(i.text)}</a>`}</li>`).join('')}</ul>
          <p class="muted" style="margin-top:1rem;font-size:.92rem">${icon('info', 'icon--sm')} Module 8’s interactive part is being rewritten, so it isn’t required yet.</p></section>` : ''}
        ${s === 'ready' || s === 'inprogress' ? `<section class="card stack"><h2 style="font-size:1.4rem">Before you start</h2><ul class="ticks"><li>${icon('layers')} Each learner gets their own draw of questions, in a shuffled order.</li><li>${icon('save')} Answers save as you go. You can resume on any device.</li><li>${icon('chart')} Afterwards you’ll see your overall score and a band for each module: Strong, OK or Needs work.</li><li>${icon('retry')} Not happy with it? Attempts are unlimited and your best counts.</li></ul><a class="btn btn-ghost" href="assessment.html?part=mock">${icon('retry')}Warm up with the practice mock first</a></section>` : ''}
        ${s === 'completed' ? `<section class="result-hero" style="--c:var(--teal)"><div class="ring" style="--v:${vm.finalBest}"><div><strong>${pct(vm.finalBest)}</strong><small>Best final</small></div></div><div class="stack"><h2 style="font-size:1.8rem">Overall ${pct(vm.overall)} · Grade ${esc(vm.grade || '—')}</h2><p class="muted">Overall = 50% of your nine module scores (${pct(vm.modMean && round1(vm.modMean))}) + 50% of your best final. ${vm.overall >= 50 ? 'You’re eligible for your certificate.' : ''}</p><a class="btn btn-primary" href="certificate.html">${icon('award')}Go to your certificate</a></div></section>
          <section><h2 style="font-size:1.4rem;margin-bottom:1rem">How you did in each module</h2><div class="result-list">${learning.map((m, i) => `<div class="result-item"><span>${icon(bands[i] === 'Strong' ? 'trend' : bands[i] === 'OK' ? 'minus' : 'retry')}</span><span>${esc(tc(m.title))}</span><span class="badge ${bands[i] === 'Strong' ? 'badge--teal' : bands[i] === 'OK' ? 'badge--mustard' : 'badge--terracotta'}">${bands[i]}</span></div>`).join('')}</div><p class="muted" style="margin-top:.75rem;font-size:.92rem">Bands, not exact percentages, so the final stays fair for everyone.</p></section>` : ''}
      </div>`;
    wireScenario();
  };

  /* ---------- Certificate page ---------- */
  const certPage = () => {
    const states = vm.cert === 'unavailable' ? ['unavailable'] : ['awaiting', 'issued', 'revoked'];
    const s = vm.cert;
    const name = (store.get('account', null)?.name || user.name).toUpperCase();
    root.innerHTML = `
      <section class="band on-dark"><div class="shell"><p class="eyebrow eyebrow--cyan">${esc(t('nav.certificate'))}</p><h1>${{ unavailable: 'Your certificate', awaiting: 'Waiting for mentor approval', issued: 'Your certificate is ready', revoked: 'Certificate revoked' }[s]}</h1>
        <p class="lede">${{ unavailable: 'Pass every module and the final with 50% or more and your certificate appears here.', awaiting: 'You’re eligible. Your mentor approves certificates for your batch, so you’ll see it here soon.', issued: 'Download it securely from this page. It is never sent by email.', revoked: 'This certificate is no longer valid.' }[s]}</p></div></section>
      <div class="shell section stack-lg" style="max-width:64rem">
        ${scenarioBar()}
        ${states.length > 1 ? `<div class="scenario"><span class="badge badge--muted">${esc(t('c.sample'))}</span><span>Certificate state:</span><div class="seg">${states.map((k) => `<button type="button" data-cst="${k}" aria-pressed="${k === s}">${{ awaiting: 'Awaiting approval', issued: 'Issued', revoked: 'Revoked' }[k]}</button>`).join('')}</div></div>` : ''}
        ${s === 'unavailable' ? `<div class="grid-2"><div class="card stack"><h2 style="font-size:1.4rem">How to become eligible</h2><ul class="ticks"><li>${icon('check-circle')} Verify your email${user.minor ? ' and get guardian consent' : ''}</li><li>${icon('check-circle')} Score 50% or more in every one of the nine modules</li><li>${icon('check-circle')} Score 50% or more in the final exam</li></ul><a class="btn btn-primary" href="dashboard.html">See your progress</a></div>
          <figure class="cert-thumb" style="margin:0"><img src="assets/certificate/cert-front.jpg" alt="The approved certificate design (sample)" loading="lazy" width="1600" height="1131"></figure></div>` : ''}
        ${s === 'awaiting' ? `<div class="state-panel" style="--c:var(--mustard-deep)"><span class="big-icon">${icon('clock')}</span><h2 style="font-size:1.6rem">You’re eligible</h2><p class="muted">Overall ${pct(vm.overall)} · Grade ${esc(vm.grade)}. Your mentor will approve your certificate. There is nothing more you need to do.</p></div>` : ''}
        ${s === 'issued' ? `<div class="grid-2" style="align-items:start"><figure class="cert-thumb" style="margin:0"><img src="assets/certificate/cert-front.jpg" alt="Certificate front (approved design, sample)" width="1600" height="1131"></figure>
          <div class="stack"><dl class="part-card" style="margin:0"><div><dt>Name</dt><dd>${esc(name)}</dd></div><div><dt>Qualification</dt><dd>Community Cyber First Responder</dd></div><div><dt>Grade</dt><dd>${esc(vm.grade)}</dd></div><div><dt>Certificate no.</dt><dd>000123 <span class="badge badge--muted">${esc(t('c.sample'))}</span></dd></div><div><dt>Issued</dt><dd>12 March 2027</dd></div></dl>
            <button class="btn btn-accent btn-lg" type="button" data-demo="In the live platform this downloads your PDF certificate securely.">${icon('download')}Download PDF</button>
            <a class="btn btn-outline" href="verify.html?code=K7QM2XR9TD">${icon('qr')}Open the public verification page</a>
            <p class="muted" style="font-size:.9rem">NSQF level and credits shown after approval by the competent authority.</p></div></div>` : ''}
        ${s === 'revoked' ? `<div class="state-panel" style="--c:var(--danger)"><span class="big-icon">${icon('x')}</span><h2 style="font-size:1.6rem">This certificate has been revoked</h2><p class="muted">The public verification page now shows it as revoked. If you think this is a mistake, contact the programme team through the <a class="link" href="grievance.html">grievance contact</a>.</p></div>` : ''}
      </div>`;
    wireScenario();
    $$('[data-cst]').forEach((b) => b.addEventListener('click', () => { store.set('certState', b.dataset.cst); vm = build(); render(); }));
  };

  const render = () => ({ dashboard, final: finalPage, certificate: certPage }[pageId])();
  await render();
});
