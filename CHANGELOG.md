# Changelog

## 2026-11-08: Stage 0, foundation and server
- Django 5.2 project skeleton, settings split (dev/staging/prod) read from env vars. Why: architecture §4, §17.
- Custom email `User` (with `email_normalized`, role, status) in the first migration. Why: can't be swapped later.
- allauth + `allauth.mfa`; staff must set up TOTP before reaching anything but the auth pages (middleware); admin login goes through allauth; staff sessions 12 h. django-unfold admin.
- Postgres roles `csfr_owner` (migrations) / `csfr_app` (runtime) created by `deploy/db/init-roles.sh`.
- Docker: `compose.dev.yml`; `compose.yml` (web, db, cron, staging-only mailpit) per environment; **`compose.edge.yml` (shared Caddy)**, because staging and prod are separate stacks on one host and only one process can own ports 80/443.
- `deploy/deploy.sh`, `deploy/server/bootstrap.sh` (hardening), encrypted hourly `pg_dump` + nightly media to B2 (write-only key), `deploy/restore.sh`.
- GitHub Actions CI: ruff, pytest on Postgres, `check --deploy`, shellcheck, compose/Caddy validation, image builds.

## 2026-11-08: Stage 1, accounts, batches, registration
- `Profile`, `ConsentRecord` (append-only), `GuardianConsent`, `Batch`, `BatchMentor`, `Enrolment`, `AuditEvent`, `EmailLog`, `MentorResetLink`. Why: architecture §6.
- `/register`: closed page when nothing is open, locked-transaction re-check of `is_accepting`, age gate (under 16 refused, 16-17 wait for guardian email consent), certificate-name preview, no account fishing, per-batch rate limit. Public allauth sign-up closed. Why: D4, D9, D16, D17, §7.2.
- Email normalisation setting (`EMAIL_NORMALISE_ALIASES`: on in prod, off on staging) and daily email budgets with an admin-dashboard "sent today" counter. Why: §7.2.
- Mentor pages under `/mentor/`: my batches, create batch, open/close + window + seats, roster with new sign-ups, move learner, one-time reset link, change certificate name; all audited and scoped through `batches_for()`. Why: §5, §7.4.
- 2FA is now required for mentors and admins by role, not only `is_staff`. Why: mentors use the mentor pages, not Django admin.
- Tests for journeys 1-4, scoping, reset links, budgets and the mentor 2FA redirect.

## 2026-11-10: Stage 1 finish items
- Added the `tasks` service (web image, non-root, `csfr_app` role) to `compose.yml` and `compose.dev.yml`, running `manage.py run_periodic`: wakes every 10 minutes, runs due jobs at 03:00 Asia/Kolkata, stores the last success in `core.PeriodicRun` so a restart catches up once, and logs a failing job without stopping the loop. `deploy.sh` restarts `tasks` with `web`. Why: D27, data minimisation.
- `purge_unverified` now also deletes learners still waiting for guardian consent 7 days after their link expired, sends no email, and writes one count-only `system.purge_unverified` audit event (replaces the per-account event). Why: DPDP data minimisation, STATUS item 1.
- Dev database now creates the real `csfr_app` role (`deploy/db/dev-grants.sh`) so `tasks` connects as it in development too. Existing dev databases need `docker compose -f deploy/compose.dev.yml down -v` once.
- Mentor "Move learner": no batch chosen returns 400 with "Pick a batch."; an unknown or not-yours batch returns 403 and an `access.denied` audit event, identical in both cases. Why: STATUS item 2.

## 2026-11-10: Stage 1.5, UI shell and components
- Ported the approved prototype's look to Django: `static/css/{tokens,fonts,base,app,stage}.css`, a shared `templates/base.html` (cream header with the SAKEC and square CyberPeace logos, a programme-emblem slot showing "CCFR", nav, language select, footer, toasts, confirm dialog), reusable partials in `templates/components/`, an SVG icon sprite and `static/js/ccfr-shell.js`. One light theme, no night mode. Why: D20, D21, Stage 1.5.
- Self-hosted fonts: Baloo 2 and Hind (Latin, Devanagari) plus Baloo Bhai 2 and Hind Vadodara (Gujarati), with the OFL licences. The unused Epilogue font was left out. Why: Stage 1.5, architecture §14.
- The programme name is now Community Cyber First Responder (CCFR), read from `settings.PROGRAMME_NAME` / `PROGRAMME_SHORT` in pages, the guardian email subject, the admin title, the authenticator issuer and the From name. Internal names (`csfr_*` DB roles, containers) are unchanged. Why: D23, D30.
- Language select wired to `POST /i18n/setlang/` (cookie for guests, `Profile.preferred_language` for signed-in users), plus `ProfileLanguageMiddleware` for new devices. Added `locale/gu` and `LOCALE_PATHS`, because Django ships no Gujarati catalogue and ignores `gu` without one. Why: Stage 1.5, D7.
- Restyled every Stage 0–1 page, including the real sign-in page and the allauth and two-factor screens (via element template overrides). Sign in keeps allauth's login, validation, CSRF and redirects; the prototype's demo box is gone and "Remember me" is not pre-ticked. Why: D20, security.
- Staff-only `/styleguide` showing every component in every state, with hard-coded Hindi, Marathi and Gujarati samples. Added `tools/screenshots.mjs` (390px and 1366px screenshots, sideways-scroll check, axe). Why: Stage 1.5 done-when.
- Review fixes: the question map tells "answered" and "marked for review" apart by shape as well as colour; "Answer every question" is running text, not a flex row. Small contrast fixes found by axe. Why: Stage 1.5 review items.
- Folded decisions D20–D30 into `docs/architecture.md` and added §22. Why: Stage 1.5.

## 2026-11-10: Stage 2, questions and MCQ assessments
- Added `Question` and immutable `QuestionVersion` (model guard plus a database trigger), the MCQ pydantic schema (exactly one correct option, hint required to go live, safety-gate options with reasons) and `client_projection()`. Why: D11, D13, D25, §6, §9.2.
- XLSX import of MCQs in the admin with a dry run and row errors; the real import is all-or-nothing. Added `import_legacy_mcq`, a create-only importer for the private legacy bank that prints counts only. The 405 legacy questions load as drafts because the bank has no hints. Why: §13.2, `docs/legacy-sources.md`.
- Added `AssessmentPart` with `validate_part()` and `publish_part()`, and `Attempt` / `AttemptItem` with the unique and partial-unique constraints. Added a minimal seeded `Module` table (1–10) and `apps/results/policy.py` (`round1`, `percent`, `PASS_MARK`). Why: §6, D26.
- Attempt lifecycle in `assessments/services.py`: `start()` (user row lock, resume, draw with min-per-tag, shuffle, random per-attempt option tokens, frozen versions), `save_answer()`, idempotent `submit()` scored on the server. Why: §9.
- Attempt, review and result pages (htmx, vendored and CSP-safe): autosave, retry when offline, Saved / Saving / Offline pill, count-up timer, question map, mark for review. The result shows score, ✓/✗ and hints, never the correct option. Why: D13, §9.5.
- Daily `auto_submit_stale_attempts` job in `run_periodic`. Why: §9.3, D27.
- New dependencies: `django-import-export[xlsx]` and `pydantic`. Why: architecture §3.

## 2026-11-10: Stage 3, interactive engine (13 formats)
- Added pydantic bodies, allow-list projections, per-attempt random token maps, `clean_response` validation and Decimal scorers for mc, cards, spot, hotspot, sort, match, order, pick, build, settings, dial, chat and crossword; MCQ moved into the same format registry unchanged. Gates fire only on something the learner did. Why: §9.2, §9.6, D13.
- Scorer parity with the legacy `engine.js`: 128 frozen cases from invented questions (including gates), plus `check_legacy_parity` for the private bank (counts only). Why: Stage 3 done-when.
- `AttemptItem.format` and a wider numeric score column; `ProgrammeAssessmentKind.MOCK`; "Partly right" on the result page. Why: partial credit.
- Hotspots: uploaded raster images (Pillow re-encode, metadata stripped, SVG rejected) served only to the attempt's owner, plus numeric regions drawn by the engine. Why: no raw SVG or HTML from content.
- `import_legacy_interactive` (create-only, drafts, counts only). The 104 legacy challenges validate but are **not loaded**: they have no hints. The 405 Stage 2 MCQs were also only dry-run checked and stay in the source file. Why: §13.2.
- TypeScript renderer (`engine/`, esbuild bundle `static/js/engine.js`, `static/css/engine.css`) with colour triage as four labelled buttons; saves through the Stage 2 htmx form; chat fetches its next step after the save. Checked in a real browser at 390px and 1366px under the production CSP, axe clean. Why: D20, Stage 3.
- New dependency: Pillow. Dev dependencies in `tools/`: esbuild, typescript, jsdom.

## 2026-11-10: Stage 3 review fixes
- Untouched questions now earn zero in manual and automatic submissions. Before, a blank free "tick the right ones" question earned 1/2 and a blank settings question 1/3 (the legacy engine's credit for leaving things alone), which inflated blank and auto-submitted attempts. Real answers, including a deliberate "finished, nothing picked", keep their partial credit. Why: scoring must follow what the learner did.
- The result page no longer prints "Your answer: ..." (for a right answer that was the correct option's text). It shows right / partly right / not quite and the hint. Why: D13, never repeat the correct option.
- Regression tests for both.


## 2026-11-10: Review fixes (accounts, language, auto-submit)
- The purge job now locks the email-verification and guardian-consent rows of its candidates and asks the rule again before deleting, so a learner who verifies (or whose guardian confirms) while it runs is kept. Why: DPDP minimisation must not delete someone who just finished signing up.
- A guardian resend keeps the old link working until the new email has really gone out. A full budget or a mail failure used to replace the link without sending it. Failures are logged and the waiting page says the email could not be sent. Why: D16.
- A signed-in learner's saved language now wins over a stale language cookie, and choosing a language no longer has its cookie reset to the old saved one on a new device. Why: D7.
- `submit()` takes `stale_before`: the auto-submit job rechecks the last save under the attempt lock, so a quiz saved after the job looked is left open. Why: §9.3.
- A regression test for each (`tests/test_review_fixes.py`).

## 2026-11-10: Guardian send result and auto-submit count
- `guardian.send_request()` treats `send_mail()` returning 0 as a failed send: the old link keeps working (and keeps its original expiry), nothing is recorded against the email budget. Why: D16.
- `submit()` marks the attempt it returns with `just_closed`, decided under the attempt lock. `auto_submit_stale()` counts and audits only the attempts this call really closed, so a manual submit that won the race, or another worker's auto-submit, is not counted. Why: §9.3, audit accuracy.

## 2026-11-10: Guardian confirmation and resend overlap
- `guardian.confirm()` locks the consent row and rechecks it, so two overlapping confirmations (or a double tap) record and audit once; the first name stands. Why: audit accuracy, D16.
- `guardian.resend()` holds the consent row from the email to the save, so overlapping resends can no longer leave the newest email with a dead link. Why: D16.

## 2026-11-10: Answer saves are kept per question and retried
- `static/js/attempt.js` now keeps every answer in an outbox tagged with its own question number. It is sent after a short pause, or at once when the learner clicks Next, Previous, the question map or Review and submit. A failed save (network, timeout, server error) stays in the outbox and is retried for the original question with a growing delay, even after the learner has moved on. Before, the retry re-sent whichever question was on screen, so question 1's answer was lost. Why: no lost answers.
- The pill says "Saved" only when the server has accepted every answer. A refused answer (400, 403) shows a new "Not saved" state. Before, any 4xx showed "Saved".
- The engine hands each change over at once instead of waiting 120 ms, so a quick Next can no longer drop an interactive answer. The question forms no longer use `hx-post`; without JavaScript they post as before.
- `tools/e2e_save_retry.mjs` (with `tools/seed_e2e.py`, invented data) is the browser test: it fails question 1's save, moves to question 2, restores the connection and checks the server holds question 1's answer, for multiple choice and interactive questions, at 390px and 1366px, under the production CSP. It also covers a quick Next, a refused answer, Review and submit, and a chat reply.

## 2026-11-10: Guardian confirmation rechecks the link under the lock
- `guardian.confirm()` locks the consent row and checks that the link the page was opened with is still the stored one and still live. A link replaced by a resend (or expired, or already used) can no longer approve consent; the consent page then shows the invalid-link page. Why: D16.

## 2026-11-10: Stay on the quiz when an answer was refused; guardian record removed mid-confirm
- Review and submit (or any plain link on the attempt page) no longer leaves the quiz when an answer was refused, whether the learner clicks after the "Not saved" message or while that save is still in progress. Focus moves to the pill and, if the refused answer belongs to another question, that question is shown. Why: the learner would otherwise submit without knowing an answer was not saved.
- Closing or reloading the tab while an answer is still waiting to be saved now makes the browser ask first (the outbox lives in the page). Why: no silent loss of answers.
- `guardian.confirm()` returns False when the consent record was removed between the link lookup and the confirmation (account cleanup), so the consent page shows the existing invalid-link page instead of a server error. It now locks only the consent row. Why: D16, robustness.
- Tests: browser scenarios in `tools/e2e_save_retry.mjs`; Python regression tests in `tests/test_review_fixes.py`.

## 2026-11-10: Stage 4, learning content
- Added `Unit`, `UnitVersion` (immutable text, one published version), `MediaAsset`, `UnitProgress`, `TimeLog` and `LearnCheck`, and the block schema. Why: §6, §13.1.
- `/learn/` pages: catalogue, module page and unit pages (reading, film, handout, myth-or-fact check) in the approved design, with outline, previous/next and completion rules. Why: §8, D20.
- `import_legacy_lessons`: 9 modules, 55 reading topics (each with at least one inline interaction), 9 film pages (poster and English/Hindi transcript), 9 handout pages and 9 myth-or-fact checks, as published versions. 31 jumbled tables carry a "table being fixed" notice. Why: Stage 4 done-when.
- Predict-then-reveal, flip cards and myth-or-fact keep their answers on the server until the learner acts; `POST /learn/check` accepts practice-pool questions only. Why: CLAUDE.md answer-key rule, §8.4.
- Adult-only time heartbeat with caps; under-18s write no `TimeLog` rows. Why: D16.
- DOCX upload (mammoth, nh3) and image/PDF/MP4 upload with sniffing; publish/restore with a "Content publisher" permission. Why: §13.1.
- Caddy CSP allows `script-src https://www.youtube.com` for the YouTube IFrame API. A person deploys it. Why: D18.
- New dependencies: `mammoth`, `nh3`.

## 2026-11-10: Stage 4 review fixes
- Completion and time-tracking requests for an unpublished (draft or retired) lesson are refused (404; the heartbeat counts nothing). A malformed module number in a posted check or heartbeat is a 404, not a server error. Why: no progress against lessons learners cannot see.
- A signed-out visitor can answer a published practice check and gets the score and full answer; no `LearnCheck` or progress row is written for them (it used to fail). Quiz and final questions are still refused. Why: §8.4, awareness content is public.

## 2026-11-10: Stage 5, results, final exam, pre-test and dashboard
- `compute_results` (Decimal, `round1` only) with the §10.3 worked example and the boundary values as tests; grades and bands. Why: §10, D1, D2.
- Pre-test (anchors only, once, resumable) and final exam (blueprint draw with anchors, cooldown setting, unlock rules, locked reasons). Final shows overall % and bands; the pre-test shows the score only. Why: §11, D14.
- Knowledge gain (first final's anchor score minus the pre-test's), weakest PCs, hours. Why: §11, §15.
- A question shown in a non-final attempt cannot move into the final pool. Why: §11.
- The learner "My progress" dashboard replaces the placeholder welcome page; the pre-test is offered once after the first sign-in (`Profile.pretest_prompted_at`). Why: §15, Stage 5.

## 2026-11-10: Stage 5 review fixes
- Combined results use unrounded marks: `compute_results` recomputes each attempt's percentage from its saved question-level marks (`Attempt.score` is only a rounded display value). 13/15 and 5/38 in equal-weight parts now give 49.9% (fail), not 50.0. Why: §10.1, D2.
- The final stays locked, and eligibility is withheld, when a counted module has no published counted assessment or a counted assessment is unpublished; the learner sees "Course setup is incomplete" (on the dashboard, the final's page and in the blockers). Why: §10.2. This replaces the Stage 5 call that treated such modules as not counted.
- The pre-test result and attempts list show the overall score only, even when a safety gate was triggered (no gate message, no "doesn't count"). Why: §11.

## 2026-11-10: Stage 5, exactly 100 marks per counted module
- The course-setup check now also requires the published counted marks of every counted module to total exactly 100 (D11). A module with only a 50-mark part keeps the final locked and the learner ineligible, and the message names the module and the configured marks ("Module 1 has 50 published marks configured; it needs exactly 100."). The unpublished-part check is unchanged. Why: §10.1 assumes 100.

## 2026-11-10: Stage 6, staff tools
- Mentor batch dashboard: roster with module %, final and overall, a module heatmap (red below 50), stuck learners, eligible-awaiting-approval, and the auto-issue switch (audited). Why: §15.
- CSV export of a batch: scoped, POST-only, audited (counts only), spreadsheet-safe cells, UTF-8 with BOM, no-store. Why: §15, Stage 6 done-when.
- Question editing with schema checking and "preview as learner" for mentors and admins; edits become new versions and go back to draft; only admins publish. **Final-pool questions are admin-only** (pages, list, Django admin, and the pool field). Why: §5, D19.
- Mark-split editor (admin) with an impact preview computed by the same `compute_results`, a confirmation step and an audit event. Why: §10.4.
- Admin report page (per-batch totals, knowledge gain vs 25, item statistics per language, email budget) and Django-admin actions to open/close registration. Why: §15.
- simple-history on `Batch`, `Enrolment`, `Question` and `AssessmentPart`. Why: §6.
- Not built (needs Stage 7's certificate table): approve, issue and revoke actions.
