# Build stages

**How to run a stage:**
1. Start a **new** Claude Code session in the repo.
2. Paste that stage's prompt.
3. Let Claude plan, then build, until every "Done when" item passes.
4. Open a PR named `Stage N: <name>`.

Each stage builds on the previous one, so don't skip ahead. Use Opus for stages 2, 3, 5 and 7 (integrity-critical) and Sonnet for the rest.

**Progress (10 Nov 2026):**

| Stage | Status |
| --- | --- |
| 0 | ✅ Done, merged |
| 1 | 🟡 Built, PR #2 open; 3 finish items in `docs/STATUS.md` |
| 1.5 | 🟡 Built locally on `stage-1-5-ui` (UI shell from the approved prototype); see `docs/STATUS.md` |
| 2 | 🟡 Built locally on `stage-2`; see `docs/STATUS.md` |
| 3 | 🟡 Built locally on `stage-3`; see `docs/STATUS.md` |
| 4 | 🟡 Built locally on `stage-4`; see `docs/STATUS.md` |
| 5 to 10 | ⬜ |

**Every page from Stage 1.5 onwards** takes its layout from `design-reference/frontend-prototype/`. The table below says which prototype file to copy for each stage.

| Stage | Prototype files to match |
| --- | --- |
| 1.5 | `css/base.css`, `css/app.css`, `js/core.js` (header, footer, language select, toasts, confirm dialog), `signin.html`, `register.html`, `guardian.html`, `mentor.html` (batch controls only) |
| 2 and 3 | `assessment.html` + `js/pages/assessment.js` + `js/engine.js` (intro, attempt, question map, mark-for-review, review-before-submit, result) |
| 4 | `modules.html`, `module.html`, `unit.html` + `js/pages/unit.js` (course player with outline sidebar) |
| 5 | `dashboard.html`, `final.html` + `js/pages/learner.js` |
| 6 | `mentor.html` + `js/pages/mentor.js` |
| 7 | `certificate.html`, `verify.html` |
| 9 | `index.html` + `css/landing.css`, `help.html`, `privacy.html`, `terms.html`, `grievance.html`, `404.html`, `500.html` |

**VPS:** Hostinger KVM 2, Ubuntu 24.04, IP `189.72.144.197`, hostname `srv2130801.hstgr.cloud`. The lead gives you SSH access (key only).

---

## Stage 0: Foundation and server

**Build**
- Repo layout as in architecture §4:
  - Django 5.2
  - settings split into dev, staging and prod, read from env vars
  - **custom `User` with email login in the very first migration**
  - `ruff`, `pytest-django`
  - GitHub Actions CI running lint and tests against Postgres
- Packages: django-allauth (+ `allauth.mfa`), django-unfold, django-simple-history, django-ratelimit, sentry-sdk.
- `deploy/compose.dev.yml` (web, db, mailpit) and `deploy/compose.yml` (caddy, web/gunicorn, db, cron). Containers run as non-root.
- The Postgres roles `csfr_owner` (migrations) and `csfr_app` (runtime).
- **Server hardening:**
  - a non-root `deploy` user
  - SSH keys only (root login and passwords off)
  - `ufw` allows 22, 80 and 443
  - fail2ban, unattended-upgrades, Docker
- **DNS** (the lead does this in Hostinger DNS Manager): A records for `cyberfirstresponse.io`, `www` and `staging` → `189.72.144.197`. Caddy gets the TLS certificates.
- Staging and prod as separate stacks, with separate `.env` files (separate SECRET_KEY, DB and email settings). Staging email goes to Mailpit, never Brevo.
- `deploy/deploy.sh <staging|prod>`: pull → build → migrate (as owner) → collectstatic → restart. Prod takes a DB dump first.
- **Backups:**
  - `cron` runs an hourly `pg_dump`, encrypted with `age` to a public key, uploaded off-site (Backblaze B2 bucket with object lock, write-only key)
  - a nightly media sync
  - `deploy/restore.sh` restores into a throwaway stack
- Staff must set up TOTP (allauth.mfa) before reaching the admin.

**Done when**
- [ ] `https://staging.cyberfirstresponse.io` loads with HTTPS. Login, signup and logout work. An admin login forces 2FA setup.
- [ ] CI is green. `ssh root@…` is refused.
- [ ] A backup appears off-site, and `restore.sh` restores it into a throwaway stack.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §2–§4, §16–§17. Implement Stage 0 from docs/build-stages.md: project skeleton,
> custom email User, allauth + MFA, unfold admin, Docker Compose for dev/staging/prod with Caddy, server hardening script, deploy script, encrypted
> off-site backups with a restore script, and CI. Ask me for anything you need from the server or DNS.

---

## Stage 1: Accounts, batches, registration

**Build** (architecture §5, §6 People/Batches, §7)
- `Profile` (certificate_name, date of birth, language), `ConsentRecord`, `GuardianConsent`.
- `Batch`, `BatchMentor`, `Enrolment`. `batches/rules.py::is_accepting(batch, now)`. `batches/scoping.py::batches_for(user)`.
- The registration flow from §7.2:
  - "closed" page when nothing is open
  - the server re-checks inside a locked transaction
  - an age gate: under 16 is refused, 16–17 waits for the guardian
  - the certificate-name preview
  - email normalisation as a setting (on in prod, off on staging)
- The guardian email → confirmation page → activate.
- Email budgets (§7.2), and a "sent today" counter on the admin dashboard.
- Mentor pages:
  - my batches
  - create a batch
  - open/close, window, seats
  - roster with new sign-ups
  - move a learner (only between their own batches)
  - a one-time reset link (§7.4)
  - change the certificate name
- Audit events for all of the above.

**Done when**
- [ ] Journeys 1–4 in architecture §18 pass as automated tests.
- [ ] A test proves a mentor can't see or move learners in another batch.
- [ ] Posting the form to a closed batch is refused.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §5–§7. Implement Stage 1 from docs/build-stages.md: profiles, consent, guardian consent for
> 16–17, batches with is_accepting(), the registration flow, email budgets, and the mentor batch pages, with tests for journeys 1–4.

**Finish items (added after review; full spec in `docs/STATUS.md`):**
- [ ] Claude: the `tasks` service and the `run_periodic` loop with the daily `purge_unverified` (D27), with tests.
- [ ] Claude: the "move learner" responses: 400 for no batch chosen, 403 + audit for any batch not the mentor's own, with tests.
- [ ] **Person only:** a person reviews and merges PR #2, deploys staging, and `/register` loads on staging.

---

## Stage 1.5: UI shell and components (from the approved prototype)

**Why:** every later stage adds pages. Building the shared look once, as Django templates and CSS, keeps them all consistent and
stops each stage from restyling by hand.

**Build**
- The prototype is already in `design-reference/frontend-prototype/` (the README copy step). Check that no `data/`, `assets/people/` or prompt file was committed.
- **Fold the decisions into `docs/architecture.md`** (the table at the end of `docs/decisions.md`), now that `stage-1` is merged.
- **Design tokens** in `static/css/tokens.css`: the prototype's colours, type scale, spacing, radii and shadows. One light theme, **no night mode** (D21).
- **Self-hosted fonts from Google Fonts (OFL licence; commit `OFL.txt` next to them):**
  * Baloo 2, weights 500–800, Latin and Devanagari (already in the prototype)
  * Hind, weights 400/500/600, Latin and Devanagari (already in the prototype)
  * **Baloo Bhai 2** (500–800) and **Hind Vadodara** (400/500/600) for Gujarati (not in the prototype: download the woff2 subsets)

  Leave out the prototype's unused Epilogue files. Use `unicode-range` per script and `font-display: swap`.
- **`templates/base.html`:**
  - skip link
  - header with the SAKEC and CyberPeace logos
  - a slot for the programme emblem (D23)
  - the main nav for guest, learner and mentor
  - a language select wired to Django's `set_language`: a cookie for guests, `Profile.preferred_language` for signed-in users. The actual translations come in Stage 8.
  - footer
  - toasts and a confirm dialog
  - the programme name from `settings.PROGRAMME_NAME` ("Community Cyber First Responder") and `PROGRAMME_SHORT` ("CCFR"), added to settings in this stage
- **Logos:** the SAKEC crest and the CyberPeace logo, both clearly readable on a phone. **Which CyberPeace file to use is the builder's call:** the prototype's
  square mark, or the wide lockup in `design-reference/cyberpeace-logo-wide.webp`. Ask in chat if unsure. Never recolour or crop them.
- **Component partials** (`templates/components/`):
  - buttons (primary mustard, secondary outline, quiet)
  - card, chip/status badge, progress ring and bar
  - module card, stage strip (Learn → Practise → Assess → Certify)
  - form field with error, empty state, alert
  - question-map palette, "Saved / Saving / Offline" pill, count-up timer
- **A staff-only `/styleguide` page** that renders every component in every state. Its sample Hindi, Marathi and Gujarati strings are **hard-coded in the
  styleguide template only**, to prove the fonts and wrapping. This is what the reviewer checks.
- **Check tooling:** a `tools/screenshots.mjs` Playwright script that takes 390px and 1366px screenshots of given URLs, plus an `@axe-core/playwright`
  accessibility check on the same pages. Every later PR uses it.
- **Restyle the Stage 0–1 pages:** sign-in, register (with the certificate-name preview), check inbox, guardian request and waiting pages, welcome,
  mentor batch list and detail, reset link, and the allauth and MFA screens.
- **Small JS modules** (no framework, CSP-safe, no inline scripts): the mobile menu, the stage strip, toasts, the confirm dialog and the language select.
- **Fixes the prototype review found:**
  - the assessment intro line "Answer **every** question" breaks into columns on phones because a bold word inside a flex row. Don't make flex rows out of running text.
  - the question-map legend uses the same colour for "answered" and "marked for review". Make them clearly different, with shape as well as colour.

**Done when**
- [ ] Every Stage 0–1 page uses the new shell. `/styleguide` shows every component, with the sample strings in all 4 languages.
- [ ] No sideways scroll at 360px and 1366px, and the axe check reports no serious or critical issues.
- [ ] No inline scripts or styles. The CSP that Caddy sets since Stage 0 is unchanged, and the pages work under it.
- [ ] The decisions are folded into architecture.md.
- [ ] Screenshots of `/styleguide`, `/register` and the mentor batch page at 390px and 1366px are attached to the PR for review.

**Prompt**
> Read docs/STATUS.md, CLAUDE.md, docs/decisions.md (all of it, especially D20–D30) and docs/build-stages.md Stage 1.5. Using design-reference/frontend-prototype/
> as the visual target, build the Django UI shell: design tokens, self-hosted fonts including Gujarati, base template, header and footer with
> both partner logos (ask me which CyberPeace logo file) and an emblem slot, the set_language wiring, component partials, a staff-only /styleguide, the
> screenshot and axe script, and restyle every Stage 0–1 page. Fold the decisions into architecture.md. No dark mode, no inline scripts, no framework.

---

## Stage 2: Questions and MCQ assessments

**Build** (§6 Questions/Assessments, §9, §13.2)
- `Question` and `QuestionVersion` (immutable versions), with a pydantic schema for `mcq`.
- XLSX import with django-import-export:
  - columns as in §13.2
  - dry run with row errors
  - hint required, exactly one correct option
- The legacy importer for the 405 MCQs (`docs/legacy-sources.md`).
- `AssessmentPart` (marks, counted, selection, draw_n, min_per_tag, pool), and `validate_part()`.
- `Attempt` and `AttemptItem`, with the unique and partial-unique constraints.
- `assessments/services.py`:
  - `start()`: lock the user, resume an existing attempt, draw with min-per-PC, shuffle, give one-off tokens
  - `save_answer()`
  - `submit()`: idempotent, scores with the frozen versions, all_answered, gate
- The attempt page (HTMX). Autosave with retry and a "Saved / Saving / Offline" pill. A count-up timer.
- The result page: score, ✓/✗, **hint**, **no correct option**.
- Auto-submit for attempts with no save for 7 days: a job in the `run_periodic` loop from Stage 1 (D27), daily, with tests.

**Done when**
- [ ] Journeys 5, 6 and 9 pass.
- [ ] A test proves the attempt page HTML/JSON contains no keys.
- [ ] Two parallel `start()` calls create one attempt.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §6, §9, §13.2. Implement Stage 2 from docs/build-stages.md: Question/QuestionVersion,
> MCQ schema, XLSX import, legacy MCQ importer, AssessmentPart with validate_part, and the full attempt lifecycle (start/answer/submit) with
> server-side scoring and a result page that shows hints but never correct options. Include concurrency and no-key-leak tests.

---

## Stage 3: Interactive engine (13 formats)

**Build** (§9.2, §9.6, `docs/legacy-sources.md`)
- A pydantic schema per format: mc, cards, spot, hotspot, sort, match, order, pick, build, settings, dial, chat, crossword (practice and Module 8 graded Part B, D26).
  The schema includes `hint`, `why` (the practice explanation) and gate flags with `gateReason`.
- `client_projection()` per format (§9.2 table). **A parameterised test over every legacy fixture** asserts that no key, marker, risky-segment flag, hotspot
  answer or canonical order is present.
- Scorers per format, ported from `engine.js`. Run the JS once in Node to freeze the expected scores as fixtures, then assert the Python matches.
- Importer for the legacy `questions.js` files.
- `engine/` in TypeScript: renderers for all formats (port the visuals from the old engine, minus the scoring). It posts answers to the server.
  Chat fetches the next step after each answer. Bundled with esbuild.
- Gate handling: a gated attempt is shown but not counted, with its message.
- **Option IDs (found in the prototype review):** the prototype strips the key fields, but every option, chip, item, reply and row keeps an ID
  that is its index in the source file (`o00`, `c03`, `i00`, `r00`, `row00`). The authors usually listed the right answers first, so the IDs give them away.
  For example:
  * in "Build the reply" the correct chip in each slot is the lowest ID (`c00`, `c03`, `c06`);
  * in the evidence bag the correct items are `i00`–`i04`;
  * in chat the best reply is usually `r00`.

  **In the real build, every ID the browser sees is a random token created for that attempt** and stored in `AttemptItem.option_map`
  (architecture §9.1). The projection test must also assert that sorting the IDs reveals nothing (tokens are random, not ordered).
- **Hotspot format:** the prototype inserts the hotspot SVG as raw markup (`${q.svg}` in `js/engine.js`). In the real build, a hotspot is an uploaded,
  sanitised image plus a list of region shapes, rendered by our template. Content is never raw SVG or HTML.
- **Visuals per format** follow the prototype's `js/engine.js` and `css/app.css`, with one change: **colour triage shows four big coloured buttons**
  (red, amber, yellow, green, each with its name and a non-colour cue). It is not a plain radio list. It is the course's signature interaction.
- Keep the prototype's attempt UX: question map, mark for review, a review screen before submitting, autosave pill, count-up timer.

**Done when**
- [ ] Every legacy challenge imports and renders.
- [ ] The projection and scorer tests pass for all fixtures, including "IDs are per-attempt random tokens" and "no raw SVG or HTML from content".
- [ ] Journeys 8 and 10 pass.

**Prompt**
> Read CLAUDE.md, docs/decisions.md, docs/architecture.md §9 and docs/legacy-sources.md. Implement Stage 3: pydantic schemas, client_projection
> and Python scorers for all 13 interactive formats (parity with the legacy engine.js via frozen fixtures), the legacy questions.js importer, and the
> TypeScript renderer bundle. Projection tests must prove no answer data reaches the browser.

---

## Stage 4: Learning content

**Build** (§6 Content, §8, §13.1)
- `Module` (counted flag), `Unit`, `UnitVersion` (blocks JSON with a pydantic schema; block types in §13.1), `MediaAsset`.
- Block rendering templates in the Stage 1.5 components, matching the prototype's `unit.html` course player (outline sidebar, previous/next, "Mark as complete").
- **Make the reading interactive (the HOD's main ask: learners do something to get the information).** In the prototype, topics are pages of
  text and the interactions only come at the end of the module. In the real build, each reading topic contains at least one inline interaction
  between its sections, using the existing block types:
  * a "predict, then reveal" question before an explanation,
  * flip cards for rules and helplines,
  * a myth-or-fact check,
  * a short practice `check` block.

  Start with the existing myth/fact and "ask yourself" material in each module's data. The content team adds more through the Content Studio.
- **Jumbled legacy tables** (m1.t0, m1.t4, m2.t3, m4.t0, m4.t3) render with cells in the wrong columns. Import them as they are, but mark them with a "table being fixed"
  notice until Teammate A's fixed versions are loaded.
- **Film units** use the poster and transcript until Teammate B provides the YouTube IDs. The posters are in the prototype's `assets/films/`.
- Importers: `booklet_text.json` + `modules.php`/`modules_ext.json` → reading units. Handout PDFs.
- The video unit:
  - YouTube ID → `youtube-nocookie.com` embed
  - the IFrame API marks the unit complete at 80%
  - `cc_lang_pref` for subtitles
  - MP4 fallback (≤150 MB) with HTML5 video
- DOCX upload → mammoth → nh3 → blocks (draft). Image upload (resize, strip EXIF). Upload limits and type sniffing.
- Draft → publish (admin, or a mentor with the "Content publisher" permission), and restore of earlier versions.
- `UnitProgress` completion rules (§8.3).
- `POST /learn/check`: practice-pool questions only, rate-limited, returns the full answer.
- The `TimeLog` heartbeat for adults only, with the caps (§8.3).
- The module page (§8.1).

**Done when**
- [ ] All 9 modules show their imported text, films (or placeholders), handouts and practice checks.
- [ ] A DOCX upload becomes a draft unit.
- [ ] A minor generates no TimeLog rows.
- [ ] `/learn/check` refuses quiz and final questions.

**Prompt**
> Read CLAUDE.md, docs/decisions.md, docs/architecture.md §6, §8, §13.1 and docs/legacy-sources.md. Implement Stage 4: modules, units with versioned
> blocks, legacy text import, YouTube/MP4 video units with completion, DOCX/image upload to draft, publish/restore, unit progress, the practice-only
> learn-check endpoint and the adult-only time-on-task heartbeat. Match design-reference/frontend-prototype/unit.html and make every
> reading topic contain at least one inline interaction.

---

## Stage 5: Results, final exam, pre-test, learner dashboard

**Build** (§10, §11, §15 learner column)
- `results/policy.py`: constants, `round1()`, `compute_results(user_ids)`, with tests for the §10.3 worked example and the boundary values.
- `ProgrammeAssessment` for the final and the pre-test: the blueprint, anchors, the cooldown setting (0).
- Final unlock rules (§10.2), the bands on the final result (§9.5), the knowledge-gain calculation (first final attempt vs pre-test, anchors only).
- The pre-test prompt after the first login (it can be postponed, but the final stays locked until it's done).
- A rule that a question can't move into the final pool once it has been shown in a non-final attempt.
- The learner "My progress" dashboard, laid out like the prototype's `dashboard.html`: the journey strip (pre-test, modules, mock, final, certificate) and the "What's left
  before your final" list. Put the items still to do first and the finished ones collapsed at the end. It contains:
  - the overall ring
  - module cards with parts
  - final state
  - blockers in plain words
  - weakest PCs
  - hours
  - a certificate card placeholder

**Done when**
- [ ] The worked example test passes exactly.
- [ ] Journeys 7 and 11 pass.
- [ ] The dashboard renders for a learner at each stage: new, mid-way, eligible.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §9.5, §10, §11, §15. Implement Stage 5: the results policy with Decimal rounding and the
> worked-example tests, the final exam and pre-test with blueprint, anchors and bands, unlock rules, knowledge gain, and the learner My progress dashboard.

---

## Stage 6: Staff tools

**Build** (§5, §10.4, §13, §15 mentor/admin columns). The mentor dashboard's layout follows the prototype's `mentor.html`.
- The mentor dashboard:
  - roster, heatmap, stuck learners
  - awaiting approval / issued this week
  - the auto-issue switch
  - CSV export (audited, with formula-injection-safe cells)
- Unfold admin actions: open/close registration, move a learner, approve, revoke.
- The final-pool permission (admins only).
- Interactive question editing with django-jsonform driven by the pydantic schemas, plus "preview as learner".
- The mark-split editor per module, with the **impact preview** using `compute_results`, a confirmation step and audit.
- The admin report page: totals per batch, knowledge gain vs 25%, item statistics (also per language), the email budget.
- `audit()` on every domain event, and simple-history on Batch, Enrolment, Question and AssessmentPart.

**Done when**
- [ ] Journeys 14 and 15 pass.
- [ ] A mentor can't open final-pool questions (403).
- [ ] The CSV opens safely in Excel.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §5, §10.4, §13, §15. Implement Stage 6: mentor dashboard, admin actions and report page,
> question editing with schema forms and preview, the mark-split editor with impact preview, audit logging and CSV export.

---

## Stage 7: Certificates

**Build** (§12). The certificate page and the public verify page follow the prototype's `certificate.html` and `verify.html`. The PDF uses the programme
name from settings and has a slot for the programme emblem (D23). Ask the lead for the final certificate wording and signatories before building the PDF template.
- `Certificate` with a DB sequence for `certificate_no`, a random `verify_code`, and a partial unique index (one issued certificate per user).
- `issue(user)`: lock, re-check, snapshot, a WeasyPrint PDF (English; **url_fetcher allowlist**), a segno QR, a sha256. Plus `revoke()`.
- Auto-issue on submit when the batch switch is on. Mentor "Approve all" for waiting learners. Switching the switch on does **not** bulk-issue.
- The learner certificate card and download (owner only).
- The public `/verify/<code>`: name, qualification, grade, date, status. Rate-limited. No lookup by number. Handles the erased-holder case.
- An `nsqf_approved` setting for the wording.
- Certificate design: match `design-reference/frontend-prototype/assets/certificate/cert-front.jpg`. Use the CCFR name and number prefix from settings (D23, D28).

**Done when**
- [ ] Journeys 12 and 13 pass.
- [ ] Names and certificate text cannot inject anything into the PDF (test).
- [ ] A revoked certificate shows "Revoked".

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §12. Implement Stage 7: certificate issue/revoke with sequence numbers and random verify
> codes, WeasyPrint PDF with a locked-down url_fetcher, QR, auto-issue and mentor approval, the learner download and the public verify page.

---

## Stage 8: Multilingual

**Build** (§14)
- gettext for all UI strings, with locale files for hi, mr and gu, and django-rosetta for staff.
- The `Translation` table and `t(key, lang)` with the key grammar, the source-hash staleness and the draft/reviewed rules (no drafts in assessments).
  Assessments **do** show translations once they are reviewed (D24).
- **Don't copy the prototype's translation method.** `js/phrases.js` matches text by its exact English sentence, which is the approach the architecture
  rejected because one English edit silently breaks the translation. Instead, **import its strings as `draft` translations**, along with the
  prototype's `data/i18n/*.js` (kept outside git in `content-data/prototype/`, see STATUS), and the team's reviewed translation sheets (from the private shared
  drive, copied into `content-data/translations/`, never into git). The legacy `booklet_i18n.json` drafts are already inside those pre-filled sheets, so
  don't import that file separately. Each one maps to the stable key it belongs to, and
  anything that can't be matched to a key goes in a report for the team.
- XLSX export/import per module, validating markers, placeholders, `<>` and blank-over-existing. A Reviewer permission per language (can't review own uploads).
- The language switch in the header, saved to the profile, with safe mid-attempt switching.
- Fonts were added in Stage 1.5. Here, check line heights and wrapping with long Hindi, Marathi and Gujarati strings on every page at 360px.
- Load the team's reviewed sheets.

**Done when**
- [ ] Journey 16 passes.
- [ ] Every page renders in all 4 languages with no English left except stale or missing strings.
- [ ] A changed English line shows as stale.

**Prompt**
> Read CLAUDE.md, docs/decisions.md and docs/architecture.md §14. Implement Stage 8: gettext + Rosetta for UI strings, the Translation table with
> source-hash staleness and reviewer workflow, XLSX round trip with validation, and the language switch (the fonts were added in 1.5). Import the draft translations listed above.

---

## Stage 9: Landing page and public pages

**Build**
- Port the **prototype's** landing page (`design-reference/frontend-prototype/index.html` + `css/landing.css`) to Django templates: the hero with the stage
  strip, the "Something just happened. What first?" check, modules, how certification works, languages, certificate, who runs it, FAQ, and the
  enrol call to action → `/register`. Use the programme name from settings: "Community Cyber First Responder (CCFR)". The prototype's "CSFR" becomes CCFR.
- The "Who runs it" photos and names are of real people: confirm with the lead that each person has agreed to appear before launch.
- A privacy notice page (the text comes from CyberPeace; use a placeholder until then), grievance contact, terms, and a help/FAQ page.
- A 404 and 500 page in the same style. Favicon and social preview image.

**Done when**
- [ ] The public pages are responsive, available in 4 languages, and Lighthouse accessibility is ≥ 90.

**Prompt**
> Read docs/STATUS.md, CLAUDE.md, docs/decisions.md and docs/legacy-sources.md. Implement Stage 9: port the prototype's landing page (design-reference/frontend-prototype/index.html) to Django templates, plus privacy, grievance,
> terms, FAQ and error pages, all translated and mobile-first.

---

## Stage 10: Launch hardening

**Build**
- A strict CSP (self plus the youtube-nocookie frame), HSTS, and a security headers check.
- Rate limits on login, register, reset, `/learn/check`, `/verify`, and answer/submit.
- A load test (locust or k6): 60 learners take the final at the same time on staging, with p95 under 1 s.
- A restore drill from a real backup, timed, with a note of how long it took.
- Sentry and an uptime pinger.
- All 17 journeys automated in Playwright.
- `docs/runbook.md`: deploy, roll back, restore, rotate secrets, incident (72 h DPDP notice), and adding an admin.
- Then (**person only**, not Claude): the lead's security audit, then fixes (Claude, in a PR), then a person deploys to prod and creates the real batches.

**Done when**
- [ ] Every Playwright journey passes on staging.
- [ ] The load test and the restore drill pass.
- [ ] The lead signs off.

**Prompt**
> Read CLAUDE.md and docs/architecture.md §16–§18. Implement Stage 10: CSP and security headers, rate limits, a 60-user load test, a timed restore drill,
> monitoring, Playwright tests for all journeys in §18, and docs/runbook.md.
