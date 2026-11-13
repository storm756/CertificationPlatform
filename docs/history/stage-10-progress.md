# Stage 10 progress (resumable notes)

Stage 10 is split in two PRs (STATUS rule 5): **10a** hardening, edge Caddy fix, monitoring, runbook; **10b** Playwright journeys and load test.

## Done
- 10a: branch `stage-10a` from `main` at `efc611a`; STATUS rows for PR #18 and Stage 10 updated.

## Next (10a)
1. CSP and security headers (Django middleware, Caddy defaults for static/media), tests.
2. Rate limits: allauth behind Caddy (`ALLAUTH_TRUSTED_PROXY_COUNT`), answer/submit per user, tests.
3. `deploy/deploy.sh edge`, env deploys stop touching Caddy; tested with a throwaway Caddy.
4. Monitoring: Sentry scrub tests, health pings, disk check.
5. `docs/runbook.md`.
6. Docs, checks, PR.

## Decisions
- Waiting for the lead on the register limit (per batch only, or plus a per-network cap) and the per-network failed-login limit.
