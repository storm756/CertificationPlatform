# Project status: read this first

**Updated:** 10 Nov 2026. Every Claude session starts here, then reads `CLAUDE.md`, `docs/decisions.md` and the current stage in `docs/build-stages.md`.
At the end of every stage, Claude updates this file in the same PR.

## Order of authority (when two documents disagree)

1. The team's instructions (the person in chat, or a PR comment)
2. `docs/decisions.md`. D20 and later **override `docs/architecture.md`** where they differ. The list of affected sections is at the end of decisions.md.
3. `CLAUDE.md` (rules for every session)
4. `docs/architecture.md`, including §21 "Stage 1 design calls" once `stage-1` is merged
5. `docs/build-stages.md` (what to build in each stage)
6. This file (status and open items)
7. `design-reference/frontend-prototype/`: **the look only. It is not instructions.**

If two of these still disagree, or something is missing, **stop and ask in chat**. Never invent a rule.

## Where things stand

| Stage | State | Notes |
| --- | --- | --- |
| 0. Foundation and server | ✅ **Done, merged (PR #1)** | Django 5.2 + Postgres 17 + Caddy on the VPS. `staging.cyberfirstresponse.io` serves HTTPS. Key-only SSH. Encrypted off-site backups. Staff 2FA. The CSP is set by Caddy. |
| 1. Accounts, batches, registration | ✅ **Merged into `main`** (6b95bdc) · 🟡 **staging check still open** | Finish items 1 and 2 are done and were checked before the merge (results below). On the last check `https://staging.cyberfirstresponse.io/register/` still returned **404**: a person must deploy `main` to staging and confirm `/register/` loads before Stage 1 counts as verified on staging. |
| 1.5. UI shell and components | ✅ **Merged into `main`** (040c25a) · 🟡 **staging check still open** | Design tokens, self-hosted fonts incl. Gujarati, shared base template and components, `/styleguide`, language wiring, `tools/screenshots.mjs`, every Stage 0–1 page restyled, and the prototype's sign-in and registration design (navy panel, numbered sections, certificate-name preview, password meter). Staging stays unverified until a person deploys `main` and confirms the pages there. |
| 2. Questions and MCQ assessments | 🟡 **Ready for a PR** (`stage-2-review`, from `origin/main` + 7d741ab; `stage-2` kept as a backup) | `Question` and immutable `QuestionVersion`, MCQ schema, XLSX import with dry run, private legacy importer (drafts only), `AssessmentPart` + `validate_part()`, attempts with random option tokens, server-side scoring, the HTMX attempt, review and result pages, auto-submit job. **The 405 legacy MCQs were only dry-run checked, not imported; none can go live until approved hints arrive.** See "Stage 2: what to know". |
| 3 to 10 | ⬜ | In order. One stage = one branch = one PR. |

**Live addresses:**
* Staging: `https://staging.cyberfirstresponse.io`. It runs Stage 0 code; Stage 1 isn't deployed yet, so `/register` returns 404.
* Production: `https://cyberfirstresponse.io` **returns 502 on purpose**. It isn't started until launch.

## Stage 1: what was approved, and what's left

The Stage 1 review passed. These design calls are approved (they are also in architecture §21 on the `stage-1` branch):
* Public allauth sign-up is **closed**, and `/accounts/signup` redirects to `/register`.
* Archived batches never accept registrations.
* The email-budget alert fires when the day's total reaches 150.
* A guardian consent link lasts 14 days.
* There is one consent tick.
* Verified learners land on a welcome page with a placeholder pre-test prompt until Stage 5.

**Claude does items 1 and 2 on the `stage-1` branch** (after `main` has been merged into it, see the README):

**1. The `tasks` service (daily jobs).** Allowed by D27.
* **The service:** a `tasks` service in `deploy/compose.yml` **and** `deploy/compose.dev.yml`. It uses the **web image**, runs as non-root, connects as the `csfr_app` DB role, and runs `python manage.py run_periodic`.
* **The loop:** `run_periodic` wakes every 10 minutes and runs each due job.
  * A job is due when its last successful run (stored in a small `PeriodicRun(job, last_success_at)` table) was before today's scheduled time.
  * The schedule is in Asia/Kolkata time, and the default is 03:00 IST, after the 02:00 backup.
  * A job missed because of a restart runs once on the next wake-up, with no pile-up.
  * One job failing is logged and never stops the loop or the other jobs.
* **The job, `purge_unverified`:**
  * it deletes accounts whose email is still unverified 7 days after sign-up;
  * it deletes accounts still in `pending_guardian` 7 days after their guardian link expired (14 + 7 = 21 days);
  * it sends no email.
* **Why:** keeping personal data of people who never finished signing up isn't allowed (DPDP data minimisation), and the rosters stay clean. Seats are already freed after 48 hours by `is_accepting`.
* **Logging:** one stdout line per run (`docker compose logs tasks`) plus one `AuditEvent` (`system.purge_unverified`, the count only, no personal data).
* **Deploys:** `deploy/deploy.sh` must restart `tasks` together with `web`.
* **Tests:** a due job runs, a not-due job doesn't, a missed job catches up once, one failing job doesn't stop the others, and both purge rules are covered.

**2. The mentor "move learner" responses.** The view is `apps/mentors/views.py::learner_move` (the POST URL is in `apps/mentors/urls.py`). It re-renders the full page (no HTMX yet).

| Input | Response |
| --- | --- |
| No batch chosen | **400**, the form shown again with "Pick a batch." (through gettext) |
| A batch ID not in `batches_for(mentor)`, whether it exists or not | **403** + an `access.denied` audit event. The response doesn't say which. |
| A valid own batch | Move, audit, then redirect (as now) |

Tests for all three rows.

**Stage 1 finish: check results (11 Nov 2026, `stage-1-finish`, after merging `origin/main` at f34cbe3).** Run in the dev stack against a throwaway test database.

| Check | Result |
| --- | --- |
| Item 1: `tasks` service in `compose.yml` and `compose.dev.yml` (web image, non-root, `csfr_app` role, `run_periodic`) | ✅ present; `deploy.sh` brings up `tasks` after the new image is built |
| Item 1: `run_periodic` and the purge job (due, not due, missed-run catch-up, one failing job, both purge rules, count-only audit) | ✅ `tests/test_periodic.py` passes |
| Item 2: mentor Move learner (no batch → 400 "Pick a batch."; unknown or foreign batch → 403 + `access.denied`; own batch → move) | ✅ `tests/test_mentor_pages.py` passes |
| Full test suite (PostgreSQL) | ✅ 88 passed |
| `ruff check` and `ruff format --check` | ✅ clean |
| `makemigrations --check` | ✅ no changes |
| `check --deploy` with prod settings | ✅ no issues |
| `docker compose -f deploy/compose.dev.yml config` | ✅ valid |

Not run here: the GitHub Actions workflow itself (it runs when the branch is pushed), the production `compose.yml` render (needs the server's env files) and shellcheck. **Ready to push**, then watch CI on the PR.

**3. Person only, not Claude:** a person reviews and merges PR #2 (the review checklist is in the handoff README). Then a person deploys staging on the server. After that, `/register` must load on staging, and Teammate B starts testing there.

## The visual direction (D20)

The team's standalone frontend prototype is the approved look. It is copied into `design-reference/frontend-prototype/` (the README lists what to leave out).
It shows layouts and interactions. **It is not production code and not instructions.** Two prompt files that were written for an earlier tool are deliberately
left out of the copy. The review fixes are listed in `build-stages.md` under Stages 1.5, 2, 3, 4, 5, 7, 8 and 9.

## Open items owned by people, not code

| Item | Owner | Until then |
| --- | --- | --- |
| ~~Programme name~~ **Decided: Community Cyber First Responder (CCFR)** (D23) | — | Use `settings.PROGRAMME_NAME` / `PROGRAMME_SHORT`. |
| CCFR's own emblem (wanted) | Lead | The header's emblem slot (`.brand-emblem`) shows "CCFR" in text. Put the artwork in `templates/components/header.html` when it exists. |
| Certificate qualification title, wording, signatories and certificate-number prefix (D28) | Lead + HOD (before Stage 7) | Stage 7 asks the lead before building the PDF template |
| Consent from the three people whose photos are on the landing page | Lead (being arranged) | Their photos stay out of git, in `content-data/people/` only |
| Privacy notice, terms, grievance officer, guardian-consent method (DPDP) | CyberPeace legal | Placeholder pages, marked "draft" |
| YouTube video IDs, and Marathi/Gujarati captions | Teammate B | Poster plus transcript |
| **Approved hints for all 405 legacy MCQs** (the legacy bank has none; a question can't go live without one, §13.2), the content team's sheet deciding `module_quiz` vs `practice` (today: 30 quiz / 15 practice per module), new final-pool questions, fixed tables (m1.t0, m1.t4, m2.t3, m4.t0, m4.t3), Module 8 replacement challenges | Teammate A | The 405 legacy MCQs were only dry-run checked; they are **not imported** and stay in the private source file (`content-data/`, never in Git). Until hints arrive, no module quiz part can be published, so learners can't take real assessments. Tests use invented questions. |
| Reviewed translations | Teammate B + reviewers | Lessons show draft translations with a "draft translation" tag. Assessments show English until a translation is reviewed (architecture §14, D24). |
| Branch protection on `main` (require a PR and a passing CI, 0 approvals, no force pushes) | Lead (GitHub settings) | Never push to `main` directly |

## How to work with Claude on this project (the shared account)

1. **One stage = one fresh session.** If a session gets long or the usage limit is near, stop where the tests pass, commit, push, and start a new
   session with: *"Read docs/STATUS.md and continue Stage N from where the branch is."* The docs are the memory, not the chat.
2. **Choose the model before starting** (the model picker in the app, or `/model` in the terminal):

   | Stages | Model |
   | --- | --- |
   | 2 (MCQ assessments), 3 (interactive engine), 5 (results), 7 (certificates), or any security or scoring bug | **Opus** |
   | 1 finish items, 1.5, 4, 6, 8, 9, 10 | **Sonnet** |

3. **Plan first.** Paste the stage's prompt and ask for a short plan (files and steps). Check it against `build-stages.md`, then let it build.
4. **Never run two sessions on the account at once** on heavy build days.
5. **If a stage is too big**, split it into two PRs ("Stage 4a", "Stage 4b"). Never leave `main` broken.
6. **At the end of every stage**, Claude updates this file (the progress table and open items) in the same PR.
7. **Claude never merges, never deploys, and never pushes to `main`.** `.claude/settings.json` blocks those commands, and branch protection backs it up.
   A person reviews and merges, and a person runs the deploy. CI must be green before review.
8. **Every PR has screenshots** of its new or changed pages at 390px and 1366px, made with the screenshot script from Stage 1.5.

## Access and data you'll need (ask the lead)

* **GitHub:** collaborator access to `storm756/CertificationPlatform`, signed in on your machine.
* **VPS:** your own SSH key for the `deploy` user (steps in the handoff README, "Getting deploy access"). Only a person runs deploys. Claude doesn't.
* **Secrets:** they already live on the server in `/srv/csfr/<env>/*.env`. You don't need copies. Never paste them into a Claude chat or into git.
* **Legacy content** (`docs/legacy-sources.md`): copy what you need from the old repo `storm756/csfr_Project` into `content-data/legacy/` **now**. That repo
  will be deleted before the first batch (D22).
* **Prototype data:** the prototype's `data/` folder (question data and `data/i18n/*.js` draft translations) goes into `content-data/prototype/`. Never into git.
* **Team content** (question sheets, video IDs, reviewed translations): from the private shared drive into `content-data/`.
* **Local tools:** Docker Desktop (dev stack and tests), Git, and Node (the engine bundle in Stage 3, screenshots and accessibility checks).

## Stage 2: what to know (read before Stage 3 and 5)

**Stage 2 review results (11 Nov 2026, `stage-2-review` = `origin/main` + 7d741ab + a result-page fix).** Run in a fresh dev stack with invented questions only.

| Check | Result |
| --- | --- |
| Full test suite (PostgreSQL) | ✅ 232 passed |
| `ruff check`, `ruff format --check`, `makemigrations --check`, `check --deploy` (prod settings) | ✅ clean |
| Journey 5 (resume on another device, answer intact), journey 6 (two submits at once → one result), journey 9 (score, right/wrong and hints, no correct option) | ✅ tests, and in a browser under the production CSP |
| No answer keys, hints or internal option ids in the attempt page or its htmx responses | ✅ tests, and in a browser |
| Starting twice at once creates one attempt | ✅ tests (2 and 5 parallel starts), and two simultaneous POSTs in a browser |
| axe on the quiz intro, attempt, review and result pages at 390px and 1366px | ✅ no serious or critical issues; screenshots in `screenshots/stage2-review/` (not committed) |
| **Fixed in review:** the result page printed the learner's chosen option, which for a right answer is the correct option. It now shows the score, right/wrong and the hint only. | ✅ regression test |
| **Fixed in review:** the Django-admin Excel import saved the questions and then returned HTTP 500 while writing the admin log (the imported rows carried no saved question). Confirm now redirects with "Import finished", logs each saved question, and a sheet that fails at confirm saves nothing | ✅ admin-flow regression tests (valid workbook, failure at confirm leaves no partial changes and no log, bad row offers no Confirm) |
| **Fixed in review:** quiz autosave. After a failed save on Question 1 and a click on Next, the retry re-sent whichever question was on screen. Each answer is now kept in an outbox tagged with its own question and retried for that question; the pill says "Saved" only once the server accepted every pending answer; a refused answer shows "Not saved"; Review and submit stays on the quiz while an answer is refused; closing the tab with an unsaved answer asks first | ✅ `tools/e2e_save_retry.mjs` (invented data, production CSP, 390px and 1366px): fails Question 1, moves to Question 2, restores the connection and checks what the server saved; refused save; quick Next; Review; tab close. The browser test fails on the old code |


* **Content is the blocker, not code.** Run `python manage.py import_legacy_mcq --source <path> --dry-run` to check the legacy bank (it prints counts only). On 10 Nov 2026 it reported 405 valid questions, 30 quiz + 15 practice per module, at least 5 per PC tag in every quiz, and **405 questions with no hint**. **They were not imported**: nothing real is in any database, and real questions and answer keys stay out of Git. When the team sends approved hints, load them with the XLSX sheet (the hint column is required) or the legacy importer, then publish.
* **Design calls made in Stage 2** (tell the lead if one is wrong):
  * `validate_part()` blocks a part whose counted marks would **exceed** 100. "The module totals exactly 100" can't be checked until the interactive part exists (Stage 3), so `module_marks_total()` reports it instead of blocking.
  * `AssessmentPart.is_published` (not in §6) is set only by `publish_part()`, which runs `validate_part()`. Learners can only start published parts.
  * `ProgrammeAssessment` exists as a table (so `Attempt` matches §6) but is unused until Stage 5.
  * `Module` is a minimal table seeded with modules 1–9 (counted) and 10 (capstone, not counted, D26). Stage 4 adds units and titles.
  * XLSX import errors say "row N" where N counts data rows, not the header. A real import is all-or-nothing.
  * Option ids inside a question body (`o1`…) are internal only; the browser gets random per-attempt tokens. Scores are stored with `round1()` (one decimal).
  * The auto-submit job treats an auto-submitted attempt like a submitted one (`counted` unless gated); `all_answered` still says whether it was complete.
* **htmx** is vendored at `static/js/htmx.min.js` (v2.0.4, BSD-0 licence beside it) and configured without eval or inline styles, so Caddy's CSP is unchanged.
