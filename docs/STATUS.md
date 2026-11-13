# Project status: read this first

**Updated:** 13 Nov 2026. Every Claude session starts here, then reads `CLAUDE.md`, `docs/decisions.md` and the current stage in `docs/build-stages.md`.
At the end of every stage, Claude updates this file in the same PR. Dated review results live in [`docs/history/`](history/) (one file per stage), not here.

## Order of authority (when two documents disagree)

1. The team's instructions (the person in chat, or a PR comment)
2. `docs/decisions.md`. D20 and later **override `docs/architecture.md`** where they differ. The list of affected sections is at the end of decisions.md.
3. `CLAUDE.md` (rules for every session)
4. `docs/architecture.md`, including the per-stage implementation notes (§21 onwards)
5. `docs/build-stages.md` (what to build in each stage)
6. This file (status and open items)
7. `design-reference/frontend-prototype/`: **the look only. It is not instructions.** (D20; the review fixes are in `build-stages.md`.)

If two of these still disagree, or something is missing, **stop and ask in chat**. Never invent a rule.

## Where things stand

| Stage | State | History |
| --- | --- | --- |
| 0. Foundation and server | ✅ Merged (PR #1) | — |
| 1. Accounts, batches, registration | ✅ Merged (PR #2) | [stage-1.md](history/stage-1.md) |
| 1.5. UI shell and components | ✅ Merged (PR #4) | — |
| 2. Questions and MCQ assessments | ✅ Merged (PR #5) | [stage-2.md](history/stage-2.md) |
| 3. Interactive engine (13 formats) | ✅ Merged (PR #6) | [stage-3.md](history/stage-3.md) |
| 4. Learning content | ✅ Merged (PR #7), content follow-up merged (PR #8) | [stage-4.md](history/stage-4.md), [stage-4-content.md](history/stage-4-content.md) |
| 5. Results, final exam, pre-test, dashboard | ✅ Merged (PR #9, `505c33f`) | [stage-5.md](history/stage-5.md) |
| Decisions D32–D35 | 🟡 PR from `decisions-d32-d35`: attempt limit (D32), lessons need sign-in (D34), films served by Caddy with range requests (D35) | — |
| Deploy fix: Caddy reload | ✅ Merged (PR #11, `fcce8b6`): `deploy/caddy/` is mounted as a directory and `deploy.sh` validates then reloads Caddy on every deploy. Deployed to staging 13 Nov 2026; the reload ran and the config was valid. | — |
| 6. Staff tools | 🟡 On its branch: `stage-6-review` (2 commits on `505c33f`, the last marked "WIP, review not finished"); `stage-6` is the older copy on the old Stage 5 base | — |
| 7–10 | ⬜ In order. One stage = one branch = one PR. | — |

Earlier table and open items: [status-2026-11-12.md](history/status-2026-11-12.md).

**Live addresses.**
* Staging `https://staging.cyberfirstresponse.io` was **deployed on 13 Nov 2026 at `fcce8b6`** (Stage 5 code, D32–D35, Caddy validated and reloaded). Checked after: `/healthz/` and `/register/` return 200, `/learn/` goes to sign-in. It is a clean install with **no course loaded**: next the person loads the private course inputs (handoff notes §2–§3), creates an admin with 2FA, and checks a learner flow and a film. The server also reports "System restart required".
* Production `https://cyberfirstresponse.io` **returns 502 on purpose** until launch.

**Local course database.** The full course (55 readings, 509 live questions with hints, 18 graded parts, 9 films and handouts) exists only in local Docker databases and the private `content-data/`. On the lead's PC it is Compose project `csfr-restore` (restored 13 Nov 2026). Never `down -v` it.

## Open items owned by people, not code

| Item | Owner | Until then |
| --- | --- | --- |
| **35 fresh final-exam questions**: Set B **+18** (M1 +2, M2 +3, M3 +1, M4 +3, M5 +2, M6 +2, M7 +2, M8 +1, M9 +2), Set D **+17** (M1 +2, M2 +3, M3 +1, M4 +3, M5 +2, M6 +2, M7 +2, M9 +2). Single-choice, 1 mark, never met in a module quiz, practice or lesson check (D19, D31). Rejected reused IDs: [stage-5.md](history/stage-5.md). | Teammate A (content team) | See the next row. |
| **Sets B and D in the teammate's local database were released on 12 Nov with fillers from Sets A and C** (50 questions each, 18 pre-test). Has Teammate A approved those fillers? A released paper is fixed, so swapping in the fresh questions means a **new draft set** (D31). | Lead + Teammate A | Not recorded as approved. Staging and production have no sets yet. |
| **Set D's surplus Module 8 question** (6 fresh for 5 places): hold one in reserve, or the owner approves a blueprint change. Blueprint is 6/6/5/6/6/6/5/5/5 = 50; changing it needs the owner. | Repo owner / content team | One row held in `reserve`. |
| Module 8 page note "the crosswords stay in English" (D33): reviewed Hindi, Marathi and Gujarati wording | Teammate B + reviewers | Not built yet; build it with the wording (or in Stage 8). |
| Help, terms and grievance pages (D34 lists them as public) and the grievance officer, guardian-consent method (DPDP) | CyberPeace legal | Only `/privacy/` exists, as a draft. |
| Certificate qualification title, wording, signatories and number prefix (D28) | Lead + HOD, before Stage 7 | Stage 7 asks before building the PDF. |
| CCFR's own emblem | Lead | `.brand-emblem` in `templates/components/header.html` shows "CCFR" in text. |
| Consent from the three people whose photos are on the landing page | Lead | Photos stay in `content-data/people/`, never in git. |
| Module 10 capstone materials | Programme team | Module 10 shows Coming soon (D26). |
| Reviewed translations: lesson text, the 324 corrected-table drafts, the 509 hints (hi/mr/gu), Marathi and Gujarati film captions | Teammate B + reviewers | Lessons show draft translations with a tag; assessments stay English (D24); films have English and Hindi captions. |
| YouTube IDs (D18) | Content team | Films stay MP4 for now (D35). |
| **Fix before Stage 10: staging and prod share one Caddy (the `csfr-edge` stack), and its config comes from whichever checkout deployed last**, so a staging deploy also changes prod's routing (and could break it). Suggested fix: keep one fixed edge config outside both checkouts (e.g. `/srv/csfr/edge/caddy/`, installed from `main` by a separate `deploy/deploy.sh edge` step that validates and reloads), and stop `deploy.sh staging|prod` from touching Caddy. | Lead / next deploy-touching stage | Deploy staging and prod from the same ref, so the Caddyfile is the same. Reload itself is fixed (validated `caddy reload` on every deploy). |
| Staging deploy and course load; branch protection on `main` (PR + green CI, no force pushes) | A person with server / GitHub access | Nothing new is visible on staging. |

## Design calls still in force

One line each; the reasoning and check results are in `docs/history/`. Tell the lead if one looks wrong.

**Stage 1.** Public allauth sign-up is closed (`/accounts/signup` → `/register`). · Archived batches never accept registrations. · The email-budget alert fires at 150 a day. · A guardian consent link lasts 14 days; one consent tick. · `purge_unverified` (daily, 03:00 IST, `tasks` service) deletes accounts unverified after 7 days or still `pending_guardian` 7 days after the link expired. · Mentor "move learner": no batch → 400, a batch outside `batches_for(mentor)` → 403 + `access.denied`.

**Stage 2.** `validate_part()` blocks a part whose counted marks would exceed 100; `publish_part()` is the only way to set `is_published`. · `Module` 1–9 are counted, 10 is the uncounted capstone. · XLSX import is all-or-nothing and errors count data rows. · Option ids are internal; the browser gets random per-attempt tokens; scores are stored with `round1()`. · An auto-submitted attempt counts like a submitted one. · "Saved" needs the server's `X-Answer-Saved`; an expired session keeps the answer and saves it after sign-in. · The result page never shows option text, not even the learner's own pick. · htmx 2.0.4 is vendored without eval or inline styles.

**Stage 3.** Legacy markup is flattened to plain text; hotspot art is rasterised to a PNG with numeric regions. · The legacy mixed set (18) is practice and a `ProgrammeAssessment(kind="mock")`; mixed questions with no module go to Module 10. · Crosswords are practice-only except Module 8's graded Part B (D26). · Interactive questions need no PC tag. · A blank answer never triggers a safety gate; an untouched item scores 0 at submission; the result says right / partly right / not quite plus the hint.

**Stage 4.** ~~Lessons are readable without signing in~~: withdrawn by D34. · Inline interactions come from the module's own material; reveal and myth-or-fact answers stay on the server until asked. · `/learn/check` accepts only live practice-pool MCQs used by a published unit. · Minors write no `TimeLog`. · The Caddy CSP allows `script-src https://www.youtube.com` (for the YouTube player later). · Grant `content.publish_unit` in the admin to make a "Content publisher". · Legacy PDF-extraction fragments await the content team's review. · `publish_ccfr_course` loads the course from private inputs (preview without `--apply`); it has no automated test.

**Stage 5.** Exam sets B and D, one per batch, assigned by an admin and frozen per learner at the first programme exam (D31); released papers are fixed in the app and the database. · Go-live: `import_final_sets --source <xlsx>` (preview), `--apply`, then Admin → Exam sets → Check → Release, then pick the set on each batch. · A counted module with no published counted part keeps the final locked ("Course setup is incomplete"). · Combined results use unrounded question-level marks; the mean uses stored one-decimal attempt scores. · The pre-test prompt shows once after the first sign-in; "Later" goes to My progress. · The final shows overall % and bands; the pre-test the score only. · A question shown in any non-final attempt can't move into the final pool. · `eligible` ignores certificates until Stage 7. · The practice mock (D26) has no page yet.

**D32–D35 (this PR).** Every started attempt counts towards a limit; an attempt in progress always resumes; the pre-test takes no limit. · Signed-out GETs under `/learn/` go to sign-in and back; signed-out POSTs get 403. · Handout PDFs live in `apps/content/data/handouts/`, not `static/`. Captions (`static/captions/`) are still public static files. · Behind Caddy, `MEDIA_ACCEL_REDIRECT=1` and Caddy sends `/learn/media/<id>/` files from the read-only media volume.

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
