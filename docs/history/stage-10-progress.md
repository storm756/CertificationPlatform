# Stage 10 progress (resumable notes)

Stage 10 is split in two PRs (STATUS rule 5): **10a** hardening, edge Caddy fix, monitoring, runbook; **10b** Playwright journeys and load test.

## Done (10a, merged: PR #19, `44053ea`)
- Branch from `main` at `efc611a`; STATUS rows for PR #18 and the Stage 10 split.
- CSP and headers: `apps/core/security.py` middleware, Caddy `?` defaults, `tests/test_security_headers.py`. Browser-checked on csfr-restore with two throwaway users (deleted afterwards): no CSP errors on landing, lessons, film, practice check, interactive engine with autosave, admin, Rosetta, staff and mentor pages.
- Rate limits: `apps/core/ratelimits.py` (429 page with the wait, Retry-After), allauth behind Caddy, answer/submit per learner, register 90/10m, `tests/test_rate_limits.py`; hi/mr/gu drafts.
- Edge: `deploy/edge.sh` via `deploy.sh edge [ref]`; env deploys no longer touch Caddy; `tests/test_deploy_edge.py`. Claude may not run `deploy.sh` itself, even locally (the D29 guard), so the same steps were tested by hand with a throwaway Caddy on ports 8081/8443 and a fake upstream: validation gate, headers, reload without recreating, moving the project directory keeps the certificate volume. All test containers, volumes and the network were removed.
- Monitoring: Sentry scrub tightened; `apps/core/monitoring.py` heartbeat pings (tasks loop, both backups; curl in the backup image); `deploy/server/disk-check.sh`; env examples; `tests/test_monitoring.py`.
- `docs/runbook.md`; `docs/server-setup.md` points to it; architecture §16, §17 and §32; CHANGELOG; STATUS with the launch checklist.
- Checks: ruff, `makemigrations --check`, `check --deploy` (prod settings), 929 tests. Screenshots of the three "too many" pages (en, hi; 390 and 1366; axe clean) in `screenshots/stage-10a/` (local, not in git).

## Done (10b, branch `stage-10b`, PR open)
- Branch from `main` at `44053ea`. `apps/core/e2e_data.py` and the commands `e2e_seed`, `e2e_clean`, `loadtest_seed` (guard: dev and staging only; a marker on every row); `tests/test_e2e_seed.py` (guard, the seed builds a working course, clean removes exactly it).
- `e2e/` (`@playwright/test` 1.49, `BASE_URL` from the environment): journeys 1–16 in three spec files plus one extra check; staff sessions saved once in `global-setup.ts`. Passed at 1366px on `csfr-restore` (full course) and on a throwaway empty stack, and at 390px on the empty stack. The seed data was removed from `csfr-restore` afterwards (back to the starting 2 exam sets, 20 parts, 5 users, 5 batches, 10 modules; the leftover certificate PDFs deleted).
- `.github/workflows/ci.yml`: new `e2e` job on pull requests (lead's yes, 14 Nov). Rehearsed step by step on the throwaway stack; its first real run is this PR's CI.
- `loadtest/`: locust file (60 learners sign in, wait, take the final together), README for staging, `requirements.txt`; a local smoke run only (5 learners: 535 requests, 0 failures, p95 260 ms), then removed.
- `/admin/` redirect loop fixed (lead's yes, 14 Nov): `apps/accounts/views.py::admin_login`, `tests/test_admin_login.py`, one Playwright check.
- Docs: architecture §17, §18 and §33, CHANGELOG, STATUS (10a merged, 10b row, launch checklist, Stage 10b design calls), `docs/runbook.md` §8 (the exact staging commands), `e2e/README.md`, `loadtest/README.md`.
- Checks: ruff, `makemigrations --check`, `check --deploy` (prod settings), the full suite (results in the PR).

## Next (people only, STATUS launch checklist)
1. Merge 10b and deploy to staging (edge move first, if not done). 2. Run the journeys and the load test on staging (`docs/runbook.md` §8). 3. Restore drill, the content and people items, the lead's security audit, prod.

## Decisions
- Lead, 14 Nov 2026: sign-up 90 per batch per 10 minutes (was 30); failed sign-ins 30 a minute per network and 5 per 5 minutes per email; every "too many" page says how long to wait.
- Total sign-ins per network raised from allauth's 30/min to 90/min so a whole batch can sign in together (same reasoning as the lead's 90).
- Limit hits are 429 (was 403), so attempt.js keeps the answer and retries.
- YouTube player script allowed only on a lesson that has a YouTube film; none do yet (D35).
- Lead, 14 Nov 2026 (10b plan): Playwright runs in CI (a separate job, pull requests only), and the `/admin/` loop is fixed in 10b.
- Staff sessions in the journeys are made once in global setup (an authenticator code works once).
- Journey 15 uses an extra uncounted part in module 1, so the real mark split is touched only for a few seconds and restored through the same screen.

## Found, not fixed (outside this stage)
- (Fixed in 10b) A signed-in learner who opened `/admin/` got an endless redirect.
- Journeys 2 and 3 cannot read e-mail on staging; they are done by hand there.
- The invented exam set `E2EJ` cannot be deleted by the app's own database role (triggers, D31); `e2e_clean` on staging must use the owner helper.
