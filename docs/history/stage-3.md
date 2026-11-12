# Stage 3 review history

Moved verbatim from `docs/STATUS.md` (as of 12 Nov 2026, commit 505c33f) on 13 Nov 2026, when STATUS.md was trimmed. Historical record: the live status is in `docs/STATUS.md`, and later decisions (`docs/decisions.md`) win over anything here.

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
