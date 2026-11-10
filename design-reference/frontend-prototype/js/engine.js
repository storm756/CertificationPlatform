/* Assessment engine: one renderer per format. Each receives ONLY the server-style projection
   (no keys, scores, hints or canonical order) and reports answers as tokens. Nothing here scores. */
window.CSFREngine = (() => {
  const { esc, icon } = CSFR;
  const FORMAT = {
    mcq: ['Multiple choice', 'square-check'], mc: ['Quick verdict', 'square-check'], spot: ['Spot the signs', 'search'], chat: ['Talk to the person', 'chat'],
    pick: ['Evidence bag', 'pointer'], build: ['Build the reply', 'blocks'], crossword: ['Crossword', 'grid'], settings: ['Fix the settings', 'sliders'],
    sort: ['Sort board', 'columns'], match: ['Connect the pairs', 'link'], order: ['Put in order', 'list'], dial: ['Dial it in', 'gauge'], cards: ['Verdict cards', 'layers'], hotspot: ['Tap the picture', 'crosshair'],
  };
  const formatOf = (q) => FORMAT[q.type] || ['Question', 'help'];
  const pressed = (on) => `aria-pressed="${on ? 'true' : 'false'}"`;
  const optBtn = (id, text, on, multi, key) => `<button type="button" class="opt${multi ? ' opt--multi' : ''}" data-id="${esc(id)}" ${pressed(on)}>${key ? `<span class="opt__key" aria-hidden="true">${key}</span>` : ''}<span class="opt__mark" aria-hidden="true">${icon('check')}</span><span>${esc(text)}</span></button>`;
  const confirmRow = (a, label) => `<label class="check" style="margin-top:1rem"><input type="checkbox" data-confirm ${a.confirmed ? 'checked' : ''}> <span>${esc(label)}</span></label>`;

  /* Grid geometry for crosswords from word starts and lengths only. */
  const xwGeometry = (words) => {
    const cells = new Map(); const starts = new Map(); let rows = 0, cols = 0;
    words.forEach((w) => {
      for (let i = 0; i < w.len; i++) {
        const r = w.row + (w.dir === 'D' ? i : 0), c = w.col + (w.dir === 'A' ? i : 0);
        const k = `${r},${c}`; const cell = cells.get(k) || { r, c, words: [] }; cell.words.push(w.n); cells.set(k, cell);
        rows = Math.max(rows, r + 1); cols = Math.max(cols, c + 1);
      }
      const sk = `${w.row},${w.col}`; if (!starts.has(sk)) starts.set(sk, starts.size + 1);
      w.label = starts.get(sk);
    });
    return { cells, starts, rows, cols };
  };

  const body = (q, a) => {
    switch (q.type) {
      case 'mcq': case 'mc':
        return `<div class="opts" role="group" aria-label="Options">${q.opts.map((o, i) => optBtn(o.id, o.t, a.opt === o.id, false, q.type === 'mcq' ? 'ABCD'[i] : '')).join('')}</div>`;
      case 'pick':
        return `<div class="opts" role="group" aria-label="Items">${q.items.map((o) => optBtn(o.id, o.t, (a.items || []).includes(o.id), true)).join('')}</div>`;
      case 'spot': {
        const on = new Set(a.segs || []);
        return `<p class="muted" style="font-size:.92rem;margin-bottom:.5rem">${icon('pointer', 'icon--sm')} Tap the underlined parts you think are warning signs. Tap again to undo.</p>
          <div class="spot-msg${q.style === 'email' ? ' spot-msg--email' : ''}">${q.segments.map((s) => s.tap ? `<button type="button" class="seg-btn" data-seg="${esc(s.id)}" ${pressed(on.has(s.id))}>${esc(s.t)}</button>` : esc(s.t)).join('')}</div>`;
      }
      case 'chat': {
        const replies = a.steps || [];
        const out = [];
        for (let i = 0; i < q.steps.length; i++) {
          const st = q.steps[i];
          out.push(`<div class="bubble"><small>${esc(q.who || 'They say')}</small>${esc(st.say)}</div>`);
          if (replies[i]) { const r = st.replies.find((x) => x.id === replies[i]); out.push(`<div class="bubble bubble--me"><small style="color:inherit;opacity:.75">You</small>${esc(r?.t)}</div>`); continue; }
          out.push(`<div class="opts" role="group" aria-label="Choose your reply">${st.replies.map((r) => optBtn(r.id, r.t, false, false)).join('')}</div>`);
          out.push(i < q.steps.length - 1 ? '<p class="muted" style="font-size:.88rem">The next message appears after your reply is saved.</p>' : '');
          break;
        }
        if (replies.length) out.push('<button type="button" class="btn btn-ghost btn-sm" data-chat-reset style="justify-self:start">' + icon('retry') + 'Restart this conversation</button>');
        return `<div class="chat">${out.join('')}</div>`;
      }
      case 'build':
        return `<div class="stack">${q.slots.map((s, i) => `<div class="sort-item"><p>${i + 1}. ${esc(s.label)}</p><div class="chip-row" role="group" aria-label="${esc(s.label)}">${s.chips.map((c) => `<button type="button" class="chip" data-slot="${i}" data-id="${esc(c.id)}" ${pressed((a.slots || [])[i] === c.id)}>${esc(c.t)}</button>`).join('')}</div></div>`).join('')}</div>`;
      case 'settings':
        return `<div class="device"><div class="device__screen"><p class="device__title">${esc(q.screen || q.device || 'Settings')}</p>${q.rows.map((r) => {
          const val = (a.rows || {})[r.id] ?? r.start;
          return `<div class="setting"><span>${esc(r.t)}</span><div class="seg" role="radiogroup" aria-label="${esc(r.t)}">${r.opts.map((o, i) => `<button type="button" role="radio" data-row="${esc(r.id)}" data-val="${i}" aria-checked="${val === i}" ${pressed(val === i)}>${esc(o)}</button>`).join('')}</div></div>`;
        }).join('')}</div></div>${confirmRow(a, 'I’ve checked every setting')}`;
      case 'sort':
        return `<p class="muted" style="font-size:.92rem;margin-bottom:.6rem">${q.bins.map((b) => `<strong>${esc(b.t)}</strong>${b.d ? `: ${esc(b.d)}` : ''}`).join(' · ')}</p><div class="sort-board">${q.items.map((it) => `<div class="sort-item"><p>${esc(it.t)}</p><div class="chip-row" role="group" aria-label="Choose a group">${q.bins.map((b) => `<button type="button" class="chip" data-item="${esc(it.id)}" data-id="${esc(b.id)}" ${pressed((a.items || {})[it.id] === b.id)}>${esc(b.t)}</button>`).join('')}</div></div>`).join('')}</div>`;
      case 'cards':
        return `<div class="sort-board">${q.items.map((it) => `<div class="sort-item"><p>${esc(it.t)}</p><div class="chip-row" role="group" aria-label="Your verdict">${q.labels.map((l) => `<button type="button" class="chip" data-item="${esc(it.id)}" data-id="${esc(l.id)}" ${pressed((a.items || {})[it.id] === l.id)}>${esc(l.t)}</button>`).join('')}</div></div>`).join('')}</div>`;
      case 'match':
        return `<div class="stack">${q.left.map((l) => `<div class="match-row"><strong id="ml-${esc(l.id)}">${esc(l.t)}</strong><select class="select" data-left="${esc(l.id)}" aria-labelledby="ml-${esc(l.id)}"><option value="">${esc(q.rightLabel ? `Choose ${q.rightLabel.toLowerCase()}` : 'Choose a match')}</option>${q.right.map((r) => `<option value="${esc(r.id)}"${(a.pairs || {})[l.id] === r.id ? ' selected' : ''}>${esc(r.t)}</option>`).join('')}</select></div>`).join('')}</div>`;
      case 'order': {
        const ids = a.order || q.items.map((i) => i.id);
        return `<ol class="order-list">${ids.map((id, i) => { const it = q.items.find((x) => x.id === id); return `<li class="order-item"><span>${esc(it.t)}</span><span class="btns"><button type="button" data-move="-1" data-id="${esc(id)}" aria-label="Move up: ${esc(it.t)}" ${i === 0 ? 'disabled' : ''}>${icon('arrow-up')}</button><button type="button" data-move="1" data-id="${esc(id)}" aria-label="Move down: ${esc(it.t)}" ${i === ids.length - 1 ? 'disabled' : ''}>${icon('arrow-down')}</button></span></li>`; }).join('')}</ol>${confirmRow(a, 'This is my order')}`;
      }
      case 'dial':
        return `<div class="stack">${q.rows.map((r) => { const v = (a.rows || {})[r.id] ?? r.start; return `<div class="dial-row"><p id="dl-${esc(r.id)}"><strong>${esc(r.label)}</strong></p><div class="dial-ctrl" role="group" aria-labelledby="dl-${esc(r.id)}">${r.steps.filter((s) => s < 0).map((s) => `<button type="button" data-dial="${esc(r.id)}" data-step="${s}" aria-label="${s}">${s}</button>`).join('')}<output aria-live="polite">${v} ${esc(r.unit)}</output>${r.steps.filter((s) => s > 0).map((s) => `<button type="button" data-dial="${esc(r.id)}" data-step="${s}" aria-label="+${s}">+${s}</button>`).join('')}</div></div>`; }).join('')}</div>${confirmRow(a, 'These are my numbers')}`;
      case 'hotspot': {
        const on = new Set(a.spots || []);
        return `<p class="muted" style="font-size:.92rem;margin-bottom:.6rem">${esc(q.legend || '')}</p><div class="hotspot-svg" data-hotspot>${q.svg}</div>
          <div class="opts" role="group" aria-label="Tap each risky item" style="margin-top:.9rem">${q.spots.map((s) => optBtn(s.id, s.label, on.has(s.id), true)).join('')}</div>`;
      }
      case 'crossword': {
        const g = xwGeometry(q.words); const cells = a.cells || {};
        let grid = '';
        for (let r = 0; r < g.rows; r++) for (let c = 0; c < g.cols; c++) {
          const k = `${r},${c}`;
          grid += g.cells.has(k) ? `<span class="xw-cell">${g.starts.has(k) ? `<sup>${g.starts.get(k)}</sup>` : ''}<input maxlength="1" autocomplete="off" autocapitalize="characters" spellcheck="false" data-cell="${k}" value="${esc(cells[k] || '')}" aria-label="Row ${r + 1}, column ${c + 1}"></span>` : '<span aria-hidden="true"></span>';
        }
        const clues = (dir) => q.words.filter((w) => w.dir === dir).map((w) => `<li><b>${w.label}</b> ${esc(w.clue)} <span class="muted">(${w.len})</span></li>`).join('');
        return `<div class="xw"><div class="xw-grid" style="grid-template-columns:repeat(${g.cols}, 2.4rem)">${grid}</div><div class="xw-clues"><h3 style="font-size:1.05rem">Across</h3><ul class="stack" style="gap:.35rem">${clues('A')}</ul><h3 style="font-size:1.05rem;margin-top:.6rem">Down</h3><ul class="stack" style="gap:.35rem">${clues('D')}</ul></div></div>`;
      }
      default: return '<p class="muted">This format is not available in the preview.</p>';
    }
  };

  const isAnswered = (q, a) => {
    if (!a) return false;
    switch (q.type) {
      case 'mcq': case 'mc': return !!a.opt;
      case 'pick': return (a.items || []).length > 0;
      case 'spot': return (a.segs || []).length > 0;
      case 'hotspot': return (a.spots || []).length > 0;
      case 'chat': return (a.steps || []).filter(Boolean).length === q.steps.length;
      case 'build': return q.slots.every((_, i) => (a.slots || [])[i]);
      case 'sort': case 'cards': return q.items.every((it) => (a.items || {})[it.id]);
      case 'match': return q.left.every((l) => (a.pairs || {})[l.id]);
      case 'settings': case 'order': case 'dial': return !!a.confirmed;
      case 'crossword': { const g = xwGeometry(q.words); return [...g.cells.keys()].every((k) => (a.cells || {})[k]); }
      default: return false;
    }
  };

  /* Mount a question; onChange(answer) fires on every change (caller autosaves). */
  const mount = (el, q, answer, onChange) => {
    let a = JSON.parse(JSON.stringify(answer || {}));
    const fire = (rerender = true) => { onChange(JSON.parse(JSON.stringify(a))); if (rerender) draw(); };
    const draw = () => {
      const focusKey = document.activeElement && el.contains(document.activeElement) ? (document.activeElement.dataset.id || document.activeElement.dataset.seg || document.activeElement.dataset.cell || null) : null;
      el.innerHTML = body(q, a);
      if (q.type === 'hotspot') $$h(el, q, a);
      if (focusKey) el.querySelector(`[data-id="${CSS.escape(focusKey)}"], [data-seg="${CSS.escape(focusKey)}"], [data-cell="${CSS.escape(focusKey)}"]`)?.focus();
    };
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b || !el.contains(b)) return;
      const id = b.dataset.id;
      switch (q.type) {
        case 'mcq': case 'mc': a.opt = id; break;
        case 'pick': case 'hotspot': { const key = q.type === 'pick' ? 'items' : 'spots'; const s = new Set(a[key] || []); s.has(id) ? s.delete(id) : s.add(id); a[key] = [...s]; break; }
        case 'spot': { if (!b.dataset.seg) return; const s = new Set(a.segs || []); const k = b.dataset.seg; s.has(k) ? s.delete(k) : s.add(k); a.segs = [...s]; break; }
        case 'chat': {
          if (b.hasAttribute('data-chat-reset')) { a.steps = []; break; }
          if (!id) return; a.steps = a.steps || []; a.steps[a.steps.length] = id; break;
        }
        case 'build': a.slots = a.slots || []; a.slots[Number(b.dataset.slot)] = id; break;
        case 'sort': case 'cards': a.items = { ...(a.items || {}), [b.dataset.item]: id }; break;
        case 'settings': if (!b.dataset.row) return; a.rows = { ...(a.rows || {}), [b.dataset.row]: Number(b.dataset.val) }; break;
        case 'order': { if (!b.dataset.move) return; const ids = a.order || q.items.map((i) => i.id); const i = ids.indexOf(id); const j = i + Number(b.dataset.move); if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; a.order = [...ids]; break; }
        case 'dial': { if (!b.dataset.dial) return; const r = q.rows.find((x) => x.id === b.dataset.dial); const cur = (a.rows || {})[r.id] ?? r.start; a.rows = { ...(a.rows || {}), [r.id]: Math.min(r.max, Math.max(r.min, cur + Number(b.dataset.step))) }; break; }
        default: return;
      }
      fire();
    });
    el.addEventListener('change', (e) => {
      if (e.target.matches('[data-confirm]')) { a.confirmed = e.target.checked; fire(false); }
      if (e.target.matches('[data-left]')) { a.pairs = { ...(a.pairs || {}), [e.target.dataset.left]: e.target.value }; if (!e.target.value) delete a.pairs[e.target.dataset.left]; fire(false); }
    });
    el.addEventListener('input', (e) => {
      const inp = e.target.closest('[data-cell]'); if (!inp) return;
      inp.value = inp.value.replace(/[^a-z]/gi, '').toUpperCase().slice(-1);
      a.cells = { ...(a.cells || {}), [inp.dataset.cell]: inp.value }; fire(false);
      if (inp.value) { const all = [...el.querySelectorAll('[data-cell]')]; const [r, c] = inp.dataset.cell.split(',').map(Number); const nextA = el.querySelector(`[data-cell="${r},${c + 1}"]`); const nextD = el.querySelector(`[data-cell="${r + 1},${c}"]`); (inp.dataset.dir === 'D' ? nextD || nextA : nextA || nextD || all[all.indexOf(inp) + 1])?.focus(); }
    });
    el.addEventListener('keydown', (e) => {
      const inp = e.target.closest('[data-cell]'); if (!inp) return;
      const [r, c] = inp.dataset.cell.split(',').map(Number);
      const mv = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }[e.key];
      if (mv) { e.preventDefault(); el.querySelector(`[data-cell="${r + mv[0]},${c + mv[1]}"]`)?.focus(); inp.dataset.dir = mv[0] ? 'D' : 'A'; }
      if (e.key === 'Backspace' && !inp.value) { const prev = el.querySelector(`[data-cell="${r},${c - 1}"]`) || el.querySelector(`[data-cell="${r - 1},${c}"]`); prev?.focus(); }
    });
    draw();
  };
  /* Hotspot picture: the SVG groups act as extra tap targets mirroring the accessible buttons below. */
  const $$h = (el, q, a) => {
    const on = new Set(a.spots || []);
    el.querySelectorAll('[data-hotspot] [data-h]').forEach((g) => {
      g.classList.toggle('is-on', on.has(g.dataset.h));
      g.setAttribute('aria-hidden', 'true');
      g.addEventListener('click', () => el.querySelector(`.opt[data-id="${CSS.escape(g.dataset.h)}"]`)?.click());
    });
  };

  return { mount, isAnswered, formatOf, FORMAT };
})();
