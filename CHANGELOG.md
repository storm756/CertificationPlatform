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
