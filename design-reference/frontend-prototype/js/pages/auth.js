/* Sign in, enrol, guardian consent, public verification. Frontend preview only: no network, no stored passwords. */
CSFR.ready(() => {
  const { $, $$, esc, session, store, params, toast, t } = CSFR;
  const pageId = document.body.dataset.page;

  /* ---------- Shared form helpers ---------- */
  const form = {
    clear(scope) {
      $$('.field-error', scope).forEach((e) => { e.hidden = true; e.textContent = ''; });
      $$('[aria-invalid]', scope).forEach((e) => e.removeAttribute('aria-invalid'));
      const sum = $('[data-error-summary]'); if (sum) sum.hidden = true;
    },
    error(input, message) {
      input.setAttribute('aria-invalid', 'true');
      const err = document.getElementById(`${input.id}-err`) || input.closest('.field, fieldset')?.querySelector('.field-error');
      if (err) { err.hidden = false; err.innerHTML = `${CSFR.icon('alert', 'icon--sm')}<span>${esc(message)}</span>`; }
      return { input, message };
    },
    summary(errors, title) {
      const sum = $('[data-error-summary]');
      if (!sum || !errors.length) return;
      if (title) $('[data-error-title]', sum).textContent = title;
      $('[data-error-list]', sum).innerHTML = errors.map((e) => `<li><a class="link" href="#${e.input.id}">${esc(e.message)}</a></li>`).join('');
      sum.hidden = false; sum.focus();
    },
  };
  const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());
  $$('[data-reveal-pw]').forEach((btn) => btn.addEventListener('click', () => {
    const input = document.getElementById(btn.getAttribute('aria-controls'));
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(show));
    btn.textContent = t(show ? 'auth.hide' : 'auth.show');
  }));
  const views = (name) => $$('[data-view]').forEach((v) => { v.hidden = v.dataset.view !== name; });
  const segGroup = (attr, onPick) => {
    const btns = $$(`[${attr}]`);
    btns.forEach((b) => b.addEventListener('click', () => { btns.forEach((x) => x.setAttribute('aria-pressed', String(x === b))); onPick(b.getAttribute(attr)); }));
  };

  /* ---------- Sign in ---------- */
  if (pageId === 'signin') {
    let role = params.get('role') === 'mentor' ? 'mentor' : 'learner';
    segGroup('data-role', (r) => { role = r; });
    if (role === 'mentor') $('[data-role="mentor"]').click();
    const go = (v) => { views(v); history.replaceState(null, '', v === 'signin' ? location.pathname + location.search : `#${v}`); $(`[data-view="${v}"] h1`)?.focus?.(); };
    $$('[data-go]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); go(a.dataset.go); }));
    if (location.hash === '#reset') views('reset');

    $('[data-signin-form]').addEventListener('submit', (e) => {
      e.preventDefault();
      const f = e.currentTarget; form.clear(f);
      const email = $('#email'), pw = $('#password'); const errors = [];
      if (!isEmail(email.value)) errors.push(form.error(email, 'Enter the email address you registered with.'));
      if (!pw.value) errors.push(form.error(pw, 'Enter your password.'));
      if (errors.length) return form.summary(errors);
      const stored = store.get('account', null);
      const account = stored && stored.email === email.value.trim() ? stored : null;
      const name = account ? account.name : email.value.split('@')[0].replace(/[._-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      session.signIn({ name, email: email.value.trim(), role, minor: role === 'learner' && !!account?.minor });
      if (account?.minor && account.pendingGuardian && role === 'learner') { location.href = 'guardian.html?view=waiting'; return; }
      const next = params.get('next');
      location.href = next && !next.includes('//') ? next : role === 'mentor' ? 'mentor.html' : 'dashboard.html';
    });
    $('[data-reset-form]').addEventListener('submit', (e) => {
      e.preventDefault(); form.clear(e.currentTarget);
      const email = $('#reset-email');
      if (!isEmail(email.value)) return form.error(email, 'Enter a valid email address.');
      go('sent');
    });
  }

  /* ---------- Register ---------- */
  if (pageId === 'register') {
    let regState = 'open';
    const show = () => views(regState === 'closed' ? 'closed' : 'form');
    segGroup('data-reg-state', (s) => { regState = s; show(); });
    const nameInput = $('#cert-name'), preview = $('[data-cert-preview]');
    const tidy = (v) => v.replace(/\s+/g, ' ').trim();
    nameInput.addEventListener('input', () => { preview.textContent = tidy(nameInput.value).toUpperCase() || '—'; });

    const pw = $('#r-password'), meter = $('[data-pw-meter]'), pwText = $('[data-pw-text]');
    const COMMON = ['password', '12345678', 'qwerty', 'iloveyou', 'password1', 'admin123', '11111111'];
    const scorePw = (v) => {
      if (!v) return 0;
      let s = 0;
      if (v.length >= 8) s++;
      if (v.length >= 12) s++;
      if (/[a-z]/i.test(v) && /\d|\W/.test(v)) s++;
      if (v.length >= 16 || (/\s/.test(v.trim()) && v.length >= 12)) s++;
      if (/^\d+$/.test(v) || COMMON.includes(v.toLowerCase())) s = 1;
      return Math.max(1, Math.min(4, s));
    };
    pw.addEventListener('input', () => {
      const s = scorePw(pw.value); meter.dataset.score = String(s);
      pwText.textContent = !pw.value ? '' : ['', 'Too weak', 'Getting there', 'Good', 'Strong'][s];
    });

    const dob = $('#r-dob'), guardian = $('[data-guardian]');
    const ageOf = (iso) => { if (!iso) return null; const d = new Date(iso), n = new Date(); let a = n.getFullYear() - d.getFullYear(); if (n < new Date(n.getFullYear(), d.getMonth(), d.getDate())) a--; return a; };
    dob.max = new Date().toISOString().slice(0, 10);
    dob.addEventListener('change', () => { const a = ageOf(dob.value); guardian.hidden = !(a >= 16 && a <= 17); });

    $('[data-register-form]').addEventListener('submit', (e) => {
      e.preventDefault();
      const f = e.currentTarget; form.clear(f);
      const errors = [];
      if (tidy(nameInput.value).length < 2) errors.push(form.error(nameInput, 'Enter your full name exactly as it should appear on your certificate.'));
      const email = $('#r-email');
      if (!isEmail(email.value)) errors.push(form.error(email, 'Enter a valid email address, for example name@example.com.'));
      if (pw.value.length < 8) errors.push(form.error(pw, 'Your password needs at least 8 characters.'));
      else if (/^\d+$/.test(pw.value) || COMMON.includes(pw.value.toLowerCase())) errors.push(form.error(pw, 'Choose a less common password. A short sentence works well.'));
      const age = ageOf(dob.value);
      if (age === null || Number.isNaN(age)) errors.push(form.error(dob, 'Enter your date of birth.'));
      const minor = age >= 16 && age <= 17;
      if (minor) {
        const gn = $('#g-name'), ge = $('#g-email');
        if (tidy(gn.value).length < 2) errors.push(form.error(gn, 'Enter your parent or guardian’s full name.'));
        if (!isEmail(ge.value)) errors.push(form.error(ge, 'Enter your parent or guardian’s email address.'));
        else if (ge.value.trim().toLowerCase() === email.value.trim().toLowerCase()) errors.push(form.error(ge, 'Your guardian needs their own email address, not yours.'));
      }
      const batch = $('#r-batch');
      if (!batch.value) errors.push(form.error(batch, 'Choose the batch you are joining.'));
      $$('input[type="checkbox"][required]', f).forEach((c) => { if (!c.checked) errors.push(form.error(c, c.name === 'privacy' ? 'Please confirm you have read the privacy notice.' : 'Please agree to the terms of use.')); });
      if (errors.length) return form.summary(errors, 'Please fix these before continuing');

      if (age < 16) { views('young'); scrollTo(0, 0); return; }
      if (regState === 'race') {
        // Server re-checks is_accepting on submit; values are kept.
        const err = form.error(batch, 'Sorry, this batch is not accepting registrations.');
        form.summary([err], 'This batch just closed');
        return;
      }
      store.set('account', { name: tidy(nameInput.value), email: email.value.trim(), minor, pendingGuardian: minor, lang: $('#r-lang').value });
      $('[data-inbox-email]').textContent = email.value.trim();
      $('[data-inbox-guardian]').hidden = !minor;
      views('inbox'); scrollTo(0, 0);
    });
    $('[data-demo-verify]').addEventListener('click', () => {
      const acc = store.get('account', null); if (!acc) return;
      session.signIn({ name: acc.name, email: acc.email, role: 'learner', minor: acc.minor });
      if (acc.lang && acc.lang !== CSFR.lang) store.set('lang', acc.lang);
      location.href = acc.pendingGuardian ? 'guardian.html?view=waiting' : 'dashboard.html?welcome=1';
    });
  }

  /* ---------- Guardian ---------- */
  if (pageId === 'guardian') {
    const acc = store.get('account', null);
    if (acc) $('[data-learner-name]').textContent = acc.name;
    const titles = { consent: ['Confirm consent for your child', 'A learner aged 16 or 17 named you as their parent or guardian for the Community Cyber First Responder programme.'], waiting: ['Almost there', 'Your account is ready. We just need your parent or guardian to confirm.'] };
    const setView = (v) => { views(v); $('[data-g-title]').textContent = titles[v][0]; $('[data-g-lede]').textContent = titles[v][1]; };
    segGroup('data-gview', setView);
    if (params.get('view') === 'waiting') $('[data-gview="waiting"]').click();
    $('[data-consent-form]').addEventListener('submit', (e) => {
      e.preventDefault(); form.clear(e.currentTarget);
      const n = $('#cg-name'), d = $('[data-declare]'); const errs = [];
      if (n.value.trim().length < 2) errs.push(form.error(n, 'Enter your full name.'));
      if (!d.checked) errs.push(form.error(d, 'Please confirm the declaration.'));
      if (errs.length) return;
      e.currentTarget.hidden = true; $('[data-consent-done]').hidden = false;
      if (acc) store.set('account', { ...acc, pendingGuardian: false });
    });
    $('[data-decline]').addEventListener('click', () => { $('[data-consent-form]').hidden = true; $('[data-consent-declined]').hidden = false; });
    $('[data-resend]').addEventListener('click', () => toast('If the email hasn’t arrived, we can resend it once every 24 hours.'));
    $('[data-demo-approve]').addEventListener('click', () => { if (acc) store.set('account', { ...acc, pendingGuardian: false }); location.href = 'dashboard.html?welcome=1'; });
  }

  /* ---------- Verify (QR landing; no lookup by number) ---------- */
  if (pageId === 'verify') {
    const code = params.get('code') || 'K7QM2XR9TD';
    const states = {
      valid: { c: 'var(--teal)', icon: 'check-circle', label: 'Valid certificate', rows: [['Name', 'ASHA R. DESAI'], ['Qualification', 'Community Cyber First Responder'], ['Grade', 'B'], ['Issued', '12 March 2027'], ['Status', 'Valid']], note: `Verification code ${code}. Sample data for this preview.` },
      revoked: { c: 'var(--danger)', icon: 'x', label: 'Revoked', rows: [['Qualification', 'Community Cyber First Responder'], ['Issued', '12 March 2027'], ['Status', 'Revoked by the programme']], note: 'This certificate is no longer valid. Contact the programme team if you have questions.' },
      erased: { c: 'var(--blue)', icon: 'info', label: 'Issued', rows: [['Qualification', 'Community Cyber First Responder'], ['Issued', '12 March 2027'], ['Holder', 'Holder details removed at their request']], note: 'This certificate was issued. The holder’s personal details have been removed.' },
      none: { c: 'var(--mustard-deep)', icon: 'qr', label: 'Scan a certificate’s QR code', rows: [], note: 'Open this page by scanning the QR code printed on a CSFR certificate. The code takes you straight to that certificate’s record.' },
    };
    const render = (k) => {
      const s = states[k];
      const st = $('[data-v-status]'); st.style.setProperty('--c', s.c);
      st.innerHTML = `${CSFR.icon(s.icon)}<span>${esc(s.label)}</span>`;
      $('[data-v-details]').innerHTML = s.rows.map(([dt, dd]) => `<div><dt>${esc(dt)}</dt><dd>${esc(dd)}</dd></div>`).join('');
      $('[data-v-note]').textContent = s.note;
    };
    segGroup('data-vstate', render);
    const initial = params.get('state') || (params.get('code') ? 'valid' : 'valid');
    $(`[data-vstate="${initial}"]`)?.click();
  }
});
