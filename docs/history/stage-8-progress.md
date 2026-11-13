# Stage 8 progress (resume file)

Resume with: *"Read docs/STATUS.md and docs/history/stage-8-progress.md and continue Stage 8 from where the branch is."*

Branch: `stage-8` (from `main` at `057c67b`). One PR for all of Stage 8 (the lead dropped the 8a/8b split on 13 Nov 2026).
The assessment part (reviewed translations of questions, options and hints inside assessments, mid-attempt switching) **must be built on Opus**.

## Private inputs (gitignored `content-data/`, never in git)

- `content-data/prototype/data/` — prototype `i18n/hi.js`, `mr.js`, `gu.js`, `catalog.js`, `mock.js`, `module-1..9.js`.
- `content-data/translations/translation-files-prefilled/` — the team's pre-filled sheets (7 Nov), CSV with
  `id, English, Hindi, Hindi status, Marathi, Marathi status, Gujarati, Gujarati status, Translator, Reviewer, Notes`.
  Every status is `draft - needs review` or `to translate`; the Reviewer column is empty. **Import all as `draft`.**
- `content-data/translations/translation-files/` — blank templates (3 Nov). Not imported.
- `content-data/translations/lesson-text-translation-files/` — lesson-text sheets (4 Nov), no `id` column, language columns blank.
- `content-data/ccfr-release/ccfr-table-translations.draft.json`, `content-data/outputs/…/CCFR-*-Translations.xlsx` — drafts from the hand-back.

## Steps

| # | Step | State |
| --- | --- | --- |
| 1 | Branch, this file | done |
| 2 | gettext locale files (hi, mr, gu) + Rosetta | in progress: Python strings wrapped; Rosetta in settings/urls; `.po` files not generated yet (needs Docker) |
| 3 | `Translation` table, `t(key, lang)`, source-hash staleness, reviewer permission per language | code written (`apps/translations/`), **untested, no migration yet** (Docker was not running) |
| 4 | XLSX export/import per module with validation | code written (`apps/translations/xlsx.py`, admin sheets page), untested |
| 5 | Draft importers + unmatched-keys report | code written: `apps/translations/drafts.py`, command `import_draft_translations` (preview; `--apply`), report to `content-data/outputs/translation-import-report.csv`. Not run yet |
| 6 | Header language switch saved to profile, lessons through `t()`, D33 note | code written. The switch already existed (Stage 1/1.5); lessons, modules, catalogue and reveal answers go through `t()`; "Draft translation" tag; D33 note reviewed-only. Untested |
| 7 | Assessments (Opus): reviewed translations only, mid-attempt switching, safety tests | code and tests written on Opus (`apps/translations/assess.py`, `tests/test_translated_assessments.py`). Not run yet |
| 8 | Checks, screenshots, CHANGELOG, STATUS, PR | |

## Next (needs Docker Desktop running)

1. Check the `django-rosetta` pin (`pip index versions django-rosetta` in the web container), rebuild the image.
2. `makemigrations translations content questions` (choice labels changed), run the new tests, fix.
3. `makemessages -l hi -l mr -l gu`; fill from phrases.js, the prototype i18n and `_framework-labels-verify.csv`; draft the rest; `compilemessages`.
4. Run `import_draft_translations` on the local `csfr-restore` DB: preview first, `--apply` only with the user's OK.
5. Screenshots (390, 1366, plus 360 in hi/mr/gu), CHANGELOG, STATUS, architecture §14, PR.

## Decisions so far

- Key grammar extended beyond §14 (documented in `apps/translations/keys.py`): `mod:<n>:<path>`, `part:<id>:name`, `note:<name>`.
- A paragraph is translated whole (spans joined); a translated paragraph keeps formatting only if it had one span.
- Crosswords have no translatable text paths (D33). The D33 note is `note:m8-crosswords-english`, shown only when reviewed.
- XLSX import: a line whose English column differs from the current English is saved against the sheet English, so it is stale (English shown).
- Admin edit of a line = a new draft by the editor. Review = admin action, per-language permission, never own upload, never stale.
- Rosetta is for staff with `upload_translations` or superusers; edits on a server are not kept across deploys (download and PR).
- `django-rosetta==0.10.2` pinned without checking PyPI (no Docker); verify on the next run.
