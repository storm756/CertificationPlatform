/* CSFR core: theme, language, shared header/footer, demo session + progress, helpers.
   Every page loads i18n.js then core.js. Pages call CSFR.ready(fn) for their own logic.
   Demo state lives in localStorage only. No passwords are ever stored. */
(() => {
  'use strict';
  const root = document.documentElement;
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(`csfr.${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(`csfr.${key}`, JSON.stringify(value)); } catch { /* private mode */ } },
    del(key) { try { localStorage.removeItem(`csfr.${key}`); } catch { /* ignore */ } },
  };

  /* ---------- Icons (Lucide, ISC licence) ---------- */
  const ICONS = {
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    code: '<path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/><path d="m14.5 4-5 16"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    'shield-alert': '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4M12 16h.01"/>',
    award: '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
    arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'arrow-left': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'arrow-up': '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    'arrow-down': '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    'check-circle': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    circle: '<circle cx="12" cy="12" r="10"/>',
    'circle-dot': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3.5"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    phone: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    'phone-call': '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    unlock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    retry: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    qr: '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    chat: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    crosshair: '<circle cx="12" cy="12" r="10"/><path d="M22 12h-4M6 12H2M12 6V2M12 22v-4"/>',
    columns: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    list: '<path d="M10 12h11M10 18h11M10 6h11M4 10h2M4 6h1v4"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
    pointer: '<path d="M14 4.1 12 6M5.1 8l-2.9-.8M6 12l-1.9 2M7.2 2.2 8 5.1"/><path d="M9.037 9.69a.498.498 0 0 1 .653-.653l11 4.5a.5.5 0 0 1-.074.949l-4.349 1.041a1 1 0 0 0-.74.739l-1.04 4.35a.5.5 0 0 1-.95.074z"/>',
    blocks: '<rect width="7" height="7" x="14" y="3" rx="1"/><path d="M10 21V8a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1H3"/>',
    sliders: '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
    gauge: '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    grid: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    'square-check': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'user-check': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    trend: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    minus: '<path d="M5 12h14"/>',
    plus: '<path d="M5 12h14M12 5v14"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    'alert-triangle': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    lightbulb: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6M10 22h4"/>',
    mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    wifi: '<path d="M12 20h.01M2 8.82a15 15 0 0 1 20 0M5 12.86a10 10 0 0 1 14 0M8.5 16.43a5 5 0 0 1 7 0"/>',
    'wifi-off': '<path d="M12 20h.01M8.5 16.43a5 5 0 0 1 7 0M5 12.86a10 10 0 0 1 5.17-2.69M19 12.86a10 10 0 0 0-2.007-1.523M2 8.82a15 15 0 0 1 4.177-2.643M22 8.82a15 15 0 0 0-11.288-3.764M2 2l20 20"/>',
    home: '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    pause: '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8M16 13H8M16 17H8"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    video: '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    chart: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    calendar: '<path d="M8 2v4M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    stop: '<path d="M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z"/>',
    save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
    megaphone: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    cap: '<path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>',
    eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    star: '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
  };
  const icon = (name, cls = '') => `<svg class="icon ${cls}" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  const sprite = () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'sprite'); svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = Object.entries(ICONS).map(([n, p]) => `<symbol id="i-${n}" viewBox="0 0 24 24">${p}</symbol>`).join('');
    document.body.prepend(svg);
  };

  /* ---------- Language ---------- */
  const LANGS = [
    { code: 'en', label: 'English', short: 'EN' },
    { code: 'hi', label: 'हिन्दी', short: 'हिन्दी' },
    { code: 'mr', label: 'मराठी', short: 'मराठी' },
    { code: 'gu', label: 'ગુજરાતી', short: 'ગુજરાતી' },
  ];
  const IDX = { en: 0, hi: 1, mr: 2, gu: 3 };
  const urlLang = new URLSearchParams(location.search).get('lang');
  if (urlLang && IDX[urlLang] !== undefined) store.set('lang', urlLang);
  const lang = store.get('lang', 'en');
  root.lang = lang;

  const t = (key, fallback) => {
    const row = (window.CSFR_UI || {})[key];
    if (!row) return fallback ?? key;
    return row[IDX[lang]] || row[0];
  };
  /* Content strings: legacy drafts + module titles. Missing → English (architecture §14). */
  const tc = (text) => {
    if (lang === 'en' || !text) return text;
    const extra = (window.CSFR_UI_CONTENT || {})[lang] || {};
    const table = (window.CSFR_I18N || {})[lang] || {};
    return extra[text] || table[text] || text;
  };
  /* Page phrases (js/phrases.js), keyed by exact English text; {0} placeholders. */
  const P = (text, ...args) => {
    const row = lang !== 'en' && (window.CSFR_PHRASES || {})[text];
    const out = row ? (row[IDX[lang] - 1] || text) : text;
    return args.reduce((s, a, i) => s.replaceAll(`{${i}}`, a), out);
  };
  const SKIP = 'script,style,textarea,input,select,option,[data-no-tr],.qcard,.spot-msg,.transcript';
  /* Text lookup order: exact phrase → lesson-content table → {0} pattern phrases (most specific first). */
  let PATTERNS = null;
  const patterns = () => {
    if (PATTERNS) return PATTERNS;
    const esc = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    PATTERNS = Object.keys(window.CSFR_PHRASES || {}).filter((k) => /\{\d\}/.test(k))
      .map((k) => ({ k, lit: k.replace(/\{\d\}/g, '').length, re: new RegExp(`^${k.split(/(\{\d\})/).map((part) => (/^\{\d\}$/.test(part) ? '(.+?)' : esc(part))).join('')}$`), order: [...k.matchAll(/\{(\d)\}/g)].map((m) => Number(m[1])) }))
      .sort((x, y) => y.lit - x.lit);
    return PATTERNS;
  };
  const trText = (key) => {
    if (!key || lang === 'en') return null;
    if ((window.CSFR_PHRASES || {})[key]) return P(key);
    const c = tc(key); if (c !== key) return c;
    /* A placeholder may hold a number, already-translated text, text we can translate, or (for the
       patterns listed in CSFR_PHRASE_FREE) a name or date. Anything else means the pattern matched
       too loosely ("Module {0}" against "Module 6 is at 44%"), so try the next one. */
    const free = window.CSFR_PHRASE_FREE || [];
    for (const p of patterns()) {
      const m = key.match(p.re); if (!m) continue;
      const args = []; let ok = true;
      p.order.forEach((idx, i) => {
        const v = m[i + 1]; const tv = trText(v);
        if (!tv && /[A-Za-z]{2,}/.test(v) && !free.includes(p.k)) ok = false;
        args[idx] = tv || v;
      });
      if (ok) return P(p.k, ...args);
    }
    return null;
  };
  const trNode = (node) => {
    const raw = node.nodeValue; const key = raw.trim();
    const out = trText(key); if (out && out !== key) node.nodeValue = raw.replace(key, out);
  };
  const translateDom = (scope = document.body) => {
    if (lang === 'en' || !window.CSFR_PHRASES || !scope) return;
    if (scope.nodeType === 3) { if (!scope.parentElement?.closest(SKIP)) trNode(scope); return; }
    if (scope.nodeType !== 1 || scope.closest?.(SKIP)) return;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(trNode);
    [scope, ...scope.querySelectorAll('[placeholder],[aria-label],[title]')].forEach((el) => {
      ['placeholder', 'aria-label', 'title'].forEach((a) => { const v = el.getAttribute?.(a); const o = v && trText(v.trim()); if (o && o !== v.trim()) el.setAttribute(a, o); });
    });
  };
  const watchDom = () => {
    if (lang === 'en' || !window.CSFR_PHRASES) return;
    new MutationObserver((muts) => muts.forEach((m) => m.addedNodes.forEach((n) => translateDom(n)))).observe(document.body, { childList: true, subtree: true });
  };
  const isTranslated = (text) => lang !== 'en' && tc(text) !== text;
  const applyI18n = (scope = document) => {
    scope.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n, el.textContent); });
    scope.querySelectorAll('[data-i18n-attr]').forEach((el) => {
      el.dataset.i18nAttr.split(';').forEach((pair) => { const [attr, key] = pair.split(':'); el.setAttribute(attr, t(key, el.getAttribute(attr))); });
    });
  };
  const draftTag = () => (lang === 'en' ? '' : `<span class="draft-tag">${icon('info', 'icon--sm')}${esc(t('lang.draft'))}</span>`);

  /* ---------- Theme ---------- */
  const setTheme = (theme) => {
    root.dataset.theme = theme;
    store.set('theme', theme);
    document.querySelectorAll('.theme-toggle').forEach((b) => {
      b.setAttribute('aria-label', t(theme === 'dark' ? 'theme.light' : 'theme.dark'));
      b.setAttribute('aria-pressed', String(theme === 'dark'));
    });
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0a1326' : '#071a3d');
  };

  /* ---------- Helpers ---------- */
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = (sel, scope = document) => scope.querySelector(sel);
  const $$ = (sel, scope = document) => [...scope.querySelectorAll(sel)];
  const params = new URLSearchParams(location.search);
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const loadScript = (src) => new Promise((resolve, reject) => {
    if (document.querySelector(`script[data-src="${src}"]`)) return resolve();
    const s = document.createElement('script');
    s.src = src; s.dataset.src = src; s.onload = () => resolve(); s.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.append(s);
  });
  const loadModule = async (n) => { await loadScript(`data/module-${n}.js`); return (window.CSFR_MODULES || {})[n]; };
  const loadCatalog = async () => { await loadScript('data/catalog.js'); return window.CSFR_CATALOG; };

  let toastTimer;
  const toast = (message) => {
    let el = $('[data-toast]');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; el.setAttribute('role', 'status'); el.dataset.toast = ''; document.body.append(el); }
    el.textContent = message; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
  };
  const confirmDialog = ({ title, body, confirm = t('c.continue'), cancel = t('c.cancel'), danger = false }) => new Promise((resolve) => {
    const d = document.createElement('dialog');
    d.className = 'modal';
    d.innerHTML = `<form method="dialog" class="modal__body"><h2 style="font-size:1.5rem">${esc(title)}</h2><div class="muted">${body}</div>
      <div class="modal__actions"><button class="btn btn-ghost" value="no">${esc(cancel)}</button><button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" value="yes">${esc(confirm)}</button></div></form>`;
    document.body.append(d);
    let done = false;
    const finish = (value) => { if (done) return; done = true; if (d.open) d.close(); d.remove(); resolve(value); };
    d.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); finish(e.submitter?.value === 'yes'); });
    d.addEventListener('cancel', (e) => { e.preventDefault(); finish(false); });
    d.addEventListener('close', () => finish(d.returnValue === 'yes'));
    d.showModal();
    d.querySelector('button[value="yes"]').focus();
  });

  /* ---------- Demo session & progress ---------- */
  const session = {
    get: () => store.get('session', null),
    signIn: (s) => store.set('session', { name: s.name, email: s.email, role: s.role || 'learner', minor: !!s.minor }),
    signOut: () => store.del('session'),
  };
  const progress = {
    all: () => store.get('progress', { units: {}, attempts: {}, pretest: false }),
    save: (p) => store.set('progress', p),
    unitDone: (id) => !!progress.all().units[id],
    markUnit(id) { const p = progress.all(); p.units[id] = Date.now(); progress.save(p); },
    attempts: (id) => progress.all().attempts[id] || [],
    addAttempt(id, a) { const p = progress.all(); (p.attempts[id] = p.attempts[id] || []).push(a); progress.save(p); },
    draft: (id) => store.get(`draft.${id}`, null),
    saveDraft: (id, d) => store.set(`draft.${id}`, d),
    clearDraft: (id) => store.del(`draft.${id}`),
    reset: () => { Object.keys(localStorage).filter((k) => k.startsWith('csfr.draft.') || k === 'csfr.progress').forEach((k) => localStorage.removeItem(k)); },
  };

  /* Unit ids per module: film, t1..tN, handout, check, practice, mcq, int */
  const unitsFor = (mod) => {
    const n = mod.n;
    const units = [];
    if (mod.hasFilm !== false) units.push({ id: `m${n}:film`, kind: 'film', group: 'watch', title: 'Module film', minutes: 2 });
    (mod.topics || []).forEach((title, i) => units.push({ id: `m${n}:t${i + 1}`, kind: 'reading', group: 'read', title, minutes: 10, index: i }));
    units.push({ id: `m${n}:handout`, kind: 'handout', group: 'handout', title: 'Module handout', minutes: 15 });
    units.push({ id: `m${n}:check`, kind: 'check', group: 'practise', title: 'Myth or fact?', minutes: 3 });
    units.push({ id: `m${n}:practice`, kind: 'practice', group: 'practise', title: 'Practice quiz', minutes: 10 });
    if (mod.interactivePracticeOnly) units.push({ id: `m${n}:xw`, kind: 'crossword', group: 'practise', title: 'Crossword practice', minutes: 15 });
    return units;
  };
  const partsFor = (mod) => [
    { id: `m${mod.n}:mcq`, part: 'mcq', title: t('mod.partA'), marks: 50, count: mod.mcqCount },
    { id: `m${mod.n}:int`, part: 'int', title: t('mod.partB'), marks: 50, count: mod.interactivePracticeOnly ? 0 : mod.challengeCount, pending: !!mod.interactivePracticeOnly },
  ];
  const moduleCompletion = (mod) => {
    const units = unitsFor(mod);
    const done = units.filter((u) => progress.unitDone(u.id)).length;
    const parts = partsFor(mod);
    const submitted = parts.filter((p) => progress.attempts(p.id).some((a) => a.allAnswered)).length;
    return { done, total: units.length, submitted, parts: parts.length, pct: Math.round(((done + submitted) / (units.length + parts.length)) * 100) };
  };

  /* ---------- Shell ---------- */
  const NAV = {
    guest: [['index.html', 'nav.home', 'home'], ['modules.html', 'nav.modules', 'layers'], ['help.html', 'nav.help', 'help']],
    learner: [['dashboard.html', 'nav.progress', 'chart'], ['modules.html', 'nav.modules', 'layers'], ['final.html', 'nav.final', 'flag'], ['certificate.html', 'nav.certificate', 'award'], ['help.html', 'nav.help', 'help']],
    mentor: [['mentor.html', 'nav.mentor', 'users'], ['modules.html', 'nav.modules', 'layers'], ['help.html', 'nav.help', 'help']],
  };
  const page = (location.pathname.split('/').pop() || 'index.html');
  const renderHeader = () => {
    const host = $('[data-shell="header"]');
    if (!host) return;
    const s = session.get();
    const links = NAV[s ? s.role : 'guest'];
    const current = document.body.dataset.nav || page;
    const initials = s ? s.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase() : '';
    host.outerHTML = `
    <a class="skip-link" href="#main">${esc(t('nav.skip'))}</a>
    <header class="site-header" data-header>
      <div class="header-inner">
        <a class="brand-lockup" href="index.html" aria-label="${esc(P('Community Cyber First Responder'))} — ${esc(t('nav.home'))}">
          <img class="brand-logo brand-logo--anchor blend" src="assets/shah-anchor-logo.png" width="245" height="254" alt="Shah &amp; Anchor">
          <span class="brand-rule" aria-hidden="true"></span>
          <img class="brand-logo brand-logo--cyberpeace" src="assets/cyberpeace-logo.png" width="284" height="284" alt="CyberPeace">
          <span class="brand-copy">A Shah &amp; Anchor × CyberPeace<br>initiative for community cybersecurity</span>
        </a>
        <div class="header-tools">
          <button class="icon-btn theme-toggle" type="button" data-theme-toggle>${icon('sun', 'icon-sun')}${icon('moon', 'icon-moon')}</button>
          <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="primary-nav"><span class="nav-toggle__label">${esc(t('nav.menu'))}</span><span class="nav-toggle__lines" aria-hidden="true"><i></i><i></i><i></i></span></button>
        </div>
        <nav class="primary-nav" id="primary-nav" aria-label="Primary">
          <ul class="nav-links">${links.map(([href, key, ic]) => `<li><a href="${href}"${current === href ? ' aria-current="page"' : ''}>${icon(ic)}${esc(t(key))}</a></li>`).join('')}</ul>
          <div class="nav-actions">
            <label class="lang-select">${icon('globe')}<span class="sr-only">${esc(t('lang.label'))}</span>
              <select data-lang-select>${LANGS.map((l) => `<option value="${l.code}" lang="${l.code}"${l.code === lang ? ' selected' : ''}>${l.short}</option>`).join('')}</select>${icon('chevron', 'icon--sm')}</label>
            ${s ? `<a class="user-chip" href="${s.role === 'mentor' ? 'mentor.html' : 'dashboard.html'}"><span class="avatar" aria-hidden="true">${esc(initials)}</span><span>${esc(s.name.split(' ')[0])}</span></a>
                   <button class="btn btn-outline btn-sm" type="button" data-signout>${icon('logout')}${esc(t('nav.signout'))}</button>`
                : `<a class="btn btn-outline" href="signin.html">${esc(t('nav.signin'))}</a><a class="btn btn-primary" href="register.html">${esc(t('nav.enrol'))}</a>`}
          </div>
        </nav>
      </div>
    </header>${lang !== 'en' ? `<div class="lang-banner" role="note">${icon('info', 'icon--sm')}<span>${esc(t('lang.banner'))}</span></div>` : ''}`;
  };
  const renderFooter = () => {
    const host = $('[data-shell="footer"]');
    if (!host) return;
    host.outerHTML = `
    <footer class="site-footer">
      <div class="shell footer-inner">
        <div class="footer-brand"><p><strong>Community Cyber First Responder</strong><br>${esc(t('footer.tagline'))}</p></div>
        <nav class="footer-nav" aria-label="${esc(t('footer.programme'))}"><h2>${esc(t('footer.programme'))}</h2>
          <a href="modules.html">${esc(t('nav.modules'))}</a><a href="final.html">${esc(t('nav.final'))}</a><a href="help.html">${esc(t('nav.help'))}</a><a href="verify.html">${esc(t('footer.verify'))}</a></nav>
        <nav class="footer-nav" aria-label="${esc(t('footer.policies'))}"><h2>${esc(t('footer.policies'))}</h2>
          <a href="privacy.html">${esc(t('footer.privacy'))}</a><a href="terms.html">${esc(t('footer.terms'))}</a><a href="grievance.html">${esc(t('footer.grievance'))}</a>
          <a href="mailto:support@cyberfirstresponse.io">${icon('mail', 'icon--sm')} support@cyberfirstresponse.io</a></nav>
        <div class="footer-col"><h2>${esc(t('footer.languages'))}</h2>
          <p>${LANGS.map((l) => `<a href="?lang=${l.code}" lang="${l.code}" style="text-decoration:none">${l.label}</a>`).join(' · ')}</p></div>
        <div class="footer-base"><p>${esc(t('footer.joint'))}</p><p><a href="mentor.html" style="color:inherit">Staff: mentor dashboard</a></p></div>
      </div>
    </footer>`;
  };

  const wireShell = () => {
    const header = $('[data-header]');
    if (header) {
      const onScroll = () => header.classList.toggle('is-scrolled', scrollY > 8);
      onScroll(); addEventListener('scroll', onScroll, { passive: true });
      const toggle = $('.nav-toggle', header), nav = $('#primary-nav');
      const setNav = (open, focusToggle) => { toggle.setAttribute('aria-expanded', String(open)); nav.classList.toggle('is-open', open); document.body.classList.toggle('nav-open', open); if (open) $('a, select', nav)?.focus(); if (!open && focusToggle) toggle.focus(); };
      toggle.addEventListener('click', () => setNav(toggle.getAttribute('aria-expanded') !== 'true'));
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && nav.classList.contains('is-open')) setNav(false, true); });
      matchMedia('(min-width: 72rem)').addEventListener('change', () => setNav(false));
    }
    $$('[data-theme-toggle]').forEach((b) => b.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark')));
    setTheme(root.dataset.theme || 'light');
    $$('[data-lang-select]').forEach((sel) => sel.addEventListener('change', () => { store.set('lang', sel.value); const u = new URL(location.href); u.searchParams.delete('lang'); location.href = u.toString(); }));
    $$('[data-signout]').forEach((b) => b.addEventListener('click', () => { session.signOut(); location.href = 'index.html'; }));
    document.addEventListener('click', (e) => { const d = e.target.closest('[data-demo]'); if (d) { e.preventDefault(); toast(d.dataset.demo); } });
  };

  const reveal = () => {
    const items = $$('[data-reveal]');
    if (reduceMotion || !('IntersectionObserver' in window)) { items.forEach((i) => i.classList.add('is-visible')); return; }
    const io = new IntersectionObserver((entries, obs) => entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add('is-visible'); obs.unobserve(en.target); } }), { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });
    items.forEach((i) => io.observe(i));
  };

  /* Page guard: learner pages need a session, mentor pages a mentor. Demo only. */
  const requireRole = (role) => {
    const s = session.get();
    if (!s || (role && s.role !== role)) { location.replace(`signin.html?next=${encodeURIComponent(page + location.search)}${role === 'mentor' ? '&role=mentor' : ''}`); return false; }
    return true;
  };

  const readyFns = [];
  const ready = (fn) => readyFns.push(fn);
  const boot = async () => {
    sprite();
    if (lang !== 'en') { try { await Promise.all([loadScript(`data/i18n/${lang}.js`), loadScript('js/phrases.js')]); } catch { /* content stays English */ } }
    renderHeader(); renderFooter(); applyI18n(); wireShell();
    for (const fn of readyFns) { try { await fn(); } catch (err) { console.error(err); toast('Something went wrong loading this page. Please refresh.'); } }
    applyI18n(); translateDom(document.body); watchDom(); reveal();
  };

  window.CSFR = { store, t, tc, P, translateDom, isTranslated, draftTag, lang, LANGS, icon, esc, $, $$, params, reduceMotion, loadScript, loadModule, loadCatalog, toast, confirmDialog, session, progress, unitsFor, partsFor, moduleCompletion, requireRole, ready, page, applyI18n };
  if (document.readyState === 'complete') boot(); else document.addEventListener('DOMContentLoaded', boot);
})();
