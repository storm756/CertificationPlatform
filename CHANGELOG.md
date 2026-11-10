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
- Stage 2 review fix: the result page no longer prints the learner's chosen option (for a right answer that was the correct option's text). It shows the score, right/wrong and the hint only. Why: D13.
- Stage 2 review fix: the Django-admin Excel import no longer returns HTTP 500 after saving. Each imported row now carries its saved question, so the confirmation shows and the admin log names the questions; a failure at confirm rolls the whole import back. Why: §13.2.
- Stage 2 review fix: quiz autosave keeps each answer in a per-question outbox (`attempt.js`) and retries it for its own question, so a failed save on Question 1 can no longer be replaced by Question 2's. "Saved" means the server accepted every pending answer; a refused answer shows "Not saved"; Review stays put while an answer is refused. Browser test: `tools/e2e_save_retry.mjs` (with `tools/seed_e2e.py`). Why: no lost or misattributed answers.
- Stage 2 review fix: an expired session during the quiz is no longer treated as a saved answer. "Saved" requires the server's `X-Answer-Saved` confirmation; after a redirect to sign-in the pending answer stays in memory, the pill reads "Sign in again to save", a notice offers a Sign in link, and the answer is sent to its own question once the learner signs in again. Why: no silently lost answers.

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

