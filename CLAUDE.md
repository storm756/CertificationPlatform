# CLAUDE.md: Cyber First Response certification platform

A certification platform for the Community Cyber First Responder programme (CyberPeace Foundation × SAKEC).
Django 5.2 + PostgreSQL 17 + HTMX, deployed with Docker Compose and Caddy on one Ubuntu 24.04 VPS.

## Always
- **Read `docs/architecture.md` before writing code.** Build what it says. Section numbers (§) in tasks refer to it.
- `docs/decisions.md` lists settled product decisions. **Do not change behaviour that contradicts them.** If something in the design looks
  wrong or is missing, stop and write the question in the PR description (or ask in chat). Don't silently invent a rule.
- Work only on the current stage from `docs/build-stages.md`. One stage = one branch = one PR.
- Every stage ends with its "Done when" checks passing, including tests. Add or update tests with every feature.
- If behaviour changes, update `docs/architecture.md` in the same PR, and add a line to `CHANGELOG.md` (date, what, why).

## Never
- **Never send answer keys, correct options, scoring rules, `[[!markers]]` or hotspot answers to the browser.** All scoring is server-side.
  Every format has a `client_projection()` with a test that proves this.
- **Never commit** `.env` files, secrets, database dumps or question data (`content-data/` is gitignored). The repo is public for now.
- Never use `|safe` on user or content text. Never store raw HTML from uploads. Sanitise with nh3.
- Never use floats for scores: `Decimal`, rounded only by `results.policy.round1()`.
- Never edit a `QuestionVersion` or a published `UnitVersion` in place. Create a new version.
- Never add Redis, Celery, a React SPA or JWT. They were considered and rejected.

## Commands (set up in stage 0)
- Dev: `docker compose -f deploy/compose.dev.yml up`
- Tests: `docker compose -f deploy/compose.dev.yml run --rm web pytest`
- Lint: `ruff check . && ruff format --check .`
- Deploy: `deploy/deploy.sh staging` then `deploy/deploy.sh prod`

## Style
- Small, readable functions. Business rules live in plain functions (`results/policy.py`, `batches/rules.py`, `assessments/services.py`),
  not in views or templates.
- Mentor-facing queries always go through `batches.scoping.batches_for(user)`, and there is a test that mentors can't see other batches.
- UI: mobile-first, colourful, in the handbook style: cream background, navy text, teal / mustard / terracotta accents, Baloo 2 headings and Hind body text
  (Devanagari and Gujarati versions included). Large tap targets. It must work on a cheap Android phone on 4G.
