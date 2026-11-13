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
| 2 | gettext locale files (hi, mr, gu) + Rosetta | next |
| 3 | `Translation` table, `t(key, lang)`, source-hash staleness, reviewer permission per language | |
| 4 | XLSX export/import per module with validation | |
| 5 | Draft importers + unmatched-keys report | |
| 6 | Header language switch saved to profile, lessons through `t()`, D33 note | |
| 7 | Assessments (Opus): reviewed translations only, mid-attempt switching, safety tests | |
| 8 | Checks, screenshots, CHANGELOG, STATUS, PR | |

## Decisions so far

- None beyond the brief yet.
