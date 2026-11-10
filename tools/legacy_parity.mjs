// Scorer parity: run the REAL legacy engine (engine.js) on legacy-shaped questions with generated
// answers and record the score and safety-gate it produces. The Python scorers must match these
// (tests/test_scorer_parity.py for invented cases; `manage.py check_legacy_parity` for the real
// private questions). Dev tool: needs `npm install` in tools/ (jsdom).
//
//   node legacy_parity.mjs --engine D:/csfr-lms/setup/scorm/src/m11/js/engine.js \
//        --questions questions.json --out cases.json [--per 6] [--seed 1]
//
// questions.json is either {"modules": {...}} (the legacy_export.mjs output) or a plain array of
// {id, question} objects. The engine's own code is instrumented in memory only (one line records
// each result); nothing about it is changed on disk. Output holds logical answers (positions in
// the legacy question) and the JS result. It prints counts only.
import fs from "node:fs";
import { JSDOM } from "jsdom";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const per = Number(args.per ?? 6);
const engineSrc = fs.readFileSync(args.engine, "utf8");
const hook = "state.res[state.i] = { score: score, gate: !!gate };";
if (!engineSrc.includes(hook)) throw new Error("engine.js is not the expected version");
const instrumented = engineSrc.replace(hook, hook + " window.__r = { score: score, gate: !!gate };");

const input = JSON.parse(fs.readFileSync(args.questions, "utf8"));
const list = Array.isArray(input)
  ? input
  : Object.entries(input.modules).flatMap(([file, m]) => m.questions.map((q, i) => ({ id: `${file}:${i + 1}`, question: q })));

const mulberry = (seed) => () => {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

// ---- logical answers, in positions of the legacy question ----------------------------------------
const pickN = (rnd, n, k) => { const a = [...Array(n).keys()]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a.slice(0, k); };
const taps = (t) => [...t.matchAll(/\[\[(!?)([\s\S]+?)\]\]/g)].map((m) => ({ risky: !!m[1] }));
const kindOf = (r) => r.kind || (Array.isArray(r.opts) ? "seg" : "number");

function stepsOf(r) { return r.steps || (r.kind === "time" ? [-60, -10, -5, 5, 10, 60] : [-1, 1]); }
function walk(r, rnd, mode) {
  let v = r.start; const clicks = [];
  const apply = (s) => { v += s; if (r.kind !== "time") { if (r.min != null) v = Math.max(r.min, v); if (r.max != null) v = Math.min(r.max, v); } clicks.push(s); };
  const dist = (x) => (r.kind === "time" ? Math.abs((((x % 1440) + 1440) % 1440) - (((r.answer % 1440) + 1440) % 1440)) : Math.abs(x - r.answer));
  if (mode === "perfect") { for (let g = 0; g < 80 && dist(v) > (r.tol || 0); g++) { const best = stepsOf(r).map((s) => [dist(v + s), s]).sort((a, b) => a[0] - b[0])[0]; if (best[0] >= dist(v)) break; apply(best[1]); } }
  else for (let k = Math.floor(rnd() * 7); k > 0; k--) apply(stepsOf(r)[Math.floor(rnd() * stepsOf(r).length)]);
  return { value: v, clicks };
}

function logicalFor(q, rnd, mode) {
  const perfect = mode === "perfect";
  switch (q.type) {
    case "mc": return { choice: perfect ? q.a : Math.floor(rnd() * q.opts.length) };
    case "cards": return { answers: Object.fromEntries(q.items.map((it, i) => [i, perfect ? it.a : Math.floor(rnd() * q.labels.length)])) };
    case "spot": { const t = taps(q.text); return { picked: t.map((x, i) => (perfect ? x.risky : rnd() < 0.5) ? i : -1).filter((i) => i >= 0) }; }
    case "hotspot": { const ids = Object.keys(q.spots); return { picked: ids.map((id, i) => (perfect ? q.spots[id].ok : rnd() < 0.4) ? i : -1).filter((i) => i >= 0) }; }
    case "sort": return { placed: Object.fromEntries(q.items.map((it, i) => [i, perfect ? it.b : Math.floor(rnd() * q.bins.length)])) };
    case "match": { const n = q.pairs.length, total = n + (q.extra || []).length; const rights = perfect ? [...Array(n).keys()] : pickN(rnd, total, n); return { links: Object.fromEntries(rights.map((r, i) => [i, r])) }; }
    case "order": return { sequence: perfect ? [...Array(q.items.length).keys()] : pickN(rnd, q.items.length, q.items.length) };
    case "pick": { const good = q.items.map((it, i) => (it.ok ? i : -1)).filter((i) => i >= 0); if (q.need) return { picked: perfect ? good : pickN(rnd, q.items.length, q.need) }; return { picked: perfect ? good : pickN(rnd, q.items.length, Math.floor(rnd() * q.items.length)) }; }
    case "build": { const used = new Set(); const filled = {}; q.slots.forEach((s, k) => { const allowed = (s.chips || q.chips.map((_, i) => i)).filter((c) => !used.has(c)); const a = Array.isArray(s.a) ? s.a : [s.a]; const c = perfect && !used.has(a[0]) ? a[0] : allowed[Math.floor(rnd() * allowed.length)]; used.add(c); filled[k] = c; }); return { filled }; }
    case "settings": return { values: Object.fromEntries(q.rows.map((r, k) => { const want = Array.isArray(r.want) ? r.want : [r.want]; if (r.kind === "switch") return [k, perfect ? Number(!!want[0]) : Number(rnd() < 0.5)]; return [k, perfect ? want[0] : Math.floor(rnd() * r.opts.length)]; })) };
    case "dial": { const rows = q.rows.map((r) => walk(r, rnd, mode)); return { values: Object.fromEntries(rows.map((w, k) => [k, w.value])), clicks: rows.map((w) => w.clicks) }; }
    case "chat": return { replies: q.steps.map((s) => { if (perfect) return s.replies.findIndex((r) => r.s === 2); return Math.floor(rnd() * s.replies.length); }) };
    case "crossword": { const letters = {}; q.words.forEach((w) => [...w.a.toUpperCase()].forEach((ch, i) => { const r = w.r + (w.dir === "D" ? i : 0), c = w.c + (w.dir === "A" ? i : 0); const roll = rnd(); letters[`${r},${c}`] = perfect || roll < 0.55 ? ch : roll < 0.8 ? String.fromCharCode(65 + Math.floor(rnd() * 26)) : ""; })); const cleaned = Object.fromEntries(Object.entries(letters).filter(([, v]) => v)); return { letters: cleaned }; }
    default: throw new Error("unknown format " + q.type);
  }
}

// ---- drive the real engine --------------------------------------------------------------------------
const textOf = (w, html) => { const d = w.document.createElement("div"); d.innerHTML = html; return d.textContent; };
const norm = (s) => String(s).replace(/\s+/g, " ").trim();
const btnWithText = (w, root, wanted, sel = "button") => [...root.querySelectorAll(sel)].find((b) => norm(b.firstChild && b.firstChild.nodeType === 3 ? b.firstChild.textContent : b.textContent) === norm(wanted) || norm(b.textContent) === norm(wanted));
const check = (w) => [...w.document.querySelectorAll(".actions button.primary")].pop();

function drive(w, q, L) {
  const area = w.document.querySelector(".area");
  const click = (el) => { if (!el) throw new Error("control not found"); if (el.click) el.click(); else el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); };
  switch (q.type) {
    case "mc": { const opt = q.opts[L.choice]; return click(btnWithText(w, area, typeof opt === "string" ? opt : opt.t)); }
    case "cards": {
      for (let n = 0; n < q.items.length; n++) {
        const vc = w.document.querySelector(".vcard"); const shown = norm(vc.textContent.replace(/^Card \d+ of \d+/, ""));
        const k = q.items.findIndex((it) => norm(textOf(w, it.t)) === shown);
        if (k < 0) throw new Error("card not found");
        click([...w.document.querySelectorAll(".area .row button")][L.answers[k]]);
        click(check(w));
      }
      return;
    }
    case "spot": { const t = [...area.querySelectorAll(".tap")]; L.picked.forEach((i) => click(t[i])); return click(check(w)); }
    case "hotspot": { const ids = Object.keys(q.spots); L.picked.forEach((i) => click(area.querySelector(`[data-h="${ids[i]}"]`))); return click(check(w)); }
    case "sort": { Object.entries(L.placed).forEach(([k, b]) => { click(area.querySelector(`.chip[data-k="${k}"]`)); click(area.querySelectorAll(".bin > button")[b]); }); return click(check(w)); }
    case "match": {
      const rights = (id) => (id < q.pairs.length ? q.pairs[id].r : q.extra[id - q.pairs.length]);
      Object.entries(L.links).forEach(([l, r]) => {
        click(area.querySelector(`.col.left button[data-k="${l}"]`));
        const rb = [...area.querySelectorAll(".col.right button")].find((b) => norm(b.firstChild.textContent) === norm(textOf(w, rights(r))));
        click(rb);
      });
      return click(check(w));
    }
    case "order": { L.sequence.forEach((k) => click(btnWithText(w, area.querySelector(".pool"), textOf(w, q.items[k].t)))); return click(check(w)); }
    case "pick": { L.picked.forEach((k) => click(area.querySelector(`.tile[data-k="${k}"]`))); return click(check(w)); }
    case "build": { Object.entries(L.filled).forEach(([s, c]) => { click(area.querySelectorAll(".slot button")[s]); click(btnWithText(w, area.querySelector(".pool"), textOf(w, q.chips[c].t))); }); return click(check(w)); }
    case "settings": {
      const rows = [...area.querySelectorAll(".setrow")];
      q.rows.forEach((r, k) => {
        if (r.kind === "switch") { const sw = rows[k].querySelector("button.switch"); if ((sw.getAttribute("aria-checked") === "true") !== !!L.values[k]) click(sw); }
        else click(rows[k].querySelectorAll(".seg button")[L.values[k]]);
      });
      return click(check(w));
    }
    case "dial": {
      const boxes = [...area.querySelectorAll(".dial")];
      q.rows.forEach((r, k) => L.clicks[k].forEach((s) => click([...boxes[k].querySelectorAll(".ctl button")].find((b) => b.getAttribute("aria-label") === (s > 0 ? "Increase by " : "Decrease by ") + Math.abs(s)))));
      return click(check(w));
    }
    case "chat": {
      q.steps.forEach((st, i) => { const rep = [...w.document.querySelectorAll(".replies button")].find((b) => norm(b.textContent) === norm(textOf(w, st.replies[L.replies[i]].t))); click(rep); click(check(w)); });
      return;
    }
    case "crossword": {
      Object.entries(L.letters).forEach(([rc, ch]) => { const [r, c] = rc.split(","); click(area.querySelector(`.xc[data-r="${r}"][data-c="${c}"]`)); click(area.querySelector(`.xkeys button[aria-label="${ch}"]`)); });
      return click(check(w));
    }
  }
}

function runEngine(q, L) {
  const dom = new JSDOM('<!doctype html><html><body><main id="app"></main></body></html>', { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
  const w = dom.window;
  w.Element.prototype.scrollIntoView = () => {}; w.scrollTo = () => {};
  let seed = 7; w.Math.random = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  w.CCFR_MODULE = { code: "t", num: 1, title: "T", gameTitle: "T", tagline: "", story: "", minutes: 5, icon: "", revise: "", questions: [JSON.parse(JSON.stringify(q))] };
  w.eval(instrumented);
  w.document.querySelector(".actions button.primary").click(); // "Start the assessment"
  drive(w, q, L);
  const r = w.__r; w.close();
  if (!r) throw new Error("the engine produced no result");
  return r;
}

const cases = []; let failed = 0;
list.forEach((entry, qi) => {
  const modes = ["perfect", ...Array(Math.max(0, per - 1)).fill("random")];
  modes.forEach((mode, ci) => {
    const rnd = mulberry(Number(args.seed ?? 1) * 100003 + qi * 131 + ci);
    const L = logicalFor(entry.question, rnd, mode);
    try { const r = runEngine(entry.question, L); cases.push({ id: entry.id, case: ci, type: entry.question.type, logical: L, js: { score: r.score, gate: r.gate } }); }
    catch (e) { failed++; cases.push({ id: entry.id, case: ci, type: entry.question.type, logical: L, error: e.message }); }
  });
});
const byType = {}; cases.forEach((c) => { byType[c.type] = (byType[c.type] || 0) + 1; });
fs.writeFileSync(args.out, JSON.stringify(cases, null, 1));
console.log(`legacy engine ran ${cases.length - failed} of ${cases.length} cases (${Object.entries(byType).map(([k, v]) => `${k}:${v}`).join(" ")}); ${failed} could not be driven; wrote ${args.out}`);
