# Stage 8 progress (resume file)

Resume with: *"Read docs/STATUS.md and docs/history/stage-8-progress.md and continue Stage 8 from where the branch is."*

Branch: `stage-8` (from `main` at `057c67b`). One PR for all of Stage 8 (the lead dropped the 8a/8b split on 13 Nov 2026).
The assessment part (reviewed translations inside assessments, mid-attempt switching) was built on Opus, as the reviewer asked.
Design notes: `docs/architecture.md` §30.

## Private inputs (gitignored `content-data/`, never in git)

- `content-data/prototype/data/` — prototype `i18n/hi.js`, `mr.js`, `gu.js` (English → text), `catalog.js`, `mock.js`, `module-1..9.js`.
- `content-data/translations/translation-files-prefilled/` — the team's pre-filled sheets (7 Nov): `id, English, Hindi, Hindi status, …`.
  Every status is `draft - needs review` or `to translate`; the Reviewer column is empty. **All imported as `draft`.**
  `_framework-labels-verify.csv` has its columns shifted one to the left (English under `id`); the reader detects it.
- `content-data/translations/translation-files/` — blank templates (3 Nov). Not imported.
- `content-data/translations/lesson-text-translation-files/` — lesson-text sheets (4 Nov), no `id` column, language columns blank. Nothing to import.
- `content-data/ccfr-release/ccfr-table-translations.draft.json` — 324 corrected-table drafts (imported as drafts).
- `content-data/outputs/…/CCFR-Question-Hints-with-Translations.xlsx` — hint workbook; **its hi/mr/gu columns are empty**, so nothing imports.
- `content-data/outputs/ui-drafts.json` — the UI drafts written in this stage (input to `fill_ui_drafts --extra`). They are already in the committed `.po` files.

## Steps

| # | Step | State |
| --- | --- | --- |
| 1 | Branch, this file | done |
| 2 | gettext catalogues (hi, mr, gu) + Rosetta | done: 658 strings per language, all drafts (`draft: needs review`); `django-rosetta==0.10.3`; gettext in the dev image |
| 3 | `Translation` table, `t()`, source-hash staleness, reviewer permission per language | done, migration `translations/0001` |
| 4 | XLSX export/import per module with validation | done |
| 5 | Draft importer + unmatched report | done (`import_draft_translations`). Local `csfr-restore` DB: migration applied, **preview only** (about 3,600 draft lines would import; 1,131 unmatched, mostly UI phrases and jumbled old tables) |
| 6 | Language switch (already existed), lessons through `t()`, D33 note | done |
| 7 | Assessments: reviewed only, mid-attempt switching, safety tests | done on Opus |
| 8 | Engine labels translated (json_script table) | done |
| 9 | Checks | done: ruff, 847 tests, `check --deploy`, `makemigrations --check` |
| 10 | Docs: architecture §30, CHANGELOG, STATUS | done |
| 11 | `import_draft_translations --apply` on the local DB (needs the user's OK), screenshots 390/1366 + 360 in hi/mr/gu, PR | next |

## Decisions so far

- Key grammar extended beyond §14 (documented in §30 and `apps/translations/keys.py`): `mod:<n>:<path>`, `part:<id>:name`, `note:<name>`.
- A paragraph is translated whole (spans joined); a translated paragraph keeps formatting only if it had one span.
- Crosswords have no translatable text paths (D33); the engine's crossword labels stay English. The D33 note is `note:m8-crosswords-english`, reviewed-only.
- Lesson practice checks (`/learn/check`) count as assessment text: reviewed only.
- XLSX import: a line whose English column differs from today's English is saved against the sheet English, so it is stale.
- Admin edit of a line = a new draft by the editor. Review = admin action, per-language permission, never own upload, never stale.
- Rosetta is for staff with `upload_translations` or superusers; edits on a server are lost at deploy (download and PR).
- The engine-label `json_script` block is the one inline `<script>` allowed on attempt pages (JSON data, never executed).
