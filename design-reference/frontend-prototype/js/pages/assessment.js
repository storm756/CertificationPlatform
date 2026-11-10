/* Intro → attempt (autosave, palette, flags) → review → confirm → result.
   The browser never scores: result screens show the layout with clearly labelled sample numbers. */
CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, params, progress, store, lang, toast, confirmDialog } = CSFR;
  const C = window.CSFRCourse, E = window.CSFREngine;
  const root = $('[data-as-root]');
  const part = params.get('part') || 'mcq';
  const n = Number(params.get('m')) || null;
  const catalog = await CSFR.loadCatalog();

  /* ---------- Build the assessment definition ---------- */
  const seeded = (seed) => { let s = 0; for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; }; };
  const shuffle = (arr, rnd) => { const a = [...arr]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const drawMcq = (pool, k, rnd) => {
    const byPc = {}; pool.forEach((q) => (byPc[q.pc] = byPc[q.pc] || []).push(q));
    const pick = []; Object.values(byPc).forEach((list) => pick.push(...shuffle(list, rnd).slice(0, 2)));
    const rest = shuffle(pool.filter((q) => !pick.includes(q)), rnd);
    return shuffle([...pick, ...rest].slice(0, k), rnd);
  };

  let def;
  if (part === 'mcq' || part === 'int') {
    const cat = catalog.find((m) => m.n === n && m.kind === 'learning');
    if (!cat) { location.replace('modules.html'); return; }
    const mod = await CSFR.loadModule(n);
    if (part === 'int' && cat.interactivePracticeOnly) { location.replace(`module.html?m=${n}#assess`); return; }
    def = part === 'mcq'
      ? { id: `m${n}:mcq`, mod: n, kicker: `${t('c.module')} ${n} · ${t('mod.partA')}`, title: tc(cat.title), marks: 50, counted: true, timer: 'up', pool: mod.mcq, draw: 15, about: null, back: `module.html?m=${n}#assess` }
      : { id: `m${n}:int`, mod: n, kicker: `${t('c.module')} ${n} · ${t('mod.partB')}`, title: mod.interactive.gameTitle || tc(cat.title), story: mod.interactive.story, marks: 50, counted: true, timer: 'about', about: mod.interactive.minutes, questions: mod.interactive.questions, back: `module.html?m=${n}#assess`, revise: mod.interactive.revise };
  } else if (part === 'mock') {
    await CSFR.loadScript('data/mock.js');
    const m = window.CSFR_MOCK;
    def = { id: 'mock', kicker: 'Practice mock · not graded', title: m.title, story: m.tagline, counted: false, timer: 'about', about: m.minutes, questions: m.questions, back: 'modules.html', practice: true };
  } else if (part === 'pretest' || part === 'final') {
    const mods = await Promise.all(catalog.filter((m) => m.kind === 'learning').map((m) => CSFR.loadModule(m.n)));
    const rnd = seeded(`${part}-${new Date().toDateString()}`);
    const sample = part === 'pretest'
      ? mods.map((m) => shuffle(m.practice, rnd)[0])
      : mods.flatMap((m) => shuffle(m.practice, rnd).slice(0, 2));
    if (part === 'final') {
      const scenario = store.get('scenario', 'live');
      const unlocked = ['ready', 'certified'].includes(scenario) || C.finalStatus(catalog).unlocked;
      if (!unlocked && !params.get('preview')) { location.replace('final.html'); return; }
    }
    def = part === 'pretest'
      ? { id: 'pretest', kicker: 'Pre-test · one attempt', title: 'Where are you starting from?', counted: false, timer: 'up', questions: sample.map((q) => ({ ...q, type: 'mcq' })), back: 'final.html', pretest: true }
      : { id: 'final', kicker: 'Final exam', title: 'Final assessment · Modules 1–9', counted: true, timer: 'about', about: 60, questions: sample.map((q) => ({ ...q, type: 'mcq' })), back: 'final.html', final: true };
    def.previewNote = part === 'final' ? 'Preview: the real final draws 50 new questions (6/6/5/6/6/6/5/5/5 per module) from a separate final pool, which is not in this build. Practice questions stand in here.' : 'Preview: the real pre-test uses the programme’s anchor questions. Practice questions stand in here.';
  } else { location.replace('modules.html'); return; }
  if (def.mod) root.dataset.mod = String(def.mod);
  document.title = `${def.kicker} · CSFR`;

  /* ---------- Attempt state (autosaved as tokens) ---------- */
  const draftKey = def.id;
  const pastAttempts = progress.attempts(def.id);
  const pretestDone = def.pretest && pastAttempts.length > 0;
  const newAttempt = () => {
    const rnd = seeded(`${def.id}-${Date.now()}`);
    const qs = def.pool ? drawMcq(def.pool, def.draw, rnd).map((q) => ({ ...q, type: 'mcq' })) : def.questions;
    return { questions: qs, answers: {}, flags: {}, current: 0, started: Date.now() };
  };
  let st = progress.draft(draftKey);

  /* ---------- Intro ---------- */
  const intro = () => {
    const count = def.pool ? def.draw : def.questions.length;
    const rows = [
      ['Questions', def.pool ? `${count}, drawn from a pool of ${def.pool.length}` : `${count} ${def.questions[0]?.type === 'mcq' ? t('c.questions') : t('c.challenges')}`],
      ['Marks', def.marks ? `${def.marks} of the module’s 100` : def.final ? '50% of your overall result' : 'Not counted'],
      ['Time', def.timer === 'about' ? `about ${def.about} ${t('c.min')}. A guide, not a limit` : 'Count-up only. Take your time'],
      ['Attempts', def.pretest ? 'One attempt (you can resume it)' : 'Unlimited. Your best attempt counts'],
      ['Pass mark', def.counted ? '50%' : '—'],
    ];
    root.innerHTML = `
      <section class="band ${def.mod ? 'band--mod' : ''}"><div class="shell">
        <nav class="crumbs" aria-label="Breadcrumb"><a href="${def.back.split('#')[0]}">${esc(def.mod ? `${t('c.module')} ${def.mod}` : def.practice ? t('nav.modules') : t('nav.final'))}</a>${icon('chevron-right')}<span aria-current="page">${esc(def.kicker)}</span></nav>
        <p class="eyebrow eyebrow--cyan">${esc(def.kicker)}</p><h1>${esc(def.title)}</h1>${def.story ? `<p class="lede">${esc(def.story)}</p>` : ''}
      </div></section>
      <div class="shell section" style="max-width:56rem">
        <div class="stack-lg">
          ${def.previewNote ? `<div class="notice notice--mustard">${icon('info')}<p>${esc(def.previewNote)}</p></div>` : ''}
          <div class="part-card"><dl>${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></div>
          <ul class="ticks">
            <li>${icon('save')} Every answer saves to your account as you go. If you close the page, you can resume on any device.</li>
            ${def.counted ? `<li>${icon('check-circle')} <strong>Answer every question.</strong> A submission only counts towards unlocking the final when nothing is left blank.</li>` : ''}
            ${def.final ? `<li>${icon('chart')} After the final you see your overall score and a band for each module (Strong, OK or Needs work). Answers are not shown.</li>` : def.pretest ? `<li>${icon('target')} You’ll see your score only. This helps measure how much the programme teaches.</li>` : `<li>${icon('lightbulb')} Afterwards you see your score, which questions to revisit and a hint for each, but never the correct option.</li>`}
            <li>${icon('globe')} <span>You can switch language at any time without losing answers.</span>${lang !== 'en' ? ` <span>${esc(t('lang.assessEnglish'))}</span>` : ''}</li>
          </ul>
          ${pastAttempts.length ? `<p class="demo-note">${icon('retry', 'icon--sm')}You’ve submitted ${pastAttempts.length} attempt${pastAttempts.length > 1 ? 's' : ''}. ${def.counted ? 'Your best one counts.' : ''}</p>` : ''}
          ${pretestDone ? `<div class="notice notice--teal">${icon('check-circle')}<p>You’ve completed the pre-test. It can only be taken once.</p></div><a class="btn btn-primary" href="final.html">${esc(t('c.back'))}</a>`
            : `<div class="row"><button class="btn btn-accent btn-lg" type="button" data-begin>${st ? `${icon('retry')}Resume where you left off` : `${icon('arrow')}${def.pretest ? 'Start the pre-test' : pastAttempts.length ? t('c.retake') : 'Start'}`}</button>
               ${st ? '<button class="btn btn-ghost" type="button" data-restart>Start a fresh attempt</button>' : ''}${def.pretest ? '<a class="btn btn-ghost" href="dashboard.html">Remind me later</a>' : ''}</div>`}
        </div>
      </div>`;
    $('[data-begin]')?.addEventListener('click', () => { if (!st) { st = newAttempt(); progress.saveDraft(draftKey, st); } attempt(); });
    $('[data-restart]')?.addEventListener('click', async () => { if (await confirmDialog({ title: 'Start a fresh attempt?', body: 'Your saved answers for this attempt will be cleared.', confirm: 'Start fresh', danger: true })) { progress.clearDraft(draftKey); st = newAttempt(); progress.saveDraft(draftKey, st); attempt(); } });
  };

  /* ---------- Attempt ---------- */
  let tick;
  const answeredCount = () => st.questions.filter((q, i) => E.isAnswered(q, st.answers[i])).length;
  const attempt = () => {
    const total = st.questions.length;
    root.innerHTML = `
      <div class="attempt-bar"><div class="shell attempt-bar__inner">
        <div class="attempt-bar__title"><strong>${esc(def.kicker)}</strong><small data-qpos></small></div>
        <span class="timer" data-timer>${icon('clock')}<span></span></span>
        <span class="save-pill" role="status" data-save data-state="saved">${icon('check', 'icon--sm')}<span>${esc(t('as.saved'))}</span></span>
        <button class="btn btn-sm btn-outline" type="button" data-to-review>${esc(t('as.review'))}</button>
      </div><div class="attempt-progress"><i data-progress></i></div></div>
      <div class="shell attempt">
        <div>
          ${def.previewNote ? `<p class="demo-note" style="margin-bottom:1rem">${icon('info', 'icon--sm')}Preview questions</p>` : ''}
          <section class="qcard" aria-live="polite" aria-atomic="false" data-qcard></section>
          <div class="qnav">
            <button class="btn btn-ghost" type="button" data-prev>${icon('arrow-left')}${esc(t('c.previous'))}</button>
            <button class="btn btn-ghost" type="button" data-flag aria-pressed="false">${icon('flag')}<span>${esc(t('as.flag'))}</span></button>
            <button class="btn btn-primary" type="button" data-next>${esc(t('c.next'))} ${icon('arrow', 'icon-arrow')}</button>
          </div>
        </div>
        <aside class="palette" aria-label="Question navigator"><h2>${total} ${def.questions?.[0]?.type === 'mcq' || def.pool ? t('c.questions') : t('c.challenges')}</h2>
          <div class="palette__grid" data-palette>${st.questions.map((_, i) => `<button type="button" data-go="${i}" aria-label="${esc(t('as.question'))} ${i + 1}">${i + 1}</button>`).join('')}</div>
          <div class="palette__legend"><span><i class="a"></i>Answered</span><span><i></i>Not answered</span><span><i class="f"></i>Marked for review</span></div>
          <p class="muted" style="margin-top:.9rem;font-size:.9rem" data-count></p></aside>
      </div>`;
    const savePill = $('[data-save]');
    let saveTimer;
    const setSave = (state) => {
      const s = !navigator.onLine ? 'offline' : state;
      savePill.dataset.state = s;
      savePill.innerHTML = s === 'saving' ? `${icon('save', 'icon--sm')}<span>${esc(t('as.saving'))}</span>` : s === 'offline' ? `${icon('wifi-off', 'icon--sm')}<span>${esc(t('as.offline'))}</span>` : `${icon('check', 'icon--sm')}<span>${esc(t('as.saved'))}</span>`;
    };
    addEventListener('offline', () => setSave('offline')); addEventListener('online', () => setSave('saved'));
    const persist = () => { setSave('saving'); progress.saveDraft(draftKey, st); clearTimeout(saveTimer); saveTimer = setTimeout(() => setSave('saved'), 450); };
    const paint = () => {
      const i = st.current, q = st.questions[i];
      const [fmt, fmtIcon] = E.formatOf(q);
      $('[data-qpos]').textContent = `${t('as.question')} ${i + 1} / ${total}`;
      $('[data-qcard]').innerHTML = `<div class="qcard__meta"><span class="qcard__format">${icon(fmtIcon)}${esc(q.format || fmt)}</span><span class="muted">${i + 1} / ${total}${q.mod ? ` · ${esc(q.mod)}` : ''}</span></div>
        <h2 id="q-title">${esc(q.q || q.title)}</h2>${q.ask ? `<p class="qcard__ask">${esc(q.ask)}</p>` : ''}
        ${q.scene ? `<div class="scene">${q.sceneLabel ? `<small>${esc(q.sceneLabel)}</small>` : ''}${esc(q.scene)}</div>` : ''}<div data-qbody></div>`;
      E.mount($('[data-qbody]'), q, st.answers[i], (a) => { st.answers[i] = a; persist(); marks(); });
      $('[data-prev]').disabled = i === 0;
      const last = i === total - 1;
      $('[data-next]').innerHTML = last ? `${esc(t('as.review'))} ${icon('arrow')}` : `${esc(t('c.next'))} ${icon('arrow', 'icon-arrow')}`;
      $('[data-flag]').setAttribute('aria-pressed', String(!!st.flags[i]));
      marks();
    };
    const marks = () => {
      $$('[data-go]').forEach((b, i) => { b.classList.toggle('is-answered', E.isAnswered(st.questions[i], st.answers[i])); b.classList.toggle('is-flagged', !!st.flags[i]); b.setAttribute('aria-current', String(i === st.current)); });
      const done = answeredCount();
      $('[data-progress]').style.setProperty('--v', (done / total) * 100);
      $('[data-count]').textContent = `${done} of ${total} answered`;
    };
    const go = (i) => { st.current = Math.max(0, Math.min(total - 1, i)); persist(); paint(); $('[data-qcard]').scrollIntoView({ block: 'nearest' }); $('#q-title')?.focus?.(); };
    $('[data-prev]').addEventListener('click', () => go(st.current - 1));
    $('[data-next]').addEventListener('click', () => (st.current === total - 1 ? review() : go(st.current + 1)));
    $('[data-flag]').addEventListener('click', () => { st.flags[st.current] = !st.flags[st.current]; persist(); paint(); });
    $('[data-palette]').addEventListener('click', (e) => { const b = e.target.closest('[data-go]'); if (b) go(Number(b.dataset.go)); });
    $('[data-to-review]').addEventListener('click', review);
    const timerEl = $('[data-timer] span');
    clearInterval(tick);
    const updateTimer = () => {
      const mins = Math.floor((Date.now() - st.started) / 60000), secs = Math.floor(((Date.now() - st.started) / 1000) % 60);
      timerEl.textContent = def.timer === 'about' ? `${mins}:${String(secs).padStart(2, '0')} · about ${def.about} ${t('c.min')}` : `${mins}:${String(secs).padStart(2, '0')}`;
    };
    updateTimer(); tick = setInterval(updateTimer, 1000);
    $('#q-title')?.setAttribute('tabindex', '-1');
    paint(); setSave('saved');
  };

  /* ---------- Review & submit ---------- */
  const review = () => {
    clearInterval(tick);
    const total = st.questions.length, done = answeredCount();
    const missing = st.questions.map((q, i) => (!E.isAnswered(q, st.answers[i]) ? i : null)).filter((i) => i !== null);
    const flagged = Object.keys(st.flags).filter((k) => st.flags[k]).map(Number);
    root.innerHTML = `
      <section class="band ${def.mod ? 'band--mod' : ''}"><div class="shell"><p class="eyebrow eyebrow--cyan">${esc(def.kicker)}</p><h1>${esc(t('as.review'))}</h1><p class="lede">${done} of ${total} answered.</p></div></section>
      <div class="shell section stack-lg" style="max-width:56rem">
        ${missing.length ? `<div class="notice notice--mustard">${icon('alert-triangle')}<div><h2 style="font-size:1.2rem">${missing.length} ${missing.length === 1 ? 'question is' : 'questions are'} not answered yet</h2><p>${def.counted ? 'You can still submit, but this attempt won’t count towards unlocking the final unless every question is answered.' : 'You can still submit.'}</p></div></div>` : `<div class="notice notice--teal">${icon('check-circle')}<p>Every question is answered.</p></div>`}
        <div class="result-list">${st.questions.map((q, i) => `<div class="result-item"><span class="status status--${E.isAnswered(q, st.answers[i]) ? 'done' : 'todo'}">${icon(E.isAnswered(q, st.answers[i]) ? 'check-circle' : 'circle')}</span><span><strong>${i + 1}.</strong> ${esc((q.q || q.title).slice(0, 110))}${flagged.includes(i) ? ` <span class="badge badge--terracotta">${icon('flag', 'icon--sm')}Marked</span>` : ''}</span><button class="btn btn-sm btn-ghost" type="button" data-back-to="${i}">${E.isAnswered(q, st.answers[i]) ? 'Change' : 'Answer'}</button></div>`).join('')}</div>
        <div class="row"><button class="btn btn-ghost" type="button" data-back-to="${missing[0] ?? 0}">${icon('arrow-left')}Back to questions</button><button class="btn btn-accent btn-lg" type="button" data-submit>${icon('check')}${esc(t('c.submit'))}</button></div>
      </div>`;
    $$('[data-back-to]').forEach((b) => b.addEventListener('click', () => { st.current = Number(b.dataset.backTo); attempt(); }));
    const submitBtn = $('[data-submit]');
    submitBtn.addEventListener('click', async () => {
      if (submitBtn.disabled) return;
      const ok = await confirmDialog({ title: 'Submit this attempt?', body: missing.length ? `${missing.length} unanswered. You can’t change answers after submitting.` : 'You can’t change answers after submitting.', confirm: t('c.submit') });
      if (!ok) return;
      submitBtn.disabled = true; submitBtn.textContent = 'Submitting…';
      const entry = { submittedAt: Date.now(), answered: done, total, allAnswered: missing.length === 0 };
      progress.addAttempt(def.id, entry);
      if (def.pretest) { const p = progress.all(); p.pretest = true; progress.save(p); }
      progress.clearDraft(draftKey); st = null;
      result(entry);
    });
  };

  /* ---------- Result (layout preview; real scores come from the server) ---------- */
  const result = (entry) => {
    const sampleStates = def.final ? ['pass', 'notyet'] : def.pretest || def.practice ? ['plain'] : ['pass', 'notyet', 'gate'];
    root.innerHTML = `
      <section class="band ${def.mod ? 'band--mod' : ''}"><div class="shell"><p class="eyebrow eyebrow--cyan">${esc(def.kicker)}</p><h1>Submitted</h1><p class="lede">${entry.answered} of ${entry.total} answered${entry.allAnswered ? ' · counts towards unlocking the final' : ''}.</p></div></section>
      <div class="shell section stack-lg" style="max-width:60rem">
        <div class="notice">${icon('shield')}<p>Scoring happens on the server, so this preview can’t show your real score. Below is how the result page looks, with <strong>sample numbers</strong>.</p></div>
        ${sampleStates.length > 1 ? `<div class="scenario"><span class="badge badge--muted">${esc(t('c.sample'))}</span><div class="seg" role="group" aria-label="Sample result">${sampleStates.map((s, i) => `<button type="button" data-sample="${s}" aria-pressed="${i === 0}">${{ pass: 'Passed', notyet: 'Not yet', gate: 'Safety gate' }[s]}</button>`).join('')}</div></div>` : ''}
        <div data-sample-view></div>
      </div>`;
    const view = $('[data-sample-view]');
    const total = entry.total;
    const draw = (kind) => {
      const pct = { pass: 72, notyet: 44, gate: 81, plain: 58 }[kind];
      const c = kind === 'pass' ? 'var(--teal)' : kind === 'gate' ? 'var(--plum)' : kind === 'plain' ? 'var(--blue)' : 'var(--mustard-deep)';
      const headline = def.pretest ? 'Pre-test complete' : def.practice ? 'Practice complete' : kind === 'pass' ? 'Passed. Well done!' : kind === 'gate' ? 'This attempt doesn’t count' : 'Not yet. Review the hints and try again';
      const sub = def.pretest ? 'Thank you. Your score helps measure what the programme teaches. The final unlocks once your modules are done too.' : def.practice ? 'Practice doesn’t count. Use it to see which modules to revise.' : kind === 'pass' ? `Your best attempt is now ${pct}%. Module score = Part A + Part B, each worth 50 marks.` : kind === 'gate' ? 'One of your choices could put someone at risk, so this attempt is shown but not counted. Read the hint below, then try again. Attempts are unlimited.' : 'You need 50% to pass. Attempts are unlimited and only your best counts, so this won’t hold you back.';
      const rows = def.final ? ['Strong', 'OK', 'Strong', 'Needs work', 'OK', 'Strong', 'OK', 'Needs work', 'Strong'].map((b, i) => [catalog[i].title, b]) : null;
      const per = Array.from({ length: total }, (_, i) => ((i * 7 + (kind === 'pass' ? 3 : 1)) % 10) < (pct / 10));
      view.innerHTML = `
        <div class="result-hero" style="--c:${c}">
          <div class="ring" style="--v:${pct};--c:${c}"><div><strong>${pct}%</strong><small>${esc(t('c.sample'))}</small></div></div>
          <div class="stack"><h2 style="font-size:clamp(1.6rem,3vw,2.2rem)">${esc(headline)}</h2><p class="muted">${esc(sub)}</p>
            ${kind === 'gate' ? `<div class="notice notice--plum">${icon('shield-alert')}<p><strong>Safety gate.</strong> The approved hint for the risky choice appears here, explaining the safety concern.</p></div>` : ''}
            <div class="row">${def.mod ? `<a class="btn btn-primary" href="module.html?m=${def.mod}#content">${icon('book')}Review the module</a><a class="btn btn-outline" href="assessment.html?m=${def.mod}&part=${part}">${icon('retry')}${esc(t('c.retake'))}</a><a class="btn btn-ghost" href="${C.unitHref(def.mod, `m${def.mod}:practice`)}">Practise</a>` : `<a class="btn btn-primary" href="${def.back}">${esc(t('c.continue'))}</a>`}</div></div>
        </div>
        ${def.final ? `<section><h2 style="font-size:1.5rem;margin-bottom:1rem">How you did in each module</h2><p class="muted" style="margin-bottom:1rem">Bands, not exact percentages, so the final stays fair for everyone.</p><div class="result-list">${rows.map(([m, b]) => `<div class="result-item"><span>${icon(b === 'Strong' ? 'trend' : b === 'OK' ? 'minus' : 'retry')}</span><span>${esc(tc(m))}</span><span class="band badge ${b === 'Strong' ? 'badge--teal' : b === 'OK' ? 'badge--mustard' : 'badge--terracotta'}">${esc(b)}</span></div>`).join('')}</div></section>`
        : def.pretest ? '' : `<section><h2 style="font-size:1.5rem;margin-bottom:1rem">Question by question</h2><div class="result-list">${st === null ? Array.from({ length: total }, (_, i) => `<div class="result-item"><span class="status status--${per[i] ? 'done' : 'progress'}">${icon(per[i] ? 'check-circle' : 'x')}<span class="sr-only">${per[i] ? 'Correct' : 'Incorrect'}</span></span><span><strong>${i + 1}.</strong> ${per[i] ? 'Correct' : `Incorrect. <span class="muted">Hint from the server appears here (never the correct option).</span>`}</span><span class="badge badge--muted">${esc(t('c.sample'))}</span></div>`).join('') : ''}</div>${def.revise ? `<p class="muted" style="margin-top:1rem">${icon('lightbulb')} ${esc(def.revise)}</p>` : ''}</section>`}`;
    };
    $$('[data-sample]').forEach((b) => b.addEventListener('click', () => { $$('[data-sample]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); draw(b.dataset.sample); }));
    draw(sampleStates[0]);
    toast('Attempt submitted');
    scrollTo(0, 0);
  };

  intro();
});
