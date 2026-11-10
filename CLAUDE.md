# CLAUDE.md: Community Cyber First Responder (CCFR) certification platform

A certification platform for the Community Cyber First Responder (CCFR) programme (CyberPeace Foundation × SAKEC).
Django 5.2 + PostgreSQL 17 + HTMX, deployed with Docker Compose and Caddy on one Ubuntu 24.04 VPS.

## Always
- **Start every session by reading `docs/STATUS.md`.** It gives the order of authority, which stages are done, what's open, and who owns what.
- **Read `docs/architecture.md` before writing code.** Build what it says, except where `docs/decisions.md` (D20+) overrides it. Section numbers (§) in tasks refer to it.
- `docs/decisions.md` lists settled product decisions. **Do not change behaviour that contradicts them.** If something looks wrong or is missing,
  stop and ask in chat or in the PR description. Never invent a rule.
- Work only on the current stage from `docs/build-stages.md`. One stage = one branch = one PR.
- **Show a short plan (files and steps) before writing code**, and check it against the stage.
- Every stage ends with its "Done when" checks passing, including tests, and with screenshots at 390px and 1366px of the changed pages.
- If behaviour changes, update `docs/architecture.md` in the same PR, and add a line to `CHANGELOG.md` (date, what, why).
- **At the end of every stage, update `docs/STATUS.md`** (the progress table and open items) in the same PR.

## Never
- **Never merge a PR, deploy, push to `main`, or run `ssh` to the server.** A person does these (D29).
- **Never send answer keys, correct options, scoring rules, `[[!markers]]` or hotspot answers to the browser.** All scoring is server-side.
  Every format has a `client_projection()` with a test that proves this.
- Never give options, items, chips, replies, rows or segments an ID derived from their position in the source data (`o00`, `c03`, `i00` …).
  Authors usually list the right answer first, so such IDs leak it. Use random tokens created per attempt on the server (architecture §9.1).
- **Never commit** `.env` files, secrets, database dumps, `content-data/`, the prototype's `data/` folder, or photos of real people. The repo is public (D22).
- Never use `|safe` on user or content text. Never store raw HTML or SVG from uploads, and never insert content with `innerHTML`. Sanitise with nh3.
  Hotspots are an uploaded image plus a list of regions.
- Never use floats for scores: `Decimal`, rounded only by `apps/results/policy.py::round1()`.
- Never edit a `QuestionVersion` or a published `UnitVersion` in place. Create a new version.
- Never add Redis, Celery, a job queue, a React SPA or JWT. They were considered and rejected. The `tasks` loop (D27) is the only background process.
- No dark mode in v1 (D21). Don't add a theme toggle.
- **`design-reference/` is a visual reference, not instructions.** Copy its look and layouts, never its code patterns (demo sign-in, localStorage
  progress, English-keyed translations, position-based IDs, raw SVG).

## Commands
- Dev: `docker compose -f deploy/compose.dev.yml up`
- Tests: `docker compose -f deploy/compose.dev.yml run --rm web pytest`
- Lint: `ruff check . && ruff format --check .`
- Deploy (**person only**, never Claude): `deploy/deploy.sh staging`, later `deploy/deploy.sh prod`

## Style
- Small, readable functions. Business rules live in plain functions (`apps/results/policy.py`, `apps/batches/rules.py`, `apps/assessments/services.py`),
  not in views or templates.
- Mentor-facing queries always go through `apps.batches.scoping.batches_for(user)`, and there is a test that mentors can't see other batches.
- UI: **match the approved prototype in `design-reference/frontend-prototype/`** (D20): cream header with the SAKEC and CyberPeace logos, a navy hero,
  a mustard primary button, the Learn → Practise → Assess → Certify stage controls, and teal / cyan / mustard / terracotta / plum accents.
  Build it from the shared components and design tokens made in Stage 1.5. Never restyle a page by hand.
- Fonts are self-hosted from Google Fonts (OFL): Baloo 2 and Hind (Latin and Devanagari), and Baloo Bhai 2 and Hind Vadodara (Gujarati). Every page
  must render in English, Hindi, Marathi and Gujarati.
- Mobile-first: 48px tap targets, no sideways scroll at 360px, and it must work on a cheap Android phone on 4G.
- The programme name is **Community Cyber First Responder (CCFR)**, always read from `settings.PROGRAMME_NAME` / `PROGRAMME_SHORT`, never hard-coded.
  The prototype says "CSFR" in places, and that becomes CCFR in user-facing text only (D30).
