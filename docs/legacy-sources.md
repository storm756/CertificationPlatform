# Legacy content: where it is and how to import it

> **Copy what you need now.** The old repo `storm756/csfr_Project` will be deleted before the first batch (D22). Put copies in `content-data/legacy/`, which is gitignored.

The old Moodle build (`github.com/storm756/csfr_Project`, also cloned at `D:\csfr-lms`) is **reference only**. We reuse its **content**, not its code.
Copy the files below into `content-data/legacy/` (gitignored). The importers in `importers/` read from there, run **once**, and refuse to run again if
any content has since been edited in the app.

| Content | Old path | Shape | Goes to |
| --- | --- | --- | --- |
| 405 MCQs (45 × modules 1–9) | `setup/bank_booklet.json` | `{ "1": [ {id, pc, t (R/A/S/I), q, o:[4], a (index)} ] }` | `Question(format=mcq)` + version. **Pool:** the content team's sheet decides `module_quiz` vs `practice`. Until then: 30 quiz / 15 practice, ≥5 per PC in the quiz. **Never `final`.** |
| Interactive assessments, Modules 1–9 (10 each) + a mixed set of 20 | `setup/scorm/src/m01…m09, m11/js/questions.js` | `window.CCFR_MODULE = {…, questions:[{type, …}]}` in 13 formats: mc, spot, chat, pick, build, crossword, settings, sort, match, order, dial, hotspot, cards | `Question` per challenge. The `type` gives the format schema. Module 8 crosswords → `practice`. The m11 mixed set → `practice` (mock). |
| Scoring rules for those formats | `setup/scorm/src/m11/js/engine.js` | JS functions per format (partial credit, wrong taps subtract, chat = points/max, gates) | Port to Python scorers. Freeze JS outputs as fixtures **once**, then compare. |
| Booklet web text (9 modules × 6 topics) | `setup/booklet_text.json` | `{ "1": { "0": {title, blocks:[{type:h/p/ul/kv/cols/ssr/case/remember, …}]} } }` | Reading units (blocks). Five tables are jumbled (m1.t0, m1.t4, m2.t3, m4.t0, m4.t3); the content team sends fixed versions. |
| Lesson data (outcomes, how it works, stop/save/report, myths…) | `setup/modules.php`, `setup/modules_ext.json` | PHP array / JSON per module | Module overview + reading units. Myths and games → practice checks. |
| Translations (drafts) | `setup/i18n/booklet_i18n.json`, `setup/i18n/ui.json` | `{hi:{English text: translation}, mr:…, gu:…}` | **Don't import this file directly.** Its drafts are already in the team's pre-filled sheets (id + status), which come back reviewed and go through the normal XLSX import (Stage 8). |
| Films | YouTube channel (being uploaded) | video IDs in the team's sheet | Video units (YouTube ID) |
| Film transcripts | `setup/files/videos/m1…m9.json` | `{lines:[{t0, t1, zh, en}]}`. **Keys are swapped: `zh` = English, `en` = Hindi.** | Already converted to .srt/.vtt for YouTube. Optional: transcript text under each film. |
| Handout PDFs | `setup/files/modules/m1–11.pdf` (not in git; ask the lead) | PDF | Handout units (download) |
| Landing page | `landing/` | static | **Superseded by D20:** port the prototype's `index.html` instead (Stage 9). The old landing is not used. |
| Theme look | `landing/tokens.css`, `custom/theme/csfr/scss/pre.scss` | colour/font tokens | **Superseded by D20:** the tokens come from the prototype's `css/base.css` (Stage 1.5). |
| Programme spec | `Certificate_in_Cyber_Incident_First_Response_Complete_Booklet.pdf` (303 pp) | PDF | Background only. Where it disagrees with `decisions.md`, **decisions.md wins**. |
