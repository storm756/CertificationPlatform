# Stage 10 progress (resumable notes)

Stage 10 is split in two PRs (STATUS rule 5): **10a** hardening, edge Caddy fix, monitoring, runbook; **10b** Playwright journeys and load test.

## Done (10a, branch `stage-10a`, PR open)
- Branch from `main` at `efc611a`; STATUS rows for PR #18 and the Stage 10 split.
- CSP and headers: `apps/core/security.py` middleware, Caddy `?` defaults, `tests/test_security_headers.py`. Browser-checked on csfr-restore with two throwaway users (deleted afterwards): no CSP errors on landing, lessons, film, practice check, interactive engine with autosave, admin, Rosetta, staff and mentor pages.
- Rate limits: `apps/core/ratelimits.py` (429 page with the wait, Retry-After), allauth behind Caddy, answer/submit per learner, register 90/10m, `tests/test_rate_limits.py`; hi/mr/gu drafts.
- Edge: `deploy/edge.sh` via `deploy.sh edge [ref]`; env deploys no longer touch Caddy; `tests/test_deploy_edge.py`. Claude may not run `deploy.sh` itself, even locally (the D29 guard), so the same steps were tested by hand with a throwaway Caddy on ports 8081/8443 and a fake upstream: validation gate, headers, reload without recreating, moving the project directory keeps the certificate volume. All test containers, volumes and the network were removed.
- Monitoring: Sentry scrub tightened; `apps/core/monitoring.py` heartbeat pings (tasks loop, both backups; curl in the backup image); `deploy/server/disk-check.sh`; env examples; `tests/test_monitoring.py`.
- `docs/runbook.md`; `docs/server-setup.md` points to it; architecture §16, §17 and §32; CHANGELOG; STATUS with the launch checklist.
- Checks: ruff, `makemigrations --check`, `check --deploy` (prod settings), 929 tests. Screenshots of the three "too many" pages (en, hi; 390 and 1366; axe clean) in `screenshots/stage-10a/` (local, not in git).

## Next (10b, a new branch from `main` after 10a is merged)
1. `e2e/` with `@playwright/test`, `BASE_URL` from the environment; guarded `manage.py e2e_seed` / `e2e_clean` (invented batches B01–B03, learners, a mentor; refuses prod).
2. Journeys 1–16 of architecture §18 (17 is the restore drill, runbook §3.1); pass locally against `csfr-restore`, then remove the seed data.
3. `loadtest/` (locust): 60 learners take the final together; `manage.py loadtest_seed`; README for a person to run it on staging; a small local smoke run only.
4. CI: decide with the lead whether Playwright runs in CI (architecture §17 says yes).

## Decisions
- Lead, 14 Nov 2026: sign-up 90 per batch per 10 minutes (was 30); failed sign-ins 30 a minute per network and 5 per 5 minutes per email; every "too many" page says how long to wait.
- Total sign-ins per network raised from allauth's 30/min to 90/min so a whole batch can sign in together (same reasoning as the lead's 90).
- Limit hits are 429 (was 403), so attempt.js keeps the answer and retries.
- YouTube player script allowed only on a lesson that has a YouTube film; none do yet (D35).

## Found, not fixed (outside this stage)
- A signed-in learner who opens `/admin/` gets an endless redirect (admin login → allauth login → `/admin/`), so the browser shows "too many redirects". Pre-existing; not a security problem.
