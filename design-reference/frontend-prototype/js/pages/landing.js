/* Landing page: stage explorer + progress preview, first-response check, curriculum route, formats explorer. */
CSFR.ready(async () => {
  const { $, $$, esc, icon, tc, t, P, reduceMotion } = CSFR;

  const rovingTabs = (tabs, onSelect) => tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => onSelect(index));
    tab.addEventListener('keydown', (e) => {
      const map = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      let target = null;
      if (map[e.key]) target = (index + map[e.key] + tabs.length) % tabs.length;
      else if (e.key === 'Home') target = 0; else if (e.key === 'End') target = tabs.length - 1;
      if (target === null) return;
      e.preventDefault(); onSelect(target); tabs[target].focus();
    });
  });
  const replay = (el, cls) => { if (reduceMotion) return; el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); };

  /* ---------- Stage explorer ---------- */
  const stages = [
    { key: 'stage.learn', title: 'Learn at your own pace', points: ['A short film, six or seven readings and a handout for every module', 'Nothing is locked, so revisit any topic whenever you like', 'Designed for a phone screen and a 4G connection'], next: 'Learn: Start with the foundations', copy: 'Watch the Module 1 film and read the first topic.', cta: 'Start learning', href: 'module.html?m=1' },
    { key: 'stage.practise', title: 'Practise with real situations', points: ['Myth-or-fact checks and a practice quiz in every module', 'Interactive challenges: spot, sort, match, chat and more', 'An 18-round practice mock gets you ready for the final'], next: 'Practise: Apply your skills', copy: 'Work through hands-on scenarios to build real-world response readiness.', cta: 'Try the practice mock', href: 'assessment.html?part=mock' },
    { key: 'stage.assess', title: 'Show what you know', points: ['Each module ends with a multiple-choice part and an interactive part', 'Pass mark is 50%. Attempts are unlimited and your best one counts', 'You get your score and a hint for every question to revisit'], next: 'Assess: Take your module assessment', copy: 'Answer every question in each part. Your best attempt is the one that counts.', cta: 'See Module 1 assessments', href: 'module.html?m=1#assess' },
    { key: 'stage.certify', title: 'Earn a verifiable certificate', points: ['Final result: 50% module assessments + 50% final exam', 'Download your certificate from your dashboard', 'A QR code lets anyone confirm it is genuine'], next: 'Certify: Complete the final', copy: 'Once the final unlocks, finish it to become eligible for your CSFR certificate.', cta: 'How the final works', href: 'final.html' },
  ];
  const stageTabs = $$('[data-stage]'), links = $$('.stage-link'), panel = $('[data-stage-panel]');
  const track = $('[data-progress-track]'), items = $$('li', track);
  const selectStage = (i) => {
    const s = stages[i];
    stageTabs.forEach((tab, j) => { tab.setAttribute('aria-selected', String(i === j)); tab.tabIndex = i === j ? 0 : -1; tab.classList.toggle('is-done', j < i); });
    links.forEach((l, j) => l.classList.toggle('is-lit', j < i));
    panel.setAttribute('aria-labelledby', stageTabs[i].id);
    $('[data-stage-kicker]').textContent = P('Stage {0} of 4', i + 1);
    $('[data-stage-title]').textContent = P(s.title);
    $('[data-stage-list]').replaceChildren(...s.points.map((p) => Object.assign(document.createElement('li'), { textContent: P(p) })));
    replay(panel, 'is-swapping');
    track.style.setProperty('--progress', i);
    items.forEach((it, j) => { it.classList.toggle('is-done', j < i); it.classList.toggle('is-current', j === i); if (j === i) it.setAttribute('aria-current', 'step'); else it.removeAttribute('aria-current'); $('[data-progress-state]', it).textContent = P(j < i ? 'completed' : j === i ? 'current step' : 'not started'); });
    $('[data-progress-status]').textContent = `${P('Step {0} of 4', i + 1)} · ${t(s.key)}`;
    $('[data-next-title]').textContent = P(s.next); $('[data-next-copy]').textContent = P(s.copy);
    $('[data-next-cta-label]').textContent = P(s.cta); $('[data-next-cta]').href = s.href;
  };
  rovingTabs(stageTabs, selectStage); selectStage(0);

  /* ---------- First-response check (legacy landing content) ---------- */
  const checks = [
    ['Within the hour', 'Call 1930, then your bank’s own number.', 'The first hour gives the best chance of a hold.'],
    ['Right now', 'Hang up. There is no digital arrest.', 'If you paid, call 1930. If you feel unsafe, 112.'],
    ['Today', 'Never read it out. Turn on two-step verification.', 'That code moves your WhatsApp to their phone.'],
    ['Within two days', 'Report it on Chakshu at sancharsaathi.gov.in.', 'Then delete it. Never open its link again.'],
  ];
  const checkTabs = $$('[data-check]'), answer = $('[data-check-answer]');
  rovingTabs(checkTabs, (i) => {
    checkTabs.forEach((b, j) => { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; });
    answer.innerHTML = `<span class="when">${esc(P(checks[i][0]))}</span><strong>${esc(P(checks[i][1]))}</strong><p>${esc(P(checks[i][2]))}</p>`;
    replay(answer, 'is-swapping');
  });

  /* ---------- Curriculum route from the catalogue ---------- */
  const colours = ['var(--teal)', 'var(--blue)', 'var(--mustard-deep)', 'var(--terracotta)', 'var(--plum)'];
  try {
    const catalog = await CSFR.loadCatalog();
    $('[data-route]').innerHTML = catalog.map((m, i) => m.kind === 'capstone'
      ? `<li><a class="route-card route-card--capstone" href="module.html?m=${m.n}" style="--c: var(--plum)"><span class="route-card__num">${icon('flag')}</span><h3>${esc(P('Module {0}', m.n))} · ${esc(tc(m.title))}</h3><p>${esc(P(`${m.tagline} Not graded.`))}</p></a></li>`
      : `<li><a class="route-card" href="module.html?m=${m.n}" style="--c: ${colours[i % 5]}"><span class="route-card__num">${String(m.n).padStart(2, '0')}</span><h3>${esc(tc(m.title))}</h3><p>${esc(P('{0} topics · ≈ {1} h · 100 marks', m.topics.length, m.hours))}</p></a></li>`).join('');
  } catch { $('[data-route]').innerHTML = '<li class="muted">Module list unavailable. Open the <a href="modules.html">catalogue</a>.</li>'; }

  /* ---------- Formats explorer (abstract illustrations only) ---------- */
  const rep = (n, f) => Array.from({ length: n }, (_, i) => f(i)).join('');
  const mocks = {
    options: () => `<div class="m-line m-line--title"></div>${rep(4, (i) => `<div class="m-opt${i === 1 ? ' is-on' : ''}"><span style="max-width:${[80, 65, 72, 55][i]}%"></span></div>`)}`,
    verdict: () => `<div class="m-screen"><div class="m-line" style="width:70%"></div><div class="m-line" style="width:50%"></div></div><div class="m-cols"><div class="m-opt is-on"><span></span></div><div class="m-opt"><span></span></div></div>`,
    multi: () => `<div class="m-line m-line--title"></div>${rep(4, (i) => `<div class="m-opt${i % 2 === 0 ? ' is-on' : ''}"><span style="max-width:${[70, 60, 75, 50][i]}%"></span></div>`)}`,
    cards: () => `<div class="m-line m-line--title"></div><div class="m-grid">${rep(6, (i) => `<div class="m-card${i === 4 ? ' is-on' : ''}"></div>`)}</div>`,
    spot: () => `<div class="m-screen"><div class="m-line" style="width:40%"></div><div class="m-line"></div><div><span class="m-mark" style="width:35%"></span></div><div class="m-line" style="width:85%"></div><div><span class="m-mark" style="width:25%"></span></div></div>`,
    hotspot: () => `<div class="m-screen"><div class="m-line" style="width:50%"></div><div class="m-line" style="width:80%"></div><div class="m-line" style="width:65%"></div><span class="m-target" style="right:18%;top:30%"></span></div>`,
    sort: () => `<div class="m-cols"><div class="m-col" style="--c:var(--teal)"><b></b><div class="m-chip"></div><div class="m-chip"></div></div><div class="m-col" style="--c:var(--terracotta)"><b></b><div class="m-chip"></div></div></div>`,
    match: () => rep(3, () => '<div class="m-pair"><div class="m-chip"></div><i></i><div class="m-chip"></div></div>'),
    order: () => rep(4, (i) => `<div class="m-step"><em>${i + 1}</em><span style="max-width:${[70, 55, 80, 60][i]}%"></span></div>`),
    build: () => `<div class="m-line m-line--title"></div><div class="m-build"><i style="--c:var(--teal);--w:5rem"></i><i style="--c:var(--mustard);--w:3.5rem"></i></div><div class="m-build" style="border-style:solid;background:transparent">${['var(--terracotta)', 'var(--plum)', 'var(--blue)'].map((c, i) => `<i style="--c:${c};--w:${[4, 3, 5][i]}rem;opacity:.85"></i>`).join('')}</div>`,
    settings: () => rep(4, (i) => `<div class="m-toggle"><span></span><b class="${i % 2 === 0 ? 'is-on' : ''}"></b></div>`),
    dial: () => '<div class="m-line m-line--title" style="justify-self:center"></div><div class="m-dial"></div>',
    chat: () => '<div class="m-bubble"><span style="width:9rem"></span><span style="width:6rem"></span></div><div class="m-bubble m-bubble--me"><span style="width:7rem"></span></div><div class="m-replies"><i></i><i></i></div>',
    crossword: () => `<div class="m-cross">${[...('xxfffxx' + 'xxsxxsx' + 'fffffsx' + 'xxsxxsx')].map((c) => `<i class="${c === 'x' ? 'x' : c === 'f' ? 'f' : ''}"></i>`).join('')}</div>`,
  };
  const formats = [
    ['Multiple choice', 'square-check', 'options', 'Choose the best response to a situation.'],
    ['Quick verdict', 'square-check', 'verdict', 'Decide in one tap: safe or risky, real or fake.'],
    ['Verdict cards', 'layers', 'cards', 'Give a verdict on each action: do now, or never.'],
    ['Spot the signs', 'search', 'spot', 'Read a message and tap every warning sign.'],
    ['Tap the picture', 'crosshair', 'hotspot', 'Tap the risky devices or settings in a picture.'],
    ['Sort board', 'columns', 'sort', 'Place each item into the right group.'],
    ['Connect the pairs', 'link', 'match', 'Connect each item with the one it belongs to.'],
    ['Put in order', 'list', 'order', 'Put response steps in sequence with the move buttons.'],
    ['Evidence bag', 'pointer', 'multi', 'Tick everything that belongs, and leave out what would harm it.'],
    ['Build the reply', 'blocks', 'build', 'Assemble a reply from cards, one for each step.'],
    ['Fix the settings', 'sliders', 'settings', 'Change the unsafe settings on a mock device.'],
    ['Dial it in', 'gauge', 'dial', 'Set the right number: hours, days, limits.'],
    ['Talk to the person', 'chat', 'chat', 'Reply step by step to someone who needs help.'],
    ['Crossword', 'grid', 'crossword', 'Revise key terms in a crossword.', true],
  ];
  const tabList = $('[data-format-tabs]'), mockEl = $('[data-format-mock]'), fPanel = $('[data-format-panel]');
  const fTabs = formats.map(([name, ic], i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'format-tab'; b.id = `ftab-${i}`; b.setAttribute('role', 'tab'); b.setAttribute('aria-controls', 'format-panel');
    b.innerHTML = `${icon(ic)}<span>${esc(P(name))}</span>`; tabList.append(b); return b;
  });
  const wide = matchMedia('(min-width: 64rem)');
  const selectFormat = (i, scroll = true) => {
    const [name, ic, mock, desc, practice] = formats[i];
    fTabs.forEach((b, j) => { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; });
    fPanel.setAttribute('aria-labelledby', fTabs[i].id);
    $('[data-format-icon]').setAttribute('href', `#i-${ic}`);
    $('[data-format-name]').textContent = P(name); $('[data-format-desc]').textContent = P(desc);
    $('[data-format-tag]').hidden = !practice;
    mockEl.innerHTML = mocks[mock](); replay(mockEl, 'is-swapping');
    if (scroll && !wide.matches) fTabs[i].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  };
  rovingTabs(fTabs, (i) => selectFormat(i)); selectFormat(0, false);

  /* One FAQ open at a time */
  const faqs = $$('.faq details');
  faqs.forEach((d) => d.addEventListener('toggle', () => { if (d.open) faqs.forEach((o) => { if (o !== d) o.open = false; }); }));
});
