# Stage 1 review history

Moved verbatim from `docs/STATUS.md` (as of 12 Nov 2026, commit 505c33f) on 13 Nov 2026, when STATUS.md was trimmed. Historical record: the live status is in `docs/STATUS.md`, and later decisions (`docs/decisions.md`) win over anything here.

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
