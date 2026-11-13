# Stage 7 (certificates): build notes (13 Nov 2026, branch `stage-7` from `main` at `5a25aac`)

* **Built to D36** with the placeholder design. The lead's decisions are D36 in `docs/decisions.md`; the code notes are architecture §29.
* **Design calls made in Stage 7** (tell the lead if one is wrong):
  * Guard A (the lead's choice): a warning on the mentor batch page and in the admin while any signature image is missing or `CERTIFICATE_DESIGN_FINAL` is off. It does not block approving.
  * "Completed on" is the date the learner's result was achieved: the latest submission among those giving their best scores. On a tie the earliest wins, so retaking for the same score never moves the date.
  * A revoke blocks a new certificate unless the admin ticks "Allow a new certificate" (for example a name correction). The new one gets a new number.
  * Signatories (names and designations) live in settings, so a change is a reviewed PR. Signature images are files in `media/private/signatures/` on the server.
  * "Awaiting approval" lists every eligible learner without a certificate, whatever the auto-issue switch says, so a learner an automatic step missed is never lost. "Approve all" issues at most 15 per click (each render takes about 0.4–0.8 s).
  * A stale auto-submit (the `tasks` job) never issues: that container has no media volume. Those learners wait for approval.
  * A revoked certificate's verify page shows qualification, issue date and "Revoked by the programme", never the name.
  * The verify page is limited to 30 checks per 10 minutes per client IP (X-Forwarded-For from Caddy).
* **Checks:** ruff and format clean, `makemigrations --check` clean, `check --deploy` (prod settings) clean, full suite 740 passed (34 new in `tests/test_certificates.py`: Journeys 12 and 13, PDF injection and the fetcher allowlist, revoke, erase, the verify page and its rate limit, owner-only download, mentor scoping, the guard, NSQF). Screenshots at 390px and 1366px of `/certificate/`, `/start/`, `/verify/<code>/`, `/verify/`, an unknown code and the mentor batch page: axe 0 serious or critical, no sideways scroll. Sample PDFs (Latin, Devanagari, Gujarati, a long name) and one PDF issued through the real flow, rendered to PNG. All in `screenshots/stage-7/` (not committed).
* **Not built (follow-ups):** a check that a name only uses scripts the certificate fonts cover (Latin, Devanagari, Gujarati); other scripts would print as empty boxes.
