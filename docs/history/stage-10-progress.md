# Stage 10 progress (resumable notes)

Stage 10 is split in two PRs (STATUS rule 5): **10a** hardening, edge Caddy fix, monitoring, runbook; **10b** Playwright journeys and load test.

## Done
- 10a: branch `stage-10a` from `main` at `efc611a`; STATUS rows for PR #18 and Stage 10 updated.
- CSP and headers: `apps/core/security.py` middleware, Caddy `?` defaults, `tests/test_security_headers.py`. Browser-checked on csfr-restore (no CSP errors).
- Rate limits: `apps/core/ratelimits.py` (429 page with the wait, Retry-After), allauth behind Caddy, answer/submit per learner, register 90/10m, `tests/test_rate_limits.py`. 916 tests pass.

## Next (10a)
1. `deploy/deploy.sh edge`, env deploys stop touching Caddy; tested with a throwaway Caddy.
2. Monitoring: Sentry scrub tests, health pings, disk check.
3. `docs/runbook.md`.
4. Docs, checks, PR.

## Decisions
- Lead, 14 Nov 2026: sign-up 90 per batch per 10 minutes (was 30); failed sign-ins 30 a minute per network and 5 per 5 minutes per email; every "too many" page says how long to wait.
- Total sign-ins per network raised from allauth's 30/min to 90/min so a whole batch can sign in together (same reasoning as the lead's 90).
- Limit hits are 429 (was 403), so attempt.js keeps the answer and retries.
- YouTube player script allowed only on a lesson that has a YouTube film; none do yet (D35).
