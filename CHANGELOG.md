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
