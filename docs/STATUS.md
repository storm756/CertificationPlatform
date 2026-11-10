# Project status: read this first

**Updated:** 12 Nov 2026. Every Claude session starts here, then reads `CLAUDE.md`, `docs/decisions.md` and the current stage in `docs/build-stages.md`.
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

### Stage 0–4 local course follow-up

The historical review notes dated 11 Nov describe the earlier draft state. The original 303-page booklet and the completed hint workbook are now available. The follow-up restores all 31 flagged blocks from 20 source tables. The nine learner handouts under `static/handouts/` contain only the booklet's lesson reading pages. All 509 approved hints are matched by stable ID. The six existing Module 8 crosswords now form its graded Part B (D26). The pre-test, final exam and capstone stay Coming soon. Staging deployment and verification follow the local review.

**Local verification.** The development course has 55 published readings with zero flagged blocks, 509 live questions with hints, and 18 published graded parts totaling 100 marks for each of Modules 1–9. Both real Module 8 parts passed a start, save and submit check with a temporary learner. All nine handout links, films and both caption tracks per film loaded in the browser. Playback was checked on Modules 2 and 8. Six pages passed the accessibility and overflow checks at the supported review sizes. Screenshots are in the local `screenshots/stage4-content/` directory.

**Final branch checks (12 Nov 2026, `stage-4-content-follow-up` on `origin/main` c55f95f).** Full PostgreSQL suite: 505 passed. `ruff check`, `ruff format --check`, `makemigrations --check` and `check --deploy` with production settings: clean. `publish_ccfr_course` preview (no `--apply`) on the local database: 20 corrected tables, 509 questions, 18 graded parts, nine practice checks, nine handouts and nine films verified without saving. axe: no serious or critical issues on the catalogue, Module 8 overview, film and handout, a corrected Module 4 table topic and the Module 10 capstone at 390px and 1366px (screenshots in `screenshots/stage4-content/`, not committed). Staging is not verified: merging does not copy the local database, MP4s or private inputs.

**Load the course.** On a fresh database, import the original lesson, MCQ and interactive banks first with the existing `import_legacy_lessons`, `import_legacy_mcq` and `import_legacy_interactive` commands. Provide the nine original module MP4 files and the prepared `approved-hints.json` and `question-edits.json` through private storage. The application image includes the learner handouts, corrected tables and English/Hindi caption tracks. Use `python manage.py publish_ccfr_course --hints <path-to-approved-hints.json> --films <film-directory>` for a rollback-only preview. Add `--apply` after verification. Mount or copy the private inputs into the application container through the team's deployment procedure.

**Translation review.** The legacy booklet has 635 draft entries each in Hindi, Marathi and Gujarati. They pass a structural check for nonblank wording, expected script and preserved placeholders. Only 55 of 324 distinct text values in the corrected tables have exact matches in those drafts. The nine module translation CSVs have blank language columns. Export the current wording with Stage 8 stable keys for further language review and approval. Assessment wording stays English until approved, and Marathi/Gujarati film captions remain pending.

| Stage | State | Notes |
| --- | --- | --- |
| 0. Foundation and server | ✅ **Done, merged (PR #1)** | Django 5.2 + Postgres 17 + Caddy on the VPS. `staging.cyberfirstresponse.io` serves HTTPS. Key-only SSH. Encrypted off-site backups. Staff 2FA. The CSP is set by Caddy. |
| 1. Accounts, batches, registration | ✅ **Merged into `main`** (6b95bdc) · 🟡 **staging check still open** | Finish items 1 and 2 are done and were checked before the merge (results below). On the last check `https://staging.cyberfirstresponse.io/register/` still returned **404**: a person must deploy `main` to staging and confirm `/register/` loads before Stage 1 counts as verified on staging. |
| 1.5. UI shell and components | ✅ **Merged into `main`** (040c25a) · 🟡 **staging check still open** | Design tokens, self-hosted fonts incl. Gujarati, shared base template and components, `/styleguide`, language wiring, `tools/screenshots.mjs`, every Stage 0–1 page restyled, and the prototype's sign-in and registration design (navy panel, numbered sections, certificate-name preview, password meter). Staging stays unverified until a person deploys `main` and confirms the pages there. |
| 2. Questions and MCQ assessments | ✅ **Merged into `main`** (8c37cd5, PR #5) · content follow-up local | **405 live MCQs with approved hints** in the development database. Nine graded Part A quizzes and a practice pool. |
| 3. Interactive engine (13 formats) | ✅ **Merged into `main`** (9d7f7f0, PR #6) · content follow-up local | **104 live challenges with approved hints** in the development database. Nine graded Part B assessments, including the six Module 8 crosswords. The standalone practice mock page is pending. |
| 4. Learning content | ✅ **Merged into `main`** (c55f95f, PR #7) · content follow-up local | On localhost, `/learn/` shows 55 real readings, nine films and handouts, and nine module practice checks. All flagged tables are corrected. Module 10 shows Coming soon. |
| 5. Results, final exam, pre-test, dashboard | 🟡 **In review** (`stage-5-review`, from `origin/main` + 3c81582, af74fd3, 7194479 and the exam-set work) | `compute_results` with Decimal rounding and the §10.3 worked example as a test, the pre-test (anchors, once, resumable) and the final (blueprint draw with anchors, unlock rules, cooldown setting), bands, knowledge gain, the pool rule, and the **My progress** dashboard. See "Stage 5: what to know". |
| 6. Staff tools | 🟡 **Saved on a local branch** (`stage-6`) | Its own follow-up PR after Stage 5. |
| 7–10 | ⬜ | In order. One stage = one branch = one PR. |

**Live addresses:**
* Staging: `https://staging.cyberfirstresponse.io`. On 11 Nov, `/register/` and `/learn/` returned 404. A person with server access needs to deploy and verify the merged build, then load the private lesson files for the staging course.
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
| Marathi and Gujarati film captions | Teammate B | The local course uses supplied MP4s with English and Hindi captions. |
| Separate final exam bank and shared pre-test questions | Teammate A | Both exams show Coming soon. The 509 existing questions and hints are published locally for module assessment and practice. |
| Module 10 capstone materials | Programme team | Module 10 shows Coming soon. |
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
| **Fixed in review:** a session that expires while the quiz is open. The answer endpoint is redirected to sign-in and the page used to treat the sign-in page (HTTP 200) as a saved answer and drop its form into the save indicator. "Saved" now needs the server's explicit confirmation (`X-Answer-Saved`); on a redirect to sign-in the quiz and indicator stay, the answer stays in memory, the pill says "Sign in again to save" with a notice and a Sign in link, and the answer is saved to its own question after the learner signs in again (the CSRF token is re-read from the cookie, since signing in changes it) | ✅ `tools/e2e_save_retry.mjs` scenario 7 at 390px and 1366px (fails on the old code), plus a test that only a real save carries the confirmation |


* **Local draft import (11 Nov 2026).** The original bank was copied to the ignored `content-data/legacy/bank_booklet.json` file. After validation, all 405 MCQs were loaded as drafts in the local Docker database. The source contains no hints. The draft assignment is 30 quiz and 15 practice per module. Apply approved hints and pool assignments with the XLSX question sheet matched by ID, then validate and publish.
* **Design calls made in Stage 2** (tell the lead if one is wrong):
  * `validate_part()` blocks a part whose counted marks would **exceed** 100. "The module totals exactly 100" can't be checked until the interactive part exists (Stage 3), so `module_marks_total()` reports it instead of blocking.
  * `AssessmentPart.is_published` (not in §6) is set only by `publish_part()`, which runs `validate_part()`. Learners can only start published parts.
  * `ProgrammeAssessment` exists as a table (so `Attempt` matches §6) but is unused until Stage 5.
  * `Module` is a minimal table seeded with modules 1–9 (counted) and 10 (capstone, not counted, D26). Stage 4 adds units and titles.
  * XLSX import errors say "row N" where N counts data rows, not the header. A real import is all-or-nothing.
  * Option ids inside a question body (`o1`…) are internal only; the browser gets random per-attempt tokens. Scores are stored with `round1()` (one decimal).
  * The auto-submit job treats an auto-submitted attempt like a submitted one (`counted` unless gated); `all_answered` still says whether it was complete.
* **htmx** is vendored at `static/js/htmx.min.js` (v2.0.4, BSD-0 licence beside it) and configured without eval or inline styles, so Caddy's CSP is unchanged.

## Stage 3: what to know (read before Stage 5)

**Stage 3 review results (11 Nov 2026, `stage-3-review` = `origin/main` + the nine Stage 3 commits, `f375771` and earlier; `stage-3` kept as a backup).** Run in a fresh dev stack with invented questions only. The overlaps with the merged Stage 2 work were resolved in favour of main's behaviour: the Excel-import fix, the `X-Answer-Saved` confirmation, expired-session recovery and the no-option result page all still work, now with interactive questions too.

| Check | Result |
| --- | --- |
| Full test suite (PostgreSQL) | ✅ 456 passed |
| `ruff check`, `ruff format --check`, `makemigrations --check`, `check --deploy` (prod settings) | ✅ clean |
| TypeScript engine (`tools/build_engine.mjs`: type-check + esbuild) | ✅ builds; the committed bundle is identical to the build |
| Journey 8 (gate choice scored, not counted, hint shown) and journey 10 (no keys or markers in any attempt page or JSON) | ✅ tests |
| Scorer parity with the legacy `engine.js` | ✅ 128 frozen invented cases; 624 of 624 on the private bank (counts only) |
| Answer data stays on the server (allow-list projections, random per-attempt tokens, private hotspot images) | ✅ projection and flow tests |
| Browser autosave checks for multiple-choice **and** interactive questions (`tools/e2e_save_retry.mjs`, production CSP, 390px and 1366px): failed save then Next, refused save, quick Next, Review while refused, tab close, chat, and the expired session (Not saved, kept in memory, saved to the right question after signing in again) | ✅ 85 checks |
| axe on the interactive quiz questions (mc, colour triage, tick list, chat) and the review page at 390px and 1366px | ✅ no serious or critical issues; screenshots in `screenshots/stage3-review/` (not committed) |
| Private content at Stage 3 review | The dry run validated 104 legacy challenges (80 quiz, 24 practice). See the local draft import update below. |


* **Local draft import (11 Nov 2026).** All 104 legacy interactive challenges were loaded as drafts in the local Docker database. The importer prepared the 18 IDs for the mixed practice mock. The Python scorers agreed with the real legacy engine on 624 of 624 private cases. All 104 still need approved hints.
* **Local learner preview.** The two demo assessment parts were unpublished and their nine demo questions retired. Existing demo records and attempts were kept. The learner catalogue now shows the real readings and myth-or-fact checks while the question drafts await approval.
* **Content calls made by the importer** (tell the lead if one is wrong):
  * Legacy markup is flattened to plain text (content is never HTML). Sort-bin descriptions (`d`) are dropped.
  * Hotspot art is rasterised from the legacy SVG (rect, text, group only) to a PNG by the importer. Learners get the picture plus numeric regions.
  * The legacy mixed set (m11) has 18 questions, not 20. It goes to `practice`, and also becomes a `ProgrammeAssessment(kind="mock")`. Mixed questions that name no module go to Module 10.
  * Module 8 crosswords are practice only.
  * Interactive questions need no PC tag to be published (only MCQs do).
* **Rules of the engine:** a blank answer never triggers a safety gate; a gate needs something the learner actually did (and "I'm finished" for spot). Formats with nothing to leave blank use an explicit `done` flag. The format scorers keep the legacy engine's credit for leaving things alone (untouched pick-free 0.5, untouched settings 1/3) so parity holds, but at submission, manual or automatic, an item the learner never touched (or only flagged) scores 0 and cannot gate. A finished-with-nothing-picked answer is an answer and keeps its credit. The result page shows right / partly right / not quite and the hint, and never repeats an option's text, not even the learner's own right pick.
* **Verified:** the full test suite, a real-browser end-to-end of all formats at 390px and 1366px under the production CSP (no violations), axe clean on every attempt, review and result page. Screenshots are in `screenshots/stage3/` (not committed).

## Stage 4: what to know (read before Stage 5)

**Stage 4 review results (11 Nov 2026, `stage-4-review` = `origin/main` (Stage 3 merged, PR #6) + cf79bb7 + 24b566d; `stage-4` kept as a backup).** Run in a fresh dev stack with the private lesson files imported locally (not in Git) and invented learners.

| Check | Result |
| --- | --- |
| Full test suite (PostgreSQL) | ✅ 504 passed |
| `ruff check`, `ruff format --check`, `makemigrations --check`, `check --deploy` (prod settings) | ✅ clean |
| Import: 9 modules, **55 reading topics** (6, 7, 6, 6, 6, 6, 6, 6, 6), 9 film pages, 9 handout pages, 9 myth-or-fact checks | ✅ all 9 module pages and all 55 topic pages return 200 |
| Every reading topic has an inline interaction (predict-then-reveal, flip cards or "ask yourself") | ✅ 55 of 55, in the data and in the rendered HTML |
| DOCX upload becomes a **draft** unit; invalid, oversized or entity-laden files are refused; publishing supersedes the old version, restore re-publishes, only an admin or a "Content publisher" can publish | ✅ tests |
| Progress rules per unit type; **minors generate no `TimeLog` rows**; adults are capped | ✅ tests |
| `/learn/check` accepts only live **practice**-pool questions used by a published unit; quiz and final questions are refused; a signed-out visitor gets feedback without a record | ✅ tests |
| Unpublished lessons cannot record completion or time | ✅ tests |
| Browser (production CSP, 390px and 1366px): reveal answer comes from the server, flip cards, myth-or-fact verdict, completion at the end and after reload, handout opens as complete, film page | ✅ `tools/e2e_learn.mjs`, no CSP violations |
| axe: catalogue, a module, a lesson and the practice check at 390px and 1366px | ✅ no serious or critical issues; screenshots in `screenshots/stage4-review/` (not committed) |
| Fixed in review: the module page's hero was pale (the per-module colour variable was not set outside the prototype); module and lesson pages now carry `data-mod` | ✅ |
| Lesson player vs the approved `unit.html` | ✅ same structure and shared classes (outline sidebar, breadcrumbs, unit head, complete bar, previous/next). **Not compared pixel for pixel**: the prototype's lesson data is not in Git (D22), so its `unit.html` cannot render here |

**Still missing from the content team (recorded, not built):** all 9 handout **PDFs** (the handout pages show the web text); the 9 **YouTube video IDs** (film pages show the poster, an English/Hindi transcript and a "being uploaded" notice); **Module 10** (capstone) pages and handout; **corrected tables** (31 tables carry a "table being fixed" notice: the five named ones m1.t0, m1.t4, m2.t3, m4.t0, m4.t3 plus 26 detected); reviewed Hindi, Marathi and Gujarati lesson text (Stage 8). No practice question is live yet, so no `check` block uses a real practice question (the legacy bank has no approved hints).


* **Where to look:** `/learn/` (all modules), `/learn/m<N>/` (module page), `/learn/m<N>/t1/` … `t7/` (reading topics), `/learn/m<N>/film/`, `/learn/m<N>/handout/`, `/learn/m<N>/check/`. Load the content with `python manage.py import_legacy_lessons --source content-data/legacy/lessons` (create-only; `--dry-run` prints counts). The 55 topics: M1 6, M2 7, M3 6, M4 6, M5 6, M6 6, M7 6, M8 6, M9 6.
* **Missing from the content team:** (1) the 9 handout **PDFs** (`m1–m9.pdf`; the handout page shows the web text, and the PDF attaches automatically when `handouts/m<N>.pdf` is present at import or the file is uploaded in the editor); (2) the 9 **YouTube video IDs** (films show the poster and transcript with a "being uploaded" notice until an ID is set); (3) Module 10 (capstone) content and handout; (4) fixed versions of the jumbled tables (31 tables are flagged "table being fixed": the five named ones m1.t0, m1.t4, m2.t3, m4.t0, m4.t3 plus 26 more the importer detected); (5) reviewed Hindi, Marathi and Gujarati text (Stage 8; lessons are English only today, film transcripts carry the Hindi line).
* **Design calls made in Stage 4** (tell the lead if one is wrong):
  * Lessons are readable without signing in (awareness content); progress and time are recorded for signed-in learners only.
  * The inline interactions are built from the module's own material: the situation cards become "predict, then reveal", the protection pairs become flip cards, the "ask yourself" questions a reflection list; each goes to the topic it shares most words with, and every topic gets at least one. The three myths per module are the module's practice check.
  * Reveal and myth-or-fact answers stay on the server until the learner asks. `/learn/check` accepts only live `practice`-pool MCQs that a published unit uses; no practice question is live yet (the legacy bank has no hints), so no `check` block is placed by the importer.
  * The Caddy CSP now allows `script-src https://www.youtube.com` (needed by the YouTube IFrame API that reports the 80% mark). A person must deploy that Caddyfile change.
  * Some legacy text was extracted from PDFs and contains fragments (for example a "Key term / Figure 1.3" paragraph in M1 topic 1). It is imported as written; the content team should review the topics in the editor.
  * Nothing creates a "Content publisher" permission holder yet: grant `content.publish_unit` to a mentor in the admin.

## Stage 5: what to know (read before Stage 6)

* **Nothing can run the real exams yet.** The pre-test and the final draw from the `final` pool, which the content team writes fresh (D19). Until anchors exist, the pre-test shows "not available yet" and the final stays locked with that reason. Tests and screenshots use invented questions only.
* **Content decisions needed:** which questions are anchors (mark `is_anchor`; the blueprint may also list ids), and the blueprint counts (today 6/6/5/6/6/6/5/5/5 = 50 in `programme.DEFAULT_PER_MODULE`, editable on the `ProgrammeAssessment` row until Stage 6 adds an editor).
* **Design calls made in Stage 5** (tell the lead if one is wrong):
  * A counted module with no published counted assessment, or an unpublished counted assessment, keeps the final locked and shows "Course setup is incomplete" (a content-team problem, not the learner's). Combined results use the unrounded question-level marks, not the stored one-decimal scores.
  * Attempt scores are stored to one decimal, so the mean uses those stored values; the worked example is tested both with full-precision parts and through real attempts.
  * The pre-test prompt is shown once, right after the first sign-in (`Profile.pretest_prompted_at`); "Later" goes to the dashboard, which keeps a pre-test card. A learner with no pre-test available is not prompted.
  * The final result shows the overall % and per-module bands only; the pre-test result shows the score only. Neither shows questions, hints or right/wrong marks.
  * A question that has been shown in any non-final attempt cannot be moved into the final pool (`Question.save` raises `PoolLocked`). Anchors are written directly in the final pool, so showing them in the pre-test is allowed.
  * The practice mock has no page yet (a placeholder step on the journey strip).
  * `eligible` does not yet check for an issued certificate (Stage 7 sets `already_issued`).
