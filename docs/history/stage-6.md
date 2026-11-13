# Stage 6 (staff tools): notes from the first build

(moved here from STATUS.md; the original heading was "Stage 6: what to know (read before Stage 7)")

* **Certificates are Stage 7.** "Awaiting approval" shows eligible learners, "issued this week" is 0, and the admin actions **approve** and **revoke** are not built yet (there is no certificate table). The auto-issue switch is stored and audited now.
* **Where:** mentors use `/mentor/batches/<id>/` (dashboard, CSV) and `/staff/questions/`; admins also have `/staff/marks/` (mark split with impact preview) and `/staff/report/`. Batch open/close are actions in the Django admin; moving a learner is on the learner page (admins can move between any batches).
* **Design calls made in Stage 6** (tell the lead if one is wrong):
  * Question editing is a **JSON editor checked against the format's pydantic schema** on save (readable errors), not django-jsonform: it adds no dependency and cannot drift from the schemas. A schema-driven form can replace it later without changing the pages' rules.
  * A mentor's edit (or an admin's, unless they tick "keep live") adds a new version and sends a live question back to **draft**; only an admin publishes. Mentors cannot select the final pool, and the pool rule (§11) still applies in the editor.
  * The impact preview counts who **meets every requirement** with and without the change (it ignores missing course content, which is reported separately as "course set-up would still be incomplete"). Marks over 100 are refused; confirming recomputes the impact, saves, and audits the counts.
  * Stuck learner = no activity for 7+ days, or below 50% on a part after 3 attempts.
  * CSV cells that start with `=`, `+`, `-`, `@`, tab or CR (also after leading spaces) get a leading apostrophe; the file is UTF-8 with a BOM and is a POST-only, no-store download.
* **Verified:** mentors get 403 (and an audit line) for another batch's dashboard, learner, export and auto-issue, and for final-pool questions (list, edit, preview, publish, or posting `pool=final`); the Django-admin question list hides the final pool from non-admin staff.
