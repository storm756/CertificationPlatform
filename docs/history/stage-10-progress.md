# Stage 10 progress (resumable notes)

Stage 10 is split in two PRs (STATUS rule 5): **10a** hardening, edge Caddy fix, monitoring, runbook; **10b** Playwright journeys and load test.

## Done
- 10a: branch `stage-10a` from `main` at `efc611a`; STATUS rows for PR #18 and Stage 10 updated.
- CSP and headers: `apps/core/security.py` middleware, Caddy `?` defaults, `tests/test_security_headers.py`. Browser-checked on csfr-restore (no CSP errors).
- Rate limits: `apps/core/ratelimits.py` (429 page with the wait, Retry-After), allauth behind Caddy, answer/submit per learner, register 90/10m, `tests/test_rate_limits.py`. 916 tests pass.
- Edge: `deploy/edge.sh` via `deploy.sh edge [ref]`; env deploys no longer touch Caddy; `tests/test_deploy_edge.py`. Tested by hand with a throwaway Caddy on ports 8081/8443 (validate gate, headers, reload without recreate, move to a new directory keeps the cert volume); Claude may not run deploy.sh itself, even locally (D29 guard), so a person should run `deploy.sh edge` once against a scratch CSFR_ROOT. All test containers, volumes and the network removed.
- Monitoring: Sentry scrub tightened (no frame variables, emails masked in messages/exceptions/breadcrumbs); `apps/core/monitoring.py` heartbeat pings (TASKS_PING_URL after each `tasks` wake-up; BACKUP_DB_PING_URL / BACKUP_MEDIA_PING_URL from the backup scheduler, `/fail` on failure; curl added to the backup image); `deploy/server/disk-check.sh` (80%, host cron); env examples. `tests/test_monitoring.py`. 929 tests pass.

## Next (10a)
1. `docs/runbook.md`.
2. Docs (architecture §16–§17 + implementation notes, CHANGELOG, STATUS with the person-only launch checklist), checks, PR.

## Decisions
- Lead, 14 Nov 2026: sign-up 90 per batch per 10 minutes (was 30); failed sign-ins 30 a minute per network and 5 per 5 minutes per email; every "too many" page says how long to wait.
- Total sign-ins per network raised from allauth's 30/min to 90/min so a whole batch can sign in together (same reasoning as the lead's 90).
- Limit hits are 429 (was 403), so attempt.js keeps the answer and retries.
- YouTube player script allowed only on a lesson that has a YouTube film; none do yet (D35).
