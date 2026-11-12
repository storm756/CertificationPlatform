# Stage 5 notes history (PR #9)

Moved verbatim from `docs/STATUS.md` (as of 12 Nov 2026, commit 505c33f) on 13 Nov 2026, when STATUS.md was trimmed. Historical record: the live status is in `docs/STATUS.md`, and later decisions (`docs/decisions.md`) win over anything here.

## Stage 5: what to know (read before Stage 6)

* **Nothing can run the real exams yet: neither set can be released.** The pre-test and the final come from the batch's exam set (D31). Until a released set is assigned, learners see "not available yet" and the final stays locked with that reason. Tests and screenshots use invented questions only.
* **Exam-set blockers (from the private import preview, 12 Nov 2026; IDs and counts only).** Reused module-assessment rows are rejected, never released, and nothing was invented to replace them. Every set needs fresh, single-choice, 1-mark questions to reach the handoff blueprint 6/6/5/6/6/6/5/5/5:
  * **Set B:** 32 accepted, 18 reused rejected (M1-FB01, M1-FB02, M2-FB07, M2-FB08, M3-FB12, M3-FB13, M4-FB18, M4-FB19, M5-FB23, M5-FB24, M6-FB29, M6-FB30, M7-FB35, M7-FB36, M8-FB40, M8-FB41, M9-FB46, M9-FB47). Needs **18 more**: M1 +2, M2 +3, M3 +1, M4 +3, M5 +2, M6 +2, M7 +2, M8 +1, M9 +2. Pre-test: 2 accepted per module, complete.
  * **Set D:** 34 accepted, 16 reused rejected (M1-FD01, M1-FD02, M2-FD07, M2-FD08, M3-FD12, M3-FD13, M4-FD18, M4-FD19, M5-FD23, M5-FD24, M6-FD29, M6-FD30, M7-FD35, M7-FD36, M9-FD46, M9-FD47). Needs **17 more**: M1 +2, M2 +3, M3 +1, M4 +3, M5 +2, M6 +2, M7 +2, M9 +2; **Module 8 has 1 surplus** (6 fresh for 5 places): the content team picks which to hold back, or the owner approves a blueprint change. Pre-test: 2 accepted per module, complete.
  * No rows needed human review for scoring and none copied a module or practice question; the release checks run again in the admin before release.
* **To go live:** the content team adds the fresh rows to the private workbook; someone runs `manage.py import_final_sets --source <xlsx>` (preview), then `--apply` (draft questions, draft sets); an admin opens Exam sets → "Check" → "Release", then picks the set on each batch.
* **Review round 2 (12 Nov 2026).** Released papers are fixed (database-enforced); the reuse rule covers lesson checks and older question wording; drafts reconcile with the workbook (reserve / rejected states, atomic apply, shared row lock); workbook and release validation is shared; stale batch edits no longer revert an assignment; the catalogue, dashboard and exam pages use the real availability, lock and cooldown rules. A correction to a released set is a new draft set (its own tab letter in the workbook).
* **Blueprint** is 6/6/5/6/6/6/5/5/5 = 50 (`programme.DEFAULT_PER_MODULE`, editable on the final's `ProgrammeAssessment` row). Changing it needs the owner's approval.
* **Design calls made in Stage 5** (tell the lead if one is wrong):
  * A counted module with no published counted assessment, or an unpublished counted assessment, keeps the final locked and shows "Course setup is incomplete" (a content-team problem, not the learner's). Combined results use the unrounded question-level marks, not the stored one-decimal scores.
  * Attempt scores are stored to one decimal, so the mean uses those stored values; the worked example is tested both with full-precision parts and through real attempts.
  * The pre-test prompt is shown once, right after the first sign-in (`Profile.pretest_prompted_at`); "Later" goes to the dashboard, which keeps a pre-test card. A learner with no pre-test available is not prompted.
  * The final result shows the overall % and per-module bands only; the pre-test result shows the score only. Neither shows questions, hints or right/wrong marks.
  * A question that has been shown in any non-final attempt cannot be moved into the final pool (`Question.save` raises `PoolLocked`). The shared questions are written directly in the final pool, so showing them in the pre-test is allowed.
  * A learner whose batch has no set (or an unreleased one) sees "Your batch has not been given a final exam set yet" / "…is not ready yet". A learner who already started a programme exam keeps their frozen set and versions if the batch is reassigned or they move batch; new learners get the new set.
  * The practice mock has no page yet (a placeholder step on the journey strip).
  * `eligible` does not yet check for an issued certificate (Stage 7 sets `already_issued`).
