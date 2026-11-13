# Stage 4 review history

Moved verbatim from `docs/STATUS.md` (as of 12 Nov 2026, commit 505c33f) on 13 Nov 2026, when STATUS.md was trimmed. Historical record: the live status is in `docs/STATUS.md`, and later decisions (`docs/decisions.md`) win over anything here.

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
