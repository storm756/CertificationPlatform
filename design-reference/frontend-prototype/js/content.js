/* Renderers for learning content: booklet readings, module handouts, film transcripts.
   All text is escaped. Translations come from CSFR.tc() (draft, labelled), English otherwise. */
window.CSFRContent = (() => {
  const { esc, icon, tc } = CSFR;
  const x = (s) => esc(tc(s));

  /* Booklet blocks: h, p, ul, kv, cols, case, remember, ssr */
  const block = (b) => {
    switch (b.type) {
      case 'h': return `<h3>${x(b.text)}</h3>`;
      case 'p': return `<p>${x(b.text)}</p>`;
      case 'ul': return `<ul>${(b.items || []).map((i) => `<li>${x(i)}</li>`).join('')}</ul>`;
      case 'kv': return `<dl class="kv">${(b.rows || []).map(([k, v]) => `<div><dt>${x(k)}</dt><dd>${x(v)}</dd></div>`).join('')}</dl>`;
      case 'cols': return `<div class="table-wrap" tabindex="0" role="region" aria-label="Table"><table class="table">${b.head ? `<thead><tr>${b.head.map((h) => `<th scope="col">${x(h)}</th>`).join('')}</tr></thead>` : ''}<tbody>${(b.rows || []).map((r) => `<tr>${r.map((c) => `<td>${x(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      case 'case': return `<aside class="callout callout--case">${icon('users')}<span class="callout__label">Case</span>${blocks(b.blocks)}</aside>`;
      case 'remember': return `<aside class="callout callout--remember">${icon('lightbulb')}<span class="callout__label">Remember</span>${blocks(b.blocks)}</aside>`;
      case 'ssr': return ssr([b.stop], [b.save], [b.report]);
      default: return '';
    }
  };
  const blocks = (list) => (list || []).map(block).join('');

  const ssr = (stop, save, report) => `<div class="ssr" role="group" aria-label="Stop, Save, Report">
    <div class="s1"><h4>${icon('stop')}Stop</h4><ul>${stop.filter(Boolean).map((s) => `<li>${x(s)}</li>`).join('')}</ul></div>
    <div class="s2"><h4>${icon('save')}Save</h4><ul>${save.filter(Boolean).map((s) => `<li>${x(s)}</li>`).join('')}</ul></div>
    <div class="s3"><h4>${icon('megaphone')}Report</h4><ul>${report.filter(Boolean).map((s) => `<li>${x(s)}</li>`).join('')}</ul></div></div>`;

  const miniCards = (pairs, kLabel) => `<div class="mini-cards">${pairs.map(([h, p]) => `<div class="mini-card">${kLabel ? `<span class="k">${esc(kLabel)}</span>` : ''}<h4>${x(h)}</h4><p>${x(p)}</p></div>`).join('')}</div>`;

  /* modules.php extra blocks: [type, heading, ...] */
  const handoutBlock = (b) => {
    const [type, heading] = b;
    if (type === 'signs') return `<h3>${x(heading)}</h3><p class="callout callout--key" style="padding-left:3.6rem">${icon('alert-triangle')}${String(b[2]).split(' · ').map(x).join(' <span aria-hidden="true">·</span> ')}</p>`;
    if (type === 'cards') return `<h3>${x(heading)}</h3>${miniCards(b[2])}`;
    if (type === 'list') { const tag = b[3] ? 'ol' : 'ul'; return `<h3>${x(heading)}</h3><${tag}>${b[2].map((i) => `<li>${x(i)}</li>`).join('')}</${tag}>`; }
    if (type === 'table') return `<h3>${x(heading)}</h3><div class="table-wrap" tabindex="0" role="region" aria-label="${esc(heading)}"><table class="table"><thead><tr>${b[2].map((h) => `<th scope="col">${x(h)}</th>`).join('')}</tr></thead><tbody>${b[3].map((r) => `<tr>${r.map((c) => `<td>${x(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    if (type === 'urgency') {
      const colour = { red: 'var(--danger)', amber: '#d97706', yellow: 'var(--mustard-deep)', green: 'var(--teal)' };
      return `<h3>${x(heading)}</h3><div class="table-wrap" tabindex="0" role="region" aria-label="${esc(heading)}"><table class="table"><thead><tr><th scope="col">Colour</th><th scope="col">When</th><th scope="col">First action</th><th scope="col">Act</th></tr></thead><tbody>${b[2].map(([cls, label, level, when, action, time]) =>
        `<tr><td><span class="badge" style="background:color-mix(in srgb, ${colour[cls] || 'var(--blue)'} 18%, transparent);color:${colour[cls] || 'var(--blue)'}"><span aria-hidden="true">●</span> ${x(label)} · ${x(level)}</span></td><td>${x(when)}</td><td>${x(action)}</td><td><strong>${x(time)}</strong></td></tr>`).join('')}</tbody></table></div>`;
    }
    return '';
  };

  const handout = (mod) => {
    const o = mod.overview, e = mod.ext || {};
    const parts = [];
    parts.push(`<h2>What is it?</h2><p>${x(o.what)}</p>`);
    if (o.meet) parts.push(`<h3>${x(o.meet[0])}</h3>${miniCards(o.meet[1])}`);
    if (o.how) parts.push(`<h2>How it works</h2>${miniCards(o.how)}`);
    if (o.blocks) parts.push(o.blocks.map(handoutBlock).join(''));
    if (o.callout) parts.push(`<aside class="callout callout--key">${icon('shield-alert')}<span class="callout__label">Key rule</span><p>${x(o.callout)}</p></aside>`);
    if (o.stop) parts.push(`<h2>Stop · Save · Report</h2>${ssr(o.stop, o.save || [], o.report || [])}`);
    if (o.protect) parts.push(`<h2>How to protect yourself and others</h2>${miniCards(o.protect)}`);
    if (o.rules) parts.push(`<h3>Golden rules</h3><ol>${o.rules.map((r) => `<li>${x(r)}</li>`).join('')}</ol>`);
    if (o.ask) parts.push(`<aside class="callout callout--ask">${icon('help')}<span class="callout__label">Ask yourself</span><div class="ask-list">${o.ask.map((a, i) => `<label class="check"><input type="checkbox" id="ask-${i}"> <span>${x(a)}</span></label>`).join('')}</div></aside>`);
    if (o.remember) parts.push(`<aside class="callout callout--remember">${icon('lightbulb')}<span class="callout__label">Remember</span><ul>${o.remember.map((r) => `<li>${x(r)}</li>`).join('')}</ul></aside>`);
    if (e.steps) parts.push(`<h2>${x(e.steps.title)}</h2><p>${x(e.steps.intro)}</p><ol>${e.steps.steps.map((s) => `<li><strong>${x(s.h)}.</strong> ${x(s.p)}</li>`).join('')}</ol>${e.steps.check ? `<aside class="callout callout--ask">${icon('help')}<span class="callout__label">${esc(CSFR.P('Think aloud'))}</span><p>${x(e.steps.check)}</p></aside>` : ''}`);
    if (e.cards) parts.push(`<h2>${x(e.cards.title)}</h2><p>${x(e.cards.intro)}</p><div class="mini-cards">${e.cards.cards.map((c) => `<div class="mini-card"><h4>${x(c.h)}</h4><p><strong>${x(c.k1)}:</strong> ${x(c.v1)}</p><p style="margin-top:.4rem"><strong>${x(c.k2)}:</strong> ${x(c.v2)}</p></div>`).join('')}</div>${e.cards.think ? `<aside class="callout callout--key">${icon('target')}<span class="callout__label">${x(e.cards.thinkk || 'Decision test')}</span><p>${x(e.cards.think)}</p></aside>` : ''}`);
    if (e.lab) parts.push(`<h2>${x(e.lab.title)}</h2><p>${x(e.lab.intro)}</p><div class="mini-cards">${e.lab.stations.map((s) => `<div class="mini-card"><span class="k">${x(s.k)}</span><h4>${x(s.h)}</h4><p>${x(s.p)}</p></div>`).join('')}</div>${e.lab.expect ? `<aside class="callout callout--remember">${icon('check-circle')}<span class="callout__label">${esc(CSFR.P('What good looks like'))}</span><p>${x(e.lab.expect)}</p></aside>` : ''}`);
    if (e.cases) parts.push(`<h2>${x(e.cases.title)}</h2><p>${x(e.cases.intro)}</p><div class="mini-cards">${e.cases.cases.map((s) => `<div class="mini-card"><span class="k">${x(s.k)}</span><h4>${x(s.h)}</h4><p>${x(s.p)}</p></div>`).join('')}</div>${e.cases.rubric ? `<h3>${esc(CSFR.P('Observer checklist'))}</h3><ul>${e.cases.rubric.map((r) => `<li>${x(r)}</li>`).join('')}</ul>` : ''}${e.cases.discuss ? `<aside class="callout callout--ask">${icon('chat')}<span class="callout__label">${esc(CSFR.P('Discuss'))}</span><p>${x(e.cases.discuss)}</p></aside>` : ''}`);
    if (e.sheet) parts.push(`<h2>${x(e.sheet.title)}</h2><p>${x(e.sheet.intro)}</p><div class="stack">${e.sheet.questions.map((q, i) => `<div class="field"><label for="sheet-${i}">${x(q)}</label><textarea class="textarea" id="sheet-${i}" rows="2" placeholder="${esc(CSFR.P('Your notes stay on this device'))}"></textarea></div>`).join('')}</div>${e.sheet.script ? `<aside class="callout callout--remember">${icon('users')}<span class="callout__label">${x(e.sheet.scripth || '')}</span><p>${x(e.sheet.script)}</p></aside>` : ''}${e.sheet.selfcheck ? `<aside class="callout callout--case">${icon('check-circle')}<span class="callout__label">${esc(CSFR.P('Self-check'))}</span><p>${x(e.sheet.selfcheck)}</p></aside>` : ''}`);
    return parts.join('');
  };

  const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  return { block, blocks, handout, ssr, miniCards, fmtTime };
})();
