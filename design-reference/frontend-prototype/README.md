# CSFR frontend (standalone, no backend)

The complete frontend for the Community Cyber First Responder platform, built from the handoff docs (`CLAUDE.md`, `docs/architecture.md`, `docs/decisions.md`) and the legacy content in `D:\csfr-lms`. It is plain HTML, CSS and vanilla JS: no framework, no build step, no backend. The Django app in the parent folder is untouched.

## Run it

```bash
node server.mjs --port 4180
```

Then open `http://localhost:4180`. Opening `index.html` directly from disk also works, because all data is loaded as `<script>` files.

## Pages (19 files)

| Area | Pages |
| --- | --- |
| Public | `index.html` (landing), `modules.html` (catalogue), `module.html?m=1…10`, `verify.html` (QR verification), `help.html`, `privacy.html`, `terms.html`, `grievance.html`, `404.html`, `500.html` |
| Accounts | `signin.html` (with reset and "check inbox"), `register.html` (enrol: live certificate-name preview, age rules, guardian step, closed and "batch fills" states), `guardian.html` (consent and learner waiting page) |
| Learning | `unit.html?m=N&u=film·t1…t7·handout·check·practice·xw` (course player with outline sidebar) |
| Assessment | `assessment.html?m=N&part=mcq·int`, `?part=mock`, `?part=pretest`, `?part=final` (intro, attempt, review, confirm, result) |
| Learner | `dashboard.html` (My progress), `final.html`, `certificate.html` |
| Staff | `mentor.html` (batches, registration controls, auto-issue, approvals, stuck learners, heatmap, CSV) |

**Preview controls:** sign in with any email and password, as Learner or Mentor. The dashboard, final and certificate pages have a scenario switcher: *Your activity* (real progress on this device), *New*, *Mid-way*, *Final ready* and *Certified*. Sample scores use the worked example from architecture §10.3, so *Certified* gives 62.0%, grade B.

## Content (real, from the legacy repo)

`tools/build_data.py` converts the legacy files into `data/*.js`:

- **9 modules:** titles, taglines, hours and outcomes, plus 6–7 booklet readings each (56 topics in total), the full handout (pages 1–8 of each module PDF), Stop/Save/Report, myth-or-fact checks, film posters and timed transcripts (English and Hindi).
- **Questions:** 30 MCQs for Part A and 15 for the practice quiz per module, per the decisions.md rule (≥5 per PC). Part B is the module's 10 interactive challenges, and there is an 18-round mixed practice mock.
- **Module 8:** the crosswords are practice only, and the graded Part B shows a "being replaced" notice.
- **Module 10 (capstone):** there is no legacy content, so it is shown as a content slot.

```bash
python -I tools/build_data.py D:/csfr-lms .
```

### No answer keys reach the browser

Every question goes through a **whitelist projection for each format**, matching architecture §9.2. Only safe fields are copied: no `a`, `ok`, `want`, `answer`, `b`, `s`, `gate`, `why`, `[[!markers]]`, colour hints or canonical order. Order and match items are pre-shuffled, and spot segments are all identical buttons. `verify()` fails the build if a key field survives. The browser never scores: result pages show the layout with labelled **sample numbers**.

`data/` is gitignored (`.gitignore` in this folder). **Never commit it.** It holds question data, and the repo is public.

## Features

- **Languages:** English, Hindi, Marathi and Gujarati, on every page: landing, sign-in, registration, guardian consent, modules, units, handouts, assessments (instructions and buttons), dashboard, final, certificate, verification, mentor, help and legal pages. Interface keys live in `js/i18n.js`. Page text is translated from the phrase table in `js/phrases.js` (loaded only for hi/mr/gu, keyed by the exact English text, with `{0}` patterns for text that contains numbers, such as "33% complete"; patterns listed in `CSFR_PHRASE_FREE` may also hold names, codes or grade letters). Lesson content (readings, overviews, handouts, film captions, game titles) comes from the legacy drafts plus our own rows in `translations/<name>.json` (same order as `translations/src/<name>.en.json`), merged into `data/i18n/` by `tools/build_data.py`. All of these are drafts pending native review, and a banner says so. Assessment questions and options stay in English (architecture §14). Names, emails, certificate codes and sample data are not translated. Switch with the header select, a footer link or `?lang=hi`.
- **Night mode:** follows the system setting, with a toggle in the header that is remembered. The header and partners band stay light at night, because both partner logos need a calm, light surface.
- **Fonts:** Baloo 2 and Hind are self-hosted (latin and devanagari) from the legacy landing. There is no Hind Vadodara file yet, so Gujarati falls back to the system font.
- **Accessibility:**
  - skip link and visible focus
  - roving-tab keyboard support
  - every drag has a tap or select alternative
  - non-colour status icons
  - 44–48 px tap targets
  - text contrast ≥ 4.5:1
  - reduced motion and forced colours respected
- **Mobile:** no horizontal scroll at 375 px, a collapsible course outline, and a sticky attempt bar.

## Known gaps and follow-ups

- **Films:** the MP4 files and YouTube IDs aren't available, so the player plays the narration as captions over the poster.
- **Handout PDFs:** not on disk.
- **Legacy tables:** some have jumbled cells left over from PDF extraction (for example m1.t0, m1.t4, m2.t3 and m4.t3). The content team is sending fixed versions.
- **Content slots:** legal text (privacy, terms, grievance), the guardian privacy notice and the capstone.
- **Sample data:** the batch names and mentor roster are clearly labelled samples.
- **Real scoring, sessions, email and PDFs:** all of this belongs to the Django backend.
