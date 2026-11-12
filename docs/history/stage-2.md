# Stage 2 review history

Moved verbatim from `docs/STATUS.md` (as of 12 Nov 2026, commit 505c33f) on 13 Nov 2026, when STATUS.md was trimmed. Historical record: the live status is in `docs/STATUS.md`, and later decisions (`docs/decisions.md`) win over anything here.

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
