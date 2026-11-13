# Stage 9 progress (resume file)

Resume with: *"Read docs/STATUS.md and docs/history/stage-9-progress.md and continue Stage 9 from where the branch is."*

Branch: `stage-9` (from `main` at `a7d0b93`, Stage 8 merged). One PR. Model: Sonnet.
Brief from the lead: port the landing page; privacy, terms, grievance, help/FAQ and 404/500; 4 languages; mobile-first; Lighthouse accessibility >= 90.

## Calls made (from the lead's brief and decisions)

- Calls to action go to `/register/` and sign-in (D34: lessons need sign-in). The module list on the landing page is a non-linking list.
- Prototype wording changed because it contradicts decisions: "Learning never locked" / "no account needed" (D34), night mode (D21), "unlimited attempts" (D32 makes unlimited only the default), the practice-mock link (no page), "CSFR" to the programme name from settings (D23/D30).
- The first-response check has its own four short scenarios in `templates/landing.html`; none comes from a quiz, practice or final question.
- "Who runs it": a placeholder card until `PEOPLE_CONSENT_GIVEN=1` **and** all three photos exist in `PEOPLE_PHOTO_DIR` (default `content-data/people/`: `bhavesh-patel.jpg`, `nilakshi-jain.jpg`, `vineet-kumar.webp`). Served by `/people/<slug>/`, never as static files, never in git.
- Privacy, terms, grievance: placeholder text with a visible "Draft" notice until CyberPeace legal sends the wording.
- Emblem slot stays text "CCFR" (D23); the favicon and social image use the same text slot.
- Formats section is a plain grid of 10 formats, not the prototype's tabbed mock illustrations (less CSS and JS; nothing there needs scripting).
- The stage tabs, check tabs and FAQ are server-rendered and translated; `static/js/landing.js` only toggles `hidden`.

## Steps

| # | Step | State |
| --- | --- | --- |
| 1 | Branch, this file | done |
| 2 | `apps/core/faq.py` (shared FAQ), public views, URLs (`/terms/`, `/grievance/`, `/help/`, `/people/<slug>/`), 404/500, middleware allow-list, footer links | done |
| 3 | `templates/landing.html`, `static/css/landing.css`, `static/js/landing.js` | done; 847 tests pass |
| 4 | Favicon PNGs, apple-touch-icon, social preview image | todo |
| 5 | UI translation drafts (hi/mr/gu) for the new strings | todo |
| 6 | New tests (`tests/test_public_pages.py`) | todo |
| 7 | Lighthouse accessibility (>= 90) and screenshots (390/1366 in 4 languages, 360 in hi/mr/gu) | todo |
| 8 | Docs: architecture §31, CHANGELOG, STATUS; push; PR | todo |

## Notes

- Docker dev image had to be rebuilt (`docker compose -f deploy/compose.dev.yml build web`) because `django_jsonform` was missing from an older image.
- `templates/home.html` is gone; `templates/landing.html` replaces it (signed-in visitors see "Continue" instead of "Start certification").
