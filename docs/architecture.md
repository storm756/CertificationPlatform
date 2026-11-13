# Community Cyber First Responder (CCFR) Certification Platform: Architecture v2 (consolidated)

* **Status:** Approved design. This is the single source of truth.
* **Date:** 2026-11-07
* **Binding requirements:** `docs/decisions.md`. Decisions D20 and later override this document where they differ; Stage 1.5 folded them in (see §22).

---

## 1. Requirements in one table

| Area | Rule | Source |
| --- | --- | --- |
| Certificate result | Overall = **50% × average of counted modules + 50% × final** | D1 |
| Module score | Each module = **100 marks**, split across its assessment parts (today MCQ 50 + Interactive 50) | D11 |
| Pass marks | Every counted module ≥ **50%**, final ≥ **50%** | D2 + recommendation |
| Learning | **Never locked** | D2 |
| Final unlock | Every counted part of every counted module submitted **with all questions answered**, plus the pre-test done | D2, D15, §11 |
| Attempts | **Unlimited**. The best counted attempt per part counts. A timer is shown but not enforced. | D3 |
| Feedback | Score + which questions were wrong + a hint. **Never the correct option.** | D13 |
| Final protection | Random draw per learner, shuffled questions and options, per-module **bands**, no answers shown. Optional wait between attempts (off). | D14 |
| Safety gate | An attempt containing a gate choice is shown but **never counts** | review |
| Registration | Self-register with email, **only into a batch that is open right now** (including the catch-all pool, which is closed by default) | D4, D9 |
| Age | **16+.** Under-18s need **guardian consent** and get no behavioural tracking. | D16 |
| Certificate | English only, on the website (no email), **name as typed at registration**, per-batch auto-issue switch, otherwise the mentor approves | D10, D17 |
| Email | Brevo, 300/day, **only** for verification, password reset and guardian consent | D10 |
| Content | Staff upload Word/text/images/PDF and add **YouTube** films. Assessments via form or spreadsheet. | D11, D18 |
| Hidden for now | Practicum, portfolio, viva | D6 |
| Languages | en, hi, mr, gu; the team reviews everything | D7 |

---

## 2. System overview

```text
 learners (phones, 4G) · mentors · admins · public (QR verify)
        │ HTTPS
┌───────▼──────────────────── Hostinger KVM 2 · Ubuntu 24.04 ───────────────────────────┐
│ Caddy ── TLS, security headers, /static; /media only after Django says "logged in"    │
│   │                                                                                   │
│ Django 5.2 (gunicorn) ── HTML pages + small JSON endpoints; ALL scoring happens here  │
│   │                                                                                   │
│ PostgreSQL 17 (private network only; two roles: csfr_owner for migrations,            │
│                csfr_app for runtime)                                                  │
│ tasks container ── same image as web; `run_periodic` daily jobs (D27), as csfr_app     │
│ cron container ── hourly encrypted DB dump + nightly media → off-site (write-only)     │
│ (staging = same images, own DB + own secrets + mail sink)                             │
└───────────────────────────────────────────────────────────────────────────────────────┘
   outbound: Brevo SMTP (email) · Sentry (errors, scrubbed) · uptime pinger
   embedded in pages: YouTube (youtube-nocookie.com) players
```

**How a request flows:** the browser asks Caddy. Caddy serves static files itself and passes the rest to Django. Django checks the session and
the role, reads and writes PostgreSQL, and returns HTML. The interactive engine (JS) posts answers to Django, and Django scores them. **The browser never holds
an answer key.**

---

## 3. Technology

| Layer | Choice | Why |
| --- | --- | --- |
| Language / framework | Python 3.12, **Django 5.2 LTS** (security fixes until April 2028) | Batteries included and secure defaults |
| Database | **PostgreSQL 17** | JSONB for question bodies and answers, partial unique indexes, row locks, data stays in India |
| Pages | Django templates + **HTMX**, built from one shared `base.html` and reusable component partials (`templates/components/`) | Fast on cheap phones, one codebase |
| Look | Shared CSS taken from the approved prototype (D20): `static/css/{tokens,fonts,base,app}.css`. No CSS framework. **One light theme, no night mode (D21).** Fonts self-hosted: Baloo 2 and Hind (Latin, Devanagari), Baloo Bhai 2 and Hind Vadodara (Gujarati) | Matches the approved design on a cheap Android phone on 4G |
| Browser JS | A few small external files in `static/js/`, no framework, no inline scripts or styles (the CSP from Caddy forbids them) | |
| Interactive engine | Vanilla **TypeScript** → esbuild → one JS file (a port of the teammates' renderer, without scoring) | |
| Accounts | **django-allauth** (email login, verification, reset, email change, rate limits) + **allauth.mfa** (staff TOTP) | Proven code for the subtle flows |
| Admin UI | **Django admin themed with django-unfold** + custom actions | No second hand-built admin panel |
| Imports | **django-import-export** (XLSX with dry-run and row errors) | |
| JSON editing | **django-jsonform**, with **pydantic** schemas per question format | Validates on import, on save and at scoring |
| History | **django-simple-history** (admin edits) + an `audit()` helper (domain events) | |
| Rate limits | django-ratelimit (+ allauth's built-in limits) | |
| UI-string translation | Django gettext + **django-rosetta** | |
| Documents | **mammoth** (DOCX → blocks), **nh3** (sanitise), **defusedxml**, **WeasyPrint** (certificate PDF), **segno** (QR) | |
| Video | **YouTube** unlisted, privacy-enhanced embed, IFrame Player API | D18, §8.2 |
| Ops | Docker Compose, **Caddy**, sentry-sdk, an external uptime pinger | |

**Not used:** Redis, Celery, a job queue, Wagtail, a React SPA, JWT. Each was considered and rejected; the review history has the reasons. The one background process is the `tasks` loop (D27): the web image running `manage.py run_periodic`, which only runs a few daily jobs. It is not a queue.

---

## 4. Code layout

```text
csfr-platform/                (git repo, cloned to D:\ locally — not OneDrive)
├── config/                   settings/{base,dev,staging,prod}.py, urls.py
├── apps/
│   ├── accounts/             User (custom, email login), Profile (erasable PII), guardian consent, allauth adapters
│   ├── batches/              Batch, BatchMentor, Enrolment, is_accepting()
│   ├── content/              Module, Unit, UnitVersion (blocks), MediaAsset, DOCX import
│   ├── questions/            Question, QuestionVersion, format schemas (pydantic), client_projection(), scorers
│   ├── assessments/          AssessmentPart, ProgrammeAssessment, Attempt, AttemptItem, draw(), submit()
│   ├── learning/             UnitProgress, TimeLog, learn-mode check
│   ├── results/              policy.py (constants), compute_results(), rounding
│   ├── certificates/         Certificate, issue(), revoke(), PDF, verify page
│   ├── i18n/                 Translation, XLSX round trip, reviewer workflow
│   ├── dashboards/           learner, mentor, admin report pages, CSV export
│   └── audit/                AuditEvent, audit()
├── engine/                   TypeScript renderer for the 13 formats
├── importers/                one-time import of the existing material (booklet text, 405 MCQs, 90 challenges, films)
├── templates/                base.html, components/ (partials), allauth/ (element overrides), one folder per app
├── locale/                   our own gettext catalogues (hi, mr, gu; Django ships none for Gujarati)
├── tests/                    pytest (unit, integration) · Playwright (journeys in §18)
├── deploy/                   compose.yml (per-env stack), compose.edge.yml (shared Caddy), compose.dev.yml, caddy/Caddyfile, backup/ + restore.sh, server/bootstrap.sh
├── static/                   css/ (tokens, fonts, base, app, stage), js/ (ccfr-shell.js, ...), fonts/ (woff2 + OFL licences), img/ (logos, icons.svg sprite)
├── design-reference/         the approved frontend prototype: the look only, never code to copy (D20)
├── tools/                    screenshots.mjs (Playwright screenshots + axe), used by every PR
└── docs/                     these documents (STATUS.md first, then decisions.md)
```

---

## 5. Roles and permissions

| Action | Learner | Mentor (own batches only) | Admin |
| --- | --- | --- | --- |
| Study, attempt, see own results and certificate | ✔ | — | — |
| See a batch roster, scores, hours | — | ✔ | ✔ all |
| Create a batch | — | ✔ (auto-assigned to it) | ✔ |
| Open or close registration, set the window and seats | — | ✔ | ✔, including the catch-all pool |
| Move a learner between batches | — | only between batches they mentor | ✔ |
| Generate a one-time password-reset link | — | ✔ | ✔ |
| Change a learner's certificate name | — | ✔ (logged) | ✔ |
| Approve or issue certificates, auto-issue switch | — | ✔ | ✔ |
| Revoke a certificate | — | — | ✔ |
| Draft content (blocks, uploads, YouTube links) | — | ✔ | ✔ |
| Publish content | — | if given the "Content publisher" permission | ✔ |
| Add, edit or import questions (module quiz / practice pools) | — | ✔ (draft) | ✔ |
| See or edit **final-pool** questions | — | ✘ | ✔ |
| Change a module's mark split, or counted parts or modules | — | ✘ | ✔ (with impact preview) |
| Review translations | team members holding the per-language **Reviewer** permission (never their own uploads) | | |
| Django admin raw access, audit log, settings | — | — | ✔ (2FA) |

Mentors and admins **must** use 2FA (TOTP). A lost device is reset by an admin, and a second admin is notified.

---

## 6. Data model

★ marks a database-enforced constraint. All tables have `id`, `created_at` and `updated_at`.

**People**

| Table | Fields |
| --- | --- |
| User | email ★unique, email_normalized ★unique (lower-case; Gmail dots and `+tag` removed), password (Argon2), role, is_active, status (`pending_guardian` / `active` / `disabled`) |
| Profile *(erasable PII)* | user, **certificate_name**, date_of_birth, preferred_language, phone (optional, unused for now) |
| GuardianConsent | user, guardian_name, guardian_email, token_hash, sent_at, confirmed_at, declaration_text_version |
| ConsentRecord | user, notice_version, purpose, given, at, ip (append-only) |

**Batches**

| Table | Fields |
| --- | --- |
| Batch | name, code ★unique, centre, **centre_code** (2–6 capitals/digits, default `SAKEC`, printed in certificate numbers, D36), start/end dates, accepting (on/off), opens_at, closes_at, seat_limit (default 40), is_open_pool ★only one, auto_issue (off), status (active / archived) |
| BatchMentor | batch, mentor ★unique pair |
| Enrolment | user ★unique, batch, joined_at. **One current batch per learner**; history lives in the audit log. |

**Content**

| Table | Fields |
| --- | --- |
| Module | number, slug, title_key, hours, kind (`learning` / `capstone`), **counted** (yes/no), order |
| Unit | module, order, type (`video` / `reading` / `handout` / `check` / `practice_quiz`), nominal_minutes |
| UnitVersion | unit, version, blocks JSONB (validated), status (draft / published / superseded), author, published_by |
| MediaAsset | module, kind (pdf / image / caption / mp4), language, path, sha256, size |

**Questions**

| Table | Fields |
| --- | --- |
| Question | stable_id ★unique (e.g. `M4-12`, `M4-C03`), module, **format** (`mcq` + 13 interactive), tags (pc, item_type), **pool** (`module_quiz` / `final` / `practice`), is_anchor, points (default 1), status (draft / live / retired) |
| QuestionVersion | question, version, body JSONB (**pydantic-validated per format**; includes key, scoring rule, gate flags, hint), content_hash. **Never edited**: a change makes a new version. |

**Assessments**

| Table | Fields |
| --- | --- |
| AssessmentPart | module, name, format family (mcq / interactive), **marks** (0–100), **counted** (yes/no), selection (`all` / `all_shuffled` / `draw`), draw_n, min_per_tag, pool, time_display_minutes (null = count-up) |
| ProgrammeAssessment | kind (`final` / `pretest`), blueprint JSONB `{per_module: {module_id: n}, anchors: [ids]}`, time_display_minutes, cooldown_hours (0) |
| Attempt | user, part **or** programme_assessment, number, status (`in_progress` / `submitted` / `auto_submitted`), started_at, last_saved_at, submitted_at, score (Decimal), all_answered (yes/no), gate_breached (yes/no), counted (= submitted AND not gate_breached) |
| AttemptItem | attempt, position, question_version, **points (frozen)**, option_map JSONB (shuffled order + one-off tokens), response JSONB, score (0–1 Decimal), gate_flag |

Attempt constraints:
* ★ unique (user, part, number)
* ★ **partial unique index:** one `in_progress` attempt per (user, part) and per (user, programme_assessment)

**Learning activity**

| Table | Fields |
| --- | --- |
| UnitProgress | user, unit ★unique pair, completed_at |
| TimeLog | user, unit or part, date, seconds. **Not recorded for under-18s** (§8.3). |
| LearnCheck | user, question_version (practice pool only), score, at |

**Certificates, translations, audit**

| Table | Fields |
| --- | --- |
| Certificate | user, serial ★unique (global DB sequence `certificate_serial`), certificate_no ★unique, verify_code ★unique (random, Crockford base32), status (`issued` / `revoked`), snapshot JSONB, pdf_path, pdf_sha256, issued_at, issued_by (user, or none with auto_issued), revoked_at / revoked_by / revoked_reason, reissue_allowed, holder_erased_at. ★ **partial unique: one `issued` certificate per user.** |
| CertificateSettings | one row: nsqf_approved, nsqf_level, nsqf_credits (★ approved needs both) |
| Translation | key, language ★unique pair, text, source_hash, status (draft / reviewed), uploaded_by, reviewed_by (≠ uploaded_by) |
| AuditEvent | actor_id, action, target_type, target_id, data JSONB (**IDs, not names**), ip, at. The runtime DB role has INSERT/SELECT only. |

**There are no stored results.** Module %, overall %, eligibility and blockers are always computed (§10).

---

## 7. Registration and accounts

### 7.1 `is_accepting(batch, now)`

```text
accepting == on
AND (opens_at is null OR opens_at ≤ now)
AND (closes_at is null OR now < closes_at)
AND seats_used < seat_limit        seats_used = verified enrolments + unverified ones younger than 48 h
```

### 7.2 Sign-up flow

```text
GET /register
  no batch passes is_accepting → "Registrations are closed right now. Ask your trainer to open registration." (no form)
  otherwise → form:
     full name for certificate  ← label: "This exact name will be printed on your certificate. Check the spelling now."
     email · password · language · date of birth · batch (only accepting batches; pool shown only if open)
     consent ticks (privacy notice v-N)
POST /register  (rate-limited per batch, not per IP — classrooms share Wi-Fi)
  ONE transaction: lock the batch row → re-check is_accepting → normalise email → uniqueness
     closed meanwhile → "Sorry, this batch is not accepting registrations." (form values kept)
  create User + Profile + Enrolment + ConsentRecord
  age = from date of birth:
     < 16  → refuse: "You must be 16 or older to join."
     16–17 → status = pending_guardian → ask guardian name + email → guardian email (§7.3)
     ≥ 18  → status = active
  send verification email (allauth). Page says "Check your inbox" (same text if the email already exists → no account fishing)
```

* **Email normalisation** (Gmail dots and `+tag`) is a setting: **on in prod, off on staging**, so testers can use `name+test1@…` accounts.
* **Certificate-name confirmation:** the form shows a preview line, *"Your certificate will read: ASHA R. DESAI"*. After registration the name is
  locked. Only a mentor or admin can change it (logged).
* **Unverified accounts** are deleted after 7 days. If the batch has closed by then, a mentor can issue a one-time registration link.
* **Email budget:** at most 1 email per address per 24 hours on the duplicate and reset paths. Daily budgets: registration 150, reset and guardian 100, reserve 50. Admin
  alert at 150.

### 7.3 16–17-year-olds (D16, DPDP)

* The guardian receives an email with a link. It leads to a page that states what data is collected and why, and the guardian confirms with their name and a
  declaration that they are the parent or guardian. Until then the learner can log in only to a "waiting for your guardian" page.
* **No behavioural tracking of minors.** The time-on-task heartbeat is off for them (§8.3). Their hours are counted as the nominal minutes of the units they complete.
* **Open item for CyberPeace legal:** confirm that guardian email confirmation plus a declaration is an acceptable "verifiable consent" method under the DPDP Rules,
  or name the required method (e.g. a DigiLocker-based check). The design isolates this in `GuardianConsent`, so the method can change without touching anything else.

### 7.4 Sessions and recovery

| Topic | Rule |
| --- | --- |
| Sessions | 14 days with "remember me", 12 hours for staff. Rotated at login. HttpOnly, Secure, SameSite=Lax. |
| Login limits | allauth login rate limits. Messages are the same whether or not the email exists. |
| Password reset | allauth email link, or a **mentor-generated one-time link** (valid 1 hour) to hand over in person. A mentor link ends all the learner's sessions, shows them a banner at next login, and blocks an email change for 7 days. |
| Email change | Re-verified at the new address, and the old address is notified |

---

## 8. Learning

**Sign-in (D34).** Every `/learn/` page and endpoint needs a signed-in user. A signed-out GET goes to sign-in and back (`?next=`); a signed-out POST gets 403. Progress and time are recorded for learners only.

### 8.1 Module page

* Film (YouTube)
* Handout (web text + PDF)
* Online units (reading, check, practice quiz)
* Assessment parts, each with its best % and a Retake button

Nothing is locked.

### 8.2 Films on YouTube (D18)

> **For now (D35) the films are uploaded MP4s** with English and Hindi caption tracks, served as described in §16 (Media). YouTube comes later; the rest of this section describes that later step.

* The films are uploaded to a **programme-owned YouTube channel** (CyberPeace or SAKEC, not a personal account) as **Unlisted**.
* They are embedded with **`youtube-nocookie.com`** (privacy-enhanced mode). The CSP allows only that frame origin.
* The **IFrame Player API** reports progress, and the unit is marked complete at **80% watched**.
* **Captions:** upload hi/mr/gu subtitle tracks on YouTube itself. The player shows the learner's language with `cc_lang_pref`.
* **Fallback:** a video unit may instead point to an **uploaded MP4** (≤150 MB, compressed beforehand with the HandBrake guide). Use it where YouTube is blocked or a film must not be public.
* **Known trade-offs (accepted):**
  * Unlisted links can be shared. They are awareness content, so that's fine.
  * YouTube may show ads even on channels that aren't monetised.
  * Some school or office networks block YouTube. The MP4 fallback covers that.
  * The YouTube player sets YouTube's own cookies once played, even in privacy-enhanced mode. This is listed in the privacy notice.

### 8.3 Completion and hours

| Unit type | Complete when |
| --- | --- |
| video | 80% watched (YouTube API or HTML5 video) |
| reading | scrolled to the end |
| handout | opened |
| check | attempted once |
| practice_quiz | submitted once |

**Hours (adults only):**
* The browser sends a heartbeat every 30 seconds while the page is visible.
* It counts only if a server-side interaction (navigation, check or answer) happened in the last 5 minutes.
* Time is capped at 2× the unit's nominal minutes, and per day.
* Exports label it "engaged time (estimated)".

**Under-18s:** hours = the sum of nominal minutes of completed units.

### 8.4 Learn-mode check

`POST /learn/check` accepts **only `practice`-pool questions that belong to a published unit**. It is rate-limited and returns the score, feedback and the full answer.
Assessment and final questions are refused.

---

## 9. Assessments

### 9.1 Start

```text
POST /assess/<part>/start
 lock user row
 in_progress attempt exists? → resume it
 max_attempts set and attempts started ≥ max_attempts? → refuse ("no attempts left", D32)
 (final only) cooldown_hours > 0 and last final attempt too recent? → "Next attempt available at …"
 draw:
   part.selection = all / all_shuffled → its questions
   part.selection = draw → random draw_n from part.pool with ≥ min_per_tag per tag,
                           excluding questions in this learner's previous attempt where possible
   pretest / final → the learner's frozen exam set (D31): the pretest is its shared questions,
                     the final all of them; shuffled within the set
 for each question: freeze version + points; shuffle options/items; issue one-off tokens
 create Attempt + AttemptItems; audit
```

### 9.2 What the browser receives: `client_projection(format, version, option_map)`

Each format has its own projection, **tested over every fixture in every language** to prove that **no key, `[[!marker]]`, hotspot answer, canonical order
or score rule** is present.

| Format | The browser receives |
| --- | --- |
| mcq / cards | Options as tokens, shuffled |
| spot | The text **split into tappable segments, with no indication of which are risky**. The server keeps the segment→risky map. |
| hotspot | The image plus tappable regions as tokens. Which regions are risky stays on the server. |
| sort / match / order | Items shuffled server-side, as tokens |
| chat | Reply options per step as tokens. The next step is fetched only after the answer is saved. |

### 9.3 Answer, autosave, resume

* `POST /attempt/<id>/answer {position, response}` validates the owner, `in_progress`, the position and the tokens, then saves the answer. **No score is returned.**
* The engine retries when offline and shows "Saved ✓ / Saving… / Offline".
* Reopening an assessment on any device resumes the attempt.
* Attempts with no save for 7 days are **auto-submitted** with their saved answers.

### 9.4 Submit

```text
POST /attempt/<id>/submit   (idempotent)
 lock user row, then attempt row
 already submitted → show result
 score every AttemptItem with its frozen version: scorer[format](body, response) → Decimal 0..1 + gate_flag
 score % = 100 × Σ(score × points) / Σ points            (unanswered = 0)
 all_answered = every item has a response;  gate_breached = any gate_flag;  counted = not gate_breached
 status = submitted; audit
 (results are computed on read — nothing else to update)
 certificate: if user now eligible AND batch.auto_issue → issue(user)  (§12)
```

### 9.5 Result page (D13)

* The **score %** and, per question, **✓ or ✗ with the hint/explanation**. **The correct option is never shown.**
* If the attempt was gated: *"This attempt doesn't count: one of your choices would have put a citizen at risk. Read the hint and retake."*
* **Final:** the overall % plus per-module **bands**:
  * **strong** ≥ 75
  * **OK** 50–74.9
  * **needs work** < 50

  The bands are computed from the module's items in that final attempt. Exact per-module % is not shown, so a learner can't learn individual answers from small changes.

### 9.6 Scorers (13 formats + MCQ)

These are Python ports of the teammates' rules: MCQ right or wrong; partial credit for sort/match/order/pick/build/settings/dial; spot and hotspot with **wrong taps subtracting**
(floored at 0); chat = points / max.

The JS→Python parity check is run **once during the port** against frozen fixtures. After that, the Python tests are the reference.

---

## 10. Results (computed, never stored)

### 10.1 `compute_results(user_ids)` (`results/policy.py`)

```text
Constants (code, versioned by git SHA):
  PROGRAMME_WEIGHT_MODULES = 0.5, PROGRAMME_WEIGHT_FINAL = 0.5
  MODULE_PASS = 50.0, FINAL_PASS = 50.0, ROUNDING = ROUND_HALF_UP to 1 decimal
  GRADES: A+ ≥90, A ≥80, B ≥60, C ≥50, else "Not yet"

For each counted module m, for each counted part p of m:
   best_p      = max(score of counted attempts of p), or 0 if none
   answered_p  = exists a submitted attempt of p with all_answered (gated attempts DO count here)
module_m   = Σ(p.marks × best_p) / 100          (marks of counted parts sum to 100 — validated on save)
modules    = mean(module_m over counted modules)
final      = max(score of counted final attempts), or 0
overall    = 0.5 × modules + 0.5 × final

Every displayed number and every comparison uses round1(x) = Decimal(x).quantize(0.1, ROUND_HALF_UP)
```

### 10.2 States derived from results

| State | Condition |
| --- | --- |
| **Final unlocked** | answered_p for every counted part of every counted module **AND** the pre-test is submitted |
| **Eligible** | email verified **AND** status active (guardian done if under 18) **AND** every round1(module_m) ≥ 50 **AND** round1(final) ≥ 50 **AND** not already issued **AND** not revoked-and-blocked |
| **Blockers** | Plain-language list, e.g. *"Module 6 is at 44.0%. Your best MCQ is 52%, your best Interactive is 36%."* |

### 10.3 Worked example (becomes a test)

* **Module 4 MCQ attempts:** 8/15 = 53.33 and 11/15 = 73.33. Best = 73.333…
* **Module 4 interactive attempts:** 81.5 (**gated**, not counted) and 64.0. Best = 64.0.
* **Module 4** = (50 × 73.333… + 50 × 64.0) / 100 = 68.666…, shown as **68.7** ✓ ≥ 50.
* **Nine modules** = 72.0, 55.0, 64.2, 68.7, 51.0, 66.0, 70.0, 58.0, 62.0. Mean = 62.985… (Module 4 enters at full precision, 68.666…), shown as 63.0.
* **Final best** = 61.0.
* **Overall** = 0.5 × 62.985… + 0.5 × 61.0 = 61.992…, shown as **62.0**, **Grade B**.
* **Boundary tests:** 49.94 → 49.9 fail; 49.95 → 50.0 pass; 79.95 → 80.0 → A.

### 10.4 Changing marks or counted parts

* A new part or module starts **not counted**.
* Making it counted, or changing a mark split, shows an **impact preview** computed by the same `compute_results` ("23 learners: 4 lose eligibility, 2 gain it").
  It needs a confirmation and is audited.
* Issued certificates are snapshots and never change.
* A learner who loses eligibility before issue just shows a new blocker.

---

## 11. Final exam and pre-test

| | Final | Pre-test |
| --- | --- | --- |
| When | Unlocked per §10.2 | Prompted once after first login. It can be postponed, but the final stays locked until it is done. |
| Questions | All 50 questions of the batch's released **exam set** (D31), matching the `per_module` blueprint 6/6/5/6/6/6/5/5/5, including its 18 shared questions. | The set's shared questions only (2 per module = 18) |
| Pool rules | A question shown in any non-final attempt **can't be moved** into the final pool (enforced on save). The blueprint must be updated when the counted modules change. | — |
| Timer | Shows "about 60 min", not enforced | Shows a count-up |
| Exam set | An admin assigns one released set per batch (audited). The learner's set and question versions freeze when their first programme exam starts. No set, or an unreleased one: "not available yet". | Same set |
| Feedback | Overall % + bands (§9.5) | Score only. **Shared questions are never given feedback anywhere.** |
| Attempts | Unlimited by default; optional `max_attempts` (D32); cooldown setting (0) | One attempt (resumable); takes no limit |

**Knowledge gain (CSR ≥25%)** = score on the shared questions in the learner's **first** final attempt − score on the same questions in the pre-test (both from the learner's frozen set). It is reported per batch.

---

## 12. Certificates

```text
issue(user)   ← called by auto-issue (after the learner's own submit) or by a mentor's / admin's approval
  lock user row
  already issued → stop; re-run compute_results; not eligible → stop
  serial         = nextval('certificate_serial')    (global; never reset per year; a failed issue skips it, never reuses it)
  certificate_no = <CERTIFICATE_PREFIX>-<issue year>-<batch.centre_code>-<6-digit serial>   e.g. CCFR-2026-SAKEC-000001 (D28, D36)
  verify_code    = 10 random chars (Crockford base32)
  snapshot = {certificate_name, qualification, batch, centre_code, completed_on, issued_on, grade, overall/modules/final %,
              per-module %, hours, the policy constants, NSQF line, signatories (and whether each signature image was in place), design}
  PDF = WeasyPrint(templates/certificates/pdf/certificate.html, snapshot) — English only; the url_fetcher answers only
        `ccfr-asset:<name>` for the bundled fonts and logos, the signature images in private storage and the QR code
        (segno, made in memory) → https://<domain>/verify/<verify_code>/; anything else is refused
  write the PDF to CERTIFICATE_PRIVATE_ROOT/certificates/<year>/<number>.pdf (never overwritten), sha256; Certificate(issued); audit
revoke(cert, reason, allow_reissue=False)  ← admin only; verify page then shows "Revoked"
erase_holder(cert)                          ← admin only (holder's erasure request): blank the name, delete the PDF, keep the rest
```

* **What is printed (D36):** CERTIFICATE OF COMPLETION, the qualification "Community Cyber First Responder (CCFR)", the certificate name, the agreed
  sentence ending "and is awarded Grade X", a line with Batch, Completed on and Certificate No., the NSQF line, three signature blocks
  (`CERTIFICATE_SIGNATORIES`, left to right) and the QR code with "Verify at <domain>/verify/<code>". **The grade only:** no percentages, no hours.
  "Completed on" is the date the result was achieved: the latest of the submissions that give the learner's best scores (normally the passing final).
* **Signature images** are never in git (D22). They are files in `CERTIFICATE_PRIVATE_ROOT/signatures/` on the server (inside the media volume, so the
  nightly media backup covers them); a missing one prints the name and designation over a blank line.
* **Name (D37):** English letters only, checked at sign-up and on a mentor's or admin's name change (`accounts.rules.certificate_name_ok`). A stored name that breaks the rule is held back from issuing (`NameNotPrintable`, before a serial is taken); the mentor's list says "Correct the name first" with a link to the learner page.
* **Design:** a placeholder until the final design and the CCFR emblem exist. The template is self-contained, so the final design is a template-only PR.
  While a signature image is missing or `CERTIFICATE_DESIGN_FINAL` is off, mentors (batch page) and admins (certificate admin, batch action) see a
  warning that certificates issued now are final. Approving still works.
* **Learner:** `/certificate/` shows not yet / awaiting approval / issued / revoked / details removed. Download is served by Django to the owner only
  (`Cache-Control: private, no-store`; a file whose sha256 no longer matches is not served). There is no email.
* **Mentor:** an "Awaiting approval" list (eligible learners holding no certificate, whatever the switch says) with **Approve** per learner and
  **Approve all** (at most `CERTIFICATE_APPROVE_PER_REQUEST` per click), and an "Issued this week" list.
* **Switching auto-issue on** for a batch does **not** bulk-issue the people already waiting. The mentor clicks "Approve all" once, deliberately.
* **The public verify page** `/verify/<code>/` (rate-limited per client IP, `CERTIFICATE_VERIFY_RATE`; `noindex`) shows name, qualification, grade,
  issue date and status. A revoked certificate shows "Revoked" without the name. There is **no lookup by certificate number**, so no one can walk the
  list and harvest names; `/verify/` only takes a typed code. If the holder has requested erasure, it says *"Issued; holder details removed at the holder's request."*
* **NSQF wording:** *"NSQF level and credits shown after approval by the competent authority"* until an admin turns `nsqf_approved` on (with the level
  and credits), which affects new issues only.

---

## 13. Authoring (no tech team needed)

### 13.1 Content

| Action | How |
| --- | --- |
| Add text | Upload **.docx** → mammoth → blocks (sanitised) → **draft** UnitVersion. Or type blocks in the editor (django-jsonform). |
| Add a PDF | Attached as a downloadable handout. Web text from a PDF = paste it into a reading unit. |
| Add a film | Paste the **YouTube link** (validated as a YouTube video ID). Optional MP4 fallback ≤150 MB. |
| Add images | PNG/JPG ≤5 MB, resized, metadata stripped |
| Publish | Admin, or a mentor with "Content publisher". The previous version is kept, and restore is one click. Publishing an English change marks that block's translations stale. |

* **Block types:** heading, paragraph (structured inline spans: bold, italic, link; http/https only), list, table, image, video, remember, case, stop-save-report, ask-yourself, check (practice question), attachment.
* **Upload safety:** size caps, real file-type sniffing, defusedxml, Pillow pixel limits, a zip-size check, no HTML ever stored, parsing inside the request with a time limit.

### 13.2 Questions and assessment parts

* **MCQ:** a form, or an **XLSX template** (django-import-export). Columns: id, question, options A–F, correct, hint, PC, type, pool, points. A dry run shows row errors before anything is saved.
* **Interactive:** edited as JSON in admin with the format's **schema-driven form** (django-jsonform + pydantic), plus a "preview as learner" button. Bulk import from JSON files.
* **Required to publish a question:** a valid schema, exactly one correct answer (MCQ), a hint, tags, a pool, the scoring rule, and gate options flagged with a reason.
* **`validate_part()`** blocks publishing unless:
  * the counted marks in the module total 100
  * the draw pool has ≥ 2× draw_n
  * every tag has ≥ min_per_tag questions
  * there are no duplicates
* **New formats** (a 14th type) are developer work.

---

## 14. Multilingual

```text
language = user.preferred_language → ?lang switch → Accept-Language → en
UI strings      → gettext (.po), edited in Rosetta
content strings → t(key, lang):  key grammar  q:<question>:<field.path>  ·  blk:<unit>:<block>:<field>
                  reviewed + source_hash matches → shown
                  draft → shown in learning units with a "draft translation" tag; assessments fall back to English until a reviewer approves that wording (D24)
                  stale/missing → English
```

* **XLSX round trip per module** from admin. The import rejects:
  * unknown keys
  * mismatched `[[!markers]]` or `{placeholders}`
  * `<`/`>` not in the source
  * blank-over-existing values
* "Reviewed" is set in the app by a per-language Reviewer who **didn't upload that line**.
* Answers are stored as tokens and IDs, so switching language mid-attempt is safe.
* Per-language item statistics flag translations that make a question easier or harder.
* **Crossword:** available for practice and for Module 8's 50-mark graded Part B (D26). The six original Module 8 challenges use the existing server-side word scoring and share the part's marks. No crossword goes into the final pool.
* **Fonts:** Baloo 2 + Hind (Latin and Devanagari), Baloo Bhai 2 + Hind Vadodara (Gujarati), self-hosted from Google Fonts (OFL, licences next to the files). Added in Stage 1.5.
* **Certificate:** English only.
* **Implementation (Stage 8):** see §30, including the extra key prefixes `mod:`, `part:` and `note:`.

---

## 15. Dashboards

| Learner — My progress | Mentor | Admin report page |
| --- | --- | --- |
| Overall ring, grade if eligible | Batches: roster with module %, final %, overall, status | Totals per batch: registered, active, eligible, issued |
| Module cards: % per part, module %, pass ✓/✗, retake | Heatmap learners × modules (red < 50) | **Knowledge gain** vs 25% |
| Final: locked (with the reason) / bands / best % | Stuck learners (inactive 7+ days, or below 50 after 3 attempts) | Item statistics (% correct, per language) |
| Blockers in plain words | Registration controls, seats, new sign-ups, move | Translation coverage |
| Weakest topics (PC level) | Awaiting approval / issued this week, auto-issue switch | Email budget today |
| Hours | CSV export (audited, formula-safe) | Everything else via Django admin |
| Certificate card | One-time reset link, name change | |

---

## 16. Security and privacy summary

| Area | Controls |
| --- | --- |
| Integrity | Server-side scoring, client projections without keys, frozen versions, one open attempt, idempotent submit, user-level locks, one issued certificate per user, no answers revealed, bands in the final, the final-pool firewall |
| Web | CSP from Django on every page (self + youtube-nocookie frames; the YouTube player script only on a lesson with a YouTube film; a separate policy for /admin/ and /rosetta/), Caddy adds the same policy only to the files it serves itself; HSTS (prod 1 year + subdomains, staging 300 s), frame-deny, CSRF, auto-escaping, nh3 sanitising, WeasyPrint url_fetcher allowlist, HTMX eval off (§32) |
| Accounts | allauth, Argon2, staff MFA, rate limits per user, per batch or per real client IP with the wait shown (§32), no account enumeration, mentor-reset safeguards |
| Server | SSH keys only, ufw 22/80/443, fail2ban, unattended upgrades, non-root containers, separate secrets per environment, two DB roles |
| Media | `/learn/media/<id>/` needs sign-in (D34); Django checks the file belongs to a published unit, then answers with `X-Accel-Redirect` and Caddy sends it from the read-only media volume with range requests (D35). `/media` is never served directly. Certificates are served only by Django to the owner; issued PDFs and signature images live in `media/private/`, which no view ever names. |
| DPDP | Minimum fields; pseudonymous audit; erasable Profile; guardian consent and no tracking for minors; processors listed in the notice (Brevo, Sentry, YouTube, the backup provider and region); 72-hour incident runbook; a named grievance officer (CyberPeace); retention of 3 years after programme end |

---

## 17. Deployment and operations

| Topic | Plan |
| --- | --- |
| Pipeline | git push → GitHub Actions (ruff, pytest with Postgres, Playwright) → `deploy/deploy.sh staging`, run **by a person** on the server (D29), → manual check → same script for **prod** (DB dump taken first) |
| Deploy script | `git pull → docker compose build → migrate (as csfr_owner) → collectstatic → restart`. **No content loading. Never touches Caddy**: `deploy.sh edge` installs the edge config (§32). |
| Stacks | Staging and prod are two separate instances of `deploy/compose.yml` (own project name, `.env`, DB, volumes). One shared Caddy (`deploy/compose.edge.yml`, run from `/srv/csfr/edge/`) owns ports 80/443 and routes by host name over the `csfr-edge` network. See `docs/server-setup.md` and `docs/runbook.md`. |
| One-time import | `importers/` loads the existing material once. It refuses to run if any content version was edited in the app. |
| Backups | Hourly `pg_dump` + nightly media to off-site storage with **write-only credentials and object lock**. Encrypted to a public key; the **private key is held offline by two named people**. Kept for 48 hours (hourly), 14 days (daily) and 8 weeks (weekly). |
| Restore drill | In a throwaway stack (never staging), before launch and every term; timed steps in `docs/runbook.md` §3 |
| Monitoring | An uptime pinger (5 min) on `/healthz/`, Sentry (scrubbed), heartbeat pings from the `tasks` loop and both backups, a disk alert at 80%, the email budget alert (`docs/runbook.md` §9) |
| Rollback | Redeploy the previous git tag. Migrations stay backward-compatible for one release. |
| Load test | 60 simulated learners taking the final together before launch |

---

## 18. Critical journeys (automated tests)

| # | Given | When | Then |
| --- | --- | --- | --- |
| 1 | No batch is accepting | Someone opens /register, or posts the form directly | No form is shown / "not accepting registrations" |
| 2 | B03 is open | An adult registers and verifies | Lands on the pre-test prompt. The mentor sees them in B03. |
| 3 | B03 is open | A 17-year-old registers | Pending until the guardian confirms. No heartbeat is recorded. |
| 4 | B03 closes while the form is open | The person submits | Refused, with the input kept |
| 5 | Mid-MCQ, the connection drops | They resume on another phone | Same attempt, answers intact |
| 6 | Double tap on submit | — | One result |
| 7 | 17 of 18 parts are answered, and one was submitted with blanks | They open the final | Locked, with the reason |
| 8 | An interactive attempt has a gate choice | It is submitted | Scored, not counted, with the hint |
| 9 | A result page | Viewed | ✓/✗ + hints, no correct options |
| 10 | Any assessment page | Inspected in DevTools | No keys or markers (projection test) |
| 11 | A final attempt | Submitted | Overall % + bands only |
| 12 | Eligible, auto-issue on | The last submit | Certificate issued; the verify page shows Valid + grade |
| 13 | Two tabs submit together | — | One certificate (constraint) |
| 14 | Mentor of B01 | Requests B02 data or a final-pool question | 403, logged |
| 15 | Admin makes a new part counted | Preview → confirm | Results change, issued certificates don't |
| 16 | A Marathi learner | Switches language mid-final | Same tokens, same score |
| 17 | Server lost | Restore from last night's backup | Back within 2 hours, losing ≤1 hour of data |

---

## 19. Open items (none block slice 0–1)

**Settled 2026-11-07:**
* Repo: `github.com/storm756/CertificationPlatform`
* Domain: **cyberfirstresponse.io**. The site will be `cyberfirstresponse.io`, staging `staging.cyberfirstresponse.io`, and email from `noreply@cyberfirstresponse.io` via Brevo. The domain currently points to 2.57.91.91, which is probably Hostinger parking, so its A record must be moved to the VPS IP.
* YouTube channel: `UCn0dfdFupBEI0gdADurMTEA`

**Answer keys must never be in git.** Both GitHub repos are **public**, and the old one already exposes all 405 MCQ keys and the interactive keys.
Rules that follow:
* the existing 405 are treated as **known**: they go into the module-quiz and practice pools only;
* **the final pool is written fresh**;
* question data for the importers lives in the team's private drive, never in the repo (`.gitignore` has `content-data/`).

1. ~~Domain name~~ (done)
2. **CyberPeace legal:** the guardian-consent method (§7.3), a grievance officer name, and the privacy notice text.
3. **Teammates' content work:**
   * Module 8's graded Part B uses its six existing crosswords (D26).
   * interactive variants
   * a larger final pool (target ~3× by batch 2)
   * hints for all 405 MCQs (most already have explanations)
   * final/anchor tagging
4. **A YouTube channel** owned by the programme.

---

## 20. Build order

See `docs/build-stages.md` (stages 0–10).

---

## 21. Stage 1 implementation notes (accounts, batches, registration)

Where the build made a choice the design left open. Each is a one-line change if the team decides otherwise.

* **Public allauth sign-up is closed** (`BudgetedAccountAdapter.is_open_for_signup`), and `/accounts/signup/` redirects to `/register`. This is what makes D9 true for every entry point.
* `is_accepting` also requires `status == active` (an archived batch never accepts, even if left switched on).
* **2FA keys on role, not `is_staff`:** `accounts.rules.requires_mfa` is true for staff, mentors and admins. Mentors never need `is_staff`. The 12-hour session applies to them too.
* **Email budget:** pools are registration 150 (verification + the "you already have an account" note), reset + guardian 100, reserve 50 (admin alerts). The admin alert fires once a day when the **total sent** reaches 150 (`EMAIL_ALERT_AT`). Every allauth email passes the same gate via the account adapter, so the per-address limit also covers password reset. If the registration pool is empty, `/register` refuses before creating anything.
* **Guardian link** is valid for 14 days (`GUARDIAN_LINK_DAYS`); the learner's waiting page can send a fresh link (5 per hour), which kills the old one. Only a hash of the token is stored.
* **Mentor reset link**: hash only stored, 1 hour, single use. Using it sets `Profile.mentor_reset_at`, ends all the learner's sessions, shows a dismissible banner, and blocks `POST /accounts/email/` for 7 days.
* **Seats** count verified enrolments plus unverified ones younger than 48 h; moves by a mentor do not check the target's seat limit.
* **Batch codes** are generated as `B02`, `B03`, ... (the next free number). The catch-all pool is created by migration with code `OPEN`, closed.
* **Daily jobs (D27):** the `tasks` service (web image, non-root, connects as `csfr_app`, never `csfr_owner`) runs `manage.py run_periodic`. It wakes every 10 minutes and runs each job in `apps/core/periodic.py::JOBS` that is due. A job is due once today's scheduled time (`PERIODIC_RUN_AT`, 03:00 Asia/Kolkata, after the 02:00 backup) has passed and its last success (`core.PeriodicRun`) was before that time. A run missed during a restart happens once on the next wake-up, with no pile-up. A failing job is logged and retried at the next wake-up, and never stops the other jobs or the loop. `deploy.sh` restarts `tasks` together with `web`. In dev, `compose.dev.yml` creates the real `csfr_app` role (same `init-roles.sh`, plus `dev-grants.sh`) so `tasks` runs as it there too; an existing dev database needs `down -v` once.
* **`purge_unverified`** (daily job, also a management command; logic in `apps/accounts/purge.py`) deletes learner accounts (1) whose email is still unverified 7 days after sign-up, and (2) that are still `pending_guardian` 7 days after their guardian link expired (14 + 7 = 21 days after it was sent). It sends no email. It records one `AuditEvent` `system.purge_unverified` with counts only, and logs one stdout line per run. Seats are already freed after 48 hours by `is_accepting`; this clears the personal data (DPDP data minimisation).
* **Move learner** (`mentors.views.learner_move`): no batch chosen returns 400 with the form and the translatable "Pick a batch."; any other value that is not one of the mentor's own active batches (unknown, someone else's, or not a number) returns the same 403 and an `access.denied` audit event, so the response never reveals which.
* **Audit**: `apps.audit.AuditEvent` + `audit()`; the migration revokes UPDATE/DELETE/TRUNCATE from `csfr_app` (skipped where that role doesn't exist, e.g. dev and CI).
* `accounts.rules.may_track_time(user, today)` is the single question the Stage 4 heartbeat must ask (false under 18).
* After sign-in everyone goes through `/start/`: pending learners to the waiting page, mentors to their batches, learners to a welcome page whose pre-test prompt is a placeholder until Stage 5.

---

## 22. Stage 1.5 implementation notes (UI shell and components)

**Look (D20, D21).** The approved prototype is the visual target. `static/css/tokens.css` holds its colours, type, spacing, radii and shadows; `base.css` and `app.css` are the prototype's CSS with the night-mode rules and the theme toggle removed; `stage.css` is the Learn → Practise → Assess → Certify strip; `fonts.css` declares the self-hosted fonts with `unicode-range` and `font-display: swap`. Gujarati pages switch the font variables to Baloo Bhai 2 (headings) and Hind Vadodara (text) through `:root:lang(gu)`.

**Shell.** `templates/base.html` has the skip link, the cream header (SAKEC and CyberPeace logos, the programme-emblem slot, nav for guest, learner and mentor, language select, user chip, sign out), a footer, toasts (Django messages) and one shared confirm dialog. The header and footer are in `templates/components/`. The programme name always comes from `settings.PROGRAMME_NAME` / `PROGRAMME_SHORT` through the `apps.core.context.programme` context processor (D23, D30). **The emblem slot shows "CCFR" in text** until the emblem artwork exists (`.brand-emblem`). The sign-in page omits the footer, like the prototype's.

**Components** (`templates/components/`, all shown in `/styleguide`): `field` (label, hint, error, password reveal; widget classes and `aria-*` come from the `as_input` filter), `form_errors`, `button`, `badge`, `alert`, `empty_state`, `progress_bar`, `progress_ring`, `module_card`, `stage_strip`, `question_palette`, `save_pill`, `timer`. Icons come from one SVG sprite (`static/img/icons.svg`) through the `{% icon "name" %}` tag. Allauth screens (reset, email, two-factor) are restyled by overriding its element templates in `templates/allauth/elements/`.

**No inline code.** Pages contain no inline `<script>`, `<style>`, `style=""` or `on…=` handlers, so the CSP set by Caddy is unchanged. Progress widths use `data-v`, which `ccfr-shell.js` copies into a CSS custom property. A test scans the rendered pages for this.

**Language wiring.** `POST /i18n/setlang/` is `apps.core.views.set_language`: Django's `set_language` (a cookie for guests) plus `Profile.preferred_language` for signed-in users. `ProfileLanguageMiddleware` applies a signed-in learner's saved language on a device that has no cookie yet. The real translations arrive in Stage 8; until then the language only changes `<html lang>` and the fonts. **Django ships no Gujarati catalogue, and without one `LocaleMiddleware` ignores `gu`.** The project therefore keeps its own `locale/gu` (header only for now) and sets `LOCALE_PATHS`; a test checks that all four languages can be activated.

**Review fixes applied.** The question map shows "marked for review" as a dashed border with a corner flag, and "answered" as a tinted square, so they differ in shape as well as colour. "Answer every question" is a block of running text, never a flex row. Small contrast fixes (the divider text, row-header links, the module-card kicker, the map heading) came from the axe check.

**Sign in** keeps allauth's real login view, form, error messages, CSRF protection and redirects. The prototype's demo "Preview as" box and simulated sign-in were not carried over. "Remember me" stays unchecked by default (a shared phone in a community centre should not stay signed in); the prototype ticked it.

**Checks.** `tools/screenshots.mjs` takes 390px and 1366px screenshots, tests for sideways scroll at 360px and 1366px, and runs `@axe-core/playwright` on the same pages (`cd tools && npm install`, then see the header of the script). It uses Microsoft Edge when installed, so no browser download is needed on Windows.

---

## 23. Stage 2 implementation notes (questions and MCQ assessments)

**Apps.** `apps/content` (a minimal `Module`, seeded 1–10), `apps/questions` (Question, QuestionVersion, schema, projection, XLSX import, legacy importer) and `apps/assessments` (AssessmentPart, Attempt, AttemptItem, services, views). `apps/results/policy.py` holds `round1()`, `percent()` and `PASS_MARK`.

**Questions.** `QuestionVersion` rows are immutable: the model refuses `save()` on an existing row and `delete()`, and a Postgres trigger refuses `UPDATE` and `DELETE`. A change makes a new version (`services.add_version`; an identical body adds nothing). The body is validated by a pydantic schema per format (`MCQBody`: stem, 2–6 options, exactly one correct, hint, optional gate options with reasons; plain text only, templates escape it). A draft may lack a hint; `services.publish()` needs a hint, a PC tag and a pool.

**Import.** The XLSX columns are `id, question, option_a … option_f, correct, hint, pc, type, pool, points` plus optional `gate`, `gate_reason`, `status`. The id is `M<module>-<code>`. It runs through django-import-export in the admin (Questions → Import) with a dry run that lists every row's problems per column and saves nothing; a real import is all-or-nothing (`rollback_on_validation_errors`). The legacy importer (`import_legacy_mcq`) is create-only, loads questions as **drafts** (the legacy bank has no hints), assigns pools 30 quiz / 15 practice per module with at least 5 per PC tag, never `final`, refuses to run after any edit, and prints counts and ids only, never question text.

**Attempts.** `AssessmentPart` has `selection` (`all`, `all_shuffled`, `draw`), `draw_n`, `min_per_tag`, `pool` and `is_published`. `Attempt` has the unique `(user, part, number)`, a **partial unique index** allowing one `in_progress` attempt per learner and part, and a check that it belongs to a part or a programme assessment. `AttemptItem` freezes the question version and points, and holds the `option_map`: a shuffled order plus random one-off tokens mapped to internal option ids. Tokens are never derived from the source position. The map, the key and the hint never reach the browser.

**Services (`assessments/services.py`).** `start()` locks the learner row, resumes an attempt in progress, otherwise draws (min-per-tag first, preferring questions not in the previous attempt), shuffles and creates items. Two simultaneous starts give one attempt. `save_answer()` validates the owner, state, position and token and returns no score. `submit()` locks user then attempt, scores each item from its frozen version on the server, and is idempotent (a double tap gives one result and one audit event). `auto_submit_stale()` submits attempts with no save for `STALE_ATTEMPT_DAYS` (7) using their saved answers; it runs daily as the `auto_submit_stale_attempts` job in the `run_periodic` loop and one failure never stops the rest.

**What the browser gets.** `questions/projections.py::client_projection()` builds the question from an allow-list (stem, options as tokens). Views pass only that plus plain flags to templates. The attempt page is one question at a time: htmx loads each question panel, saves each answer (`hx-trigger="change"`) and refreshes the question map out of band; without JavaScript the same links and a Save button work. `attempt.js` shows Saved / Saving / Offline, retries with a growing delay until the answer is saved, and runs the count-up timer (a guide, never enforced). The result page shows the score, ✓/✗ and the hint for each question and, for a gated attempt, the "doesn't count" message; it never shows the correct option.

**Tests.** Tests use invented questions only (`tests/conftest.py`). They prove, among others: resume (journey 5), double submit (6), the result page (9), two and five simultaneous starts giving one attempt, two simultaneous submits scoring once, that no attempt page, question partial, save response, review page or result page contains a key, hint (before submit), gate reason or internal option id, and that the correct option's markup is identical to the others.

## 24. Stage 3 implementation notes (interactive engine)

**Formats.** `apps/questions/bodies.py` holds a pydantic body per format (mc, cards, spot, hotspot, sort, match, order, pick, build, settings, dial, chat, crossword); `apps/questions/formats.py` holds one class per format (MCQ included) with `make_map`, `project`, `clean_response`, `score` and `complete`. `schemas.publish_errors` also checks gate messages and the hotspot image. Only MCQs require a PC tag. D26 also allows crosswords in Module 8's graded part.

**Tokens and projections.** `AttemptItem.option_map` for interactive formats is `{"v":2,"refs":{token:[table,index]},"lists":{table:[tokens in display order]}}`; tokens are `secrets.token_urlsafe(9)`. MCQ keeps `{order, tokens}`. `project()` is an allow-list: text and tokens only, never a key, risky flag, hint, `why`, gate or canonical order, and the echoed response has its `flag` key removed. Tests prove this for every format, on pages, partials, the JSON endpoint and the save response (journey 10).

**Answering.** The question panel is the Stage 2 htmx form with a hidden `response` input holding JSON (max 20000 characters). The TypeScript engine writes it and fires `change` after a 120 ms debounce; the server validates with `formats.clean_response` (unknown tokens raise `InvalidAnswer`). `AttemptItem.answered` uses `formats.complete`. Chat fetches its next step from `q/<pos>/data/` (JSON, no-store) only after the save succeeded.

**Scoring.** `assessments/scoring.py::score_item` delegates to the format scorers. Scores are `Decimal` (`AttemptItem.score` is numeric(30,20)), rounded only by `round1()`. Partial credit shows as "Partly right". Gates come from something the learner did: a blank answer never gates. `scoring.score_item` gives an untouched item (no response, only the review flag, or only empty values without "finished") zero and no gate at submission, manual or automatic; the format scorers alone keep the legacy credit for leaving things alone so that parity holds. The result page shows status and hint only and never repeats an option's text (a right pick would be the correct option). `ProgrammeAssessmentKind.MOCK` was added.

**Parity.** `tools/legacy_parity.mjs` runs the real legacy `engine.js` in jsdom. `tests/fixtures/legacy_parity_expected.json` freezes 128 cases (25 with gates) from invented questions; `tests/test_scorer_parity.py` asserts the Python matches. `manage.py check_legacy_parity` does the same on the private bank and prints counts only.

**Hotspots.** `QuestionImage` stores an uploaded raster (Pillow re-encodes it, strips metadata, 5 MB and 25 MP caps, SVG rejected). It is served only through `/attempt/<pk>/q/<pos>/image/` to the attempt's owner. Regions are numbers (rect, circle, poly, 0-100); the engine draws them as SVG shapes, never from content markup.

**Importer.** `import_legacy_interactive` is create-only and refuses after edits. It prints counts and ids only and creates drafts (legacy challenges have no hint). See `docs/STATUS.md` for the content calls.

**Renderer.** `engine/src` (strict TypeScript, `textContent` only, no `innerHTML`) is bundled by `tools/build_engine.mjs` (type-check, then esbuild, iife, es2019) into the committed `static/js/engine.js`; styles are in `static/css/engine.css`. Colour triage is four large labelled buttons in fixed colour order with a "✓ Your choice" text cue. It works under the production CSP (no inline script or style).

**Review fixes (accounts, language, auto-submit).** `purge.py` decides each group *after* locking the `EmailAddress` and `GuardianConsent` rows of the candidates (`_stale_ids`), so a verification in flight wins. `guardian.resend()` replaces the stored link hash only after the email is sent (`send_request(..., new_hash=)`); a budget refusal or mail error keeps the old link and returns False. `ProfileLanguageMiddleware` applies `Profile.preferred_language` on every signed-in request (it beats the cookie) except on the `set_language` request itself. `services.submit(..., stale_before=)` makes the auto-submit job recheck `last_saved_at` under the attempt lock.

**Saving answers in the browser.** `attempt.js` keeps an outbox (one entry per question number, holding the form's latest serialised answer). A change is copied into it at once, sent after 150 ms or immediately when the learner navigates (htmx `beforeRequest`, `pagehide`, a plain link), and retried for its own question (2 s, doubling to 30 s) if the network or server fails. The pill reads "Saved" only when the outbox is empty and nothing was refused; a 4xx shows "Not saved". A plain link (Review and submit) waits for the outbox to drain and stays on the quiz if an answer was refused or still cannot be sent, showing the affected question; leaving the page with answers still waiting triggers the browser's leave-page prompt. The server response (pill and question map) is applied only while that question is on screen. The engine announces nothing itself: it writes the hidden field, fires `change`, and waits for `ccfr:saved` for its question (chat uses this before fetching its next step). `guardian.confirm()` rechecks the stored link and its expiry under the row lock.

## 25. Stage 4 implementation notes (learning content)

**Models (`apps/content`).** `Module` gains `title`, `tagline`, hours and an `overview` JSON (validated by `blocks.ModuleOverview`). `Unit` (slug unique per module; type video, reading, handout, check, practice_quiz), `UnitVersion` (blocks JSON, draft/published/superseded, source legacy/docx/editor/restore; a partial unique index allows one published version per unit; the title and blocks are immutable in the model **and** by a Postgres trigger, and rows are never deleted), `MediaAsset`, `UnitProgress` (unique per user and unit), `TimeLog` (unique per user, unit, day), `LearnCheck`.

**Blocks (`blocks.py`).** Plain text only. Types: heading, paragraph (spans: bold, italic, http/https link), list, pairs, table (`being_fixed`), cards, signs, urgency, callout, stop_save_report, ask_yourself, image, video (YouTube ID validated as 11 characters, optional MP4 and poster assets, transcript), attachment, reveal, flipcards, mythfact, check, case, remember. Templates (`templates/learn/`) escape everything.

**Interactions.** `reveal` and `mythfact` blocks keep `answer`, `is_fact` and `why` out of the page: `_prepare` drops them and `POST /learn/m<N>/<unit>/block/<i>/` returns them when the learner acts. `check` blocks use `learncheck.py`: `POST /learn/check/` accepts only a live practice-pool MCQ used by a published unit's check block, with per-view random option tokens held in the session, rate-limited, and returns the score and the full answer. Quiz and final questions are refused.

**Completion and hours (`services.py`).** reading: scrolled to the end (or the button); video: 80% (HTML5 or the YouTube IFrame API); handout: opened; check: attempted; practice quiz: submitted. `complete()` refuses a way that does not fit the type. The heartbeat counts 30 s only for adults (`may_track_time`), only if a server interaction happened in the last 5 minutes, at most once per 25 s per unit, capped at twice the unit's nominal minutes and per day. Under-18s write no `TimeLog` rows; their hours are the nominal minutes of completed units (`hours_for`).

**Authoring.** `publish()` and `restore()` need an admin or the `content.publish_unit` permission; restore makes a new version with the old text and publishes it. `docx.py` reads a Word file (size, zip and entity checks, mammoth, nh3) into blocks for a draft; `media.py` stores PDFs (`%PDF-`), MP4s (`ftyp`, 150 MB) and images (Pillow re-encode, EXIF stripped, 5 MB, pixel cap). `/learn/media/<id>/` serves only assets used by a published unit, with `nosniff`. Since D34 it needs sign-in and sends `Cache-Control: private`; behind Caddy (`MEDIA_ACCEL_REDIRECT`) it hands the file to Caddy with `X-Accel-Redirect` (D35). The handout PDFs that `publish_ccfr_course` stores live in `apps/content/data/handouts/`, outside the static files.

**Importer (`legacy.py`).** Create-only; refuses once any unit was edited. A small reader parses `modules.php`; booklet blocks map to the block types; tables that look jumbled are flagged.

## 26. Stage 5 implementation notes (results, final exam, dashboard)

**`results/policy.py`.** Constants, `round1`, `grade`, `band`, and `compute_results(user_ids)`, which returns a `Result` per user from their attempts (module % per counted part, best counted attempt, `answered` from any submitted attempt with every question answered, the final's best, the pre-test flag, verified email, status). `final_unlocked`, `eligible` and the plain-language `blockers` are derived from it, so the dashboard, mentor pages and the impact preview cannot disagree. `results/insights.py` has `final_bands`, `shared_percent`, `knowledge_gain` (the shared questions' score in the first final attempt minus the pre-test's) and `weakest_pcs`.

**`assessments/programme.py`.** `start_programme(user, kind)` locks the learner, resumes an open attempt, and otherwise: the pre-test is once; the final checks `final_locked_reasons` (pre-test done, every counted part answered) and the cooldown. Both then use `examsets.freeze(user)` (the learner's `LearnerExamSet`: set, question versions and shared ids, created at the first programme exam) and shuffle within it.

**`assessments/examsets.py` (D31).** `ExamSet` (code, draft/released), `ExamSetItem` (question, `in_pretest`), `Batch.exam_set`. `release_errors` lists every blocker (blueprint counts, 2 pre-test questions per module, final pool, `mc`/`mcq` only, 1 mark, publish-clean, never shown in a module or practice attempt, no text copy of a module or practice question); `release` and `assign` are admin-only and audited (`exam_set.released`, `batch.exam_set_changed`); `freeze` audits `exam_set.frozen`. The Batch admin lets only admins pick a set, and only released ones. Sets come from the private workbook via `manage.py import_final_sets --source <xlsx>` (a read-only preview that prints IDs and counts and what `--apply` would change; `--apply` reconciles each draft set atomically: new rows become draft `mc` questions, changed rows get a new version, held rows are `reserve`, removed or rejected rows are `rejected`, never deleted).

**Fixed papers.** `release` stores the approved `version`, `approved_points`, `approved_format` and `approved_module` on each `ExamSetItem` and freezes learners to those versions. Model guards (`ExamSetLocked`, `QuestionLocked`) and Postgres triggers (migration `0006_released_sets_fixed`) refuse changes to released membership, the released set, the marks / format / module / pool / status of its questions, and new versions of them; corrections are a new draft set. Import and release take the same `select_for_update` lock on the set row. `Question.reuse_reasons()` is the single reuse rule (module/practice attempts, lesson checks and lesson check blocks); `examsets.blueprint_problems()` and `release_errors()` back both Check sets and Release. Items freeze their version, points and option tokens exactly like Stage 2 attempts; `submit()`, autosave and auto-submit are shared.

**Pages.** `/exam/<final|pretest>/` and `/exam/<kind>/start/`; the attempt pages work for programme attempts (`Attempt.title`). `/start/` is the learner's My progress dashboard (`results/views.py`, `templates/progress/dashboard.html`): journey strip, what's left (to do first, finished collapsed), module cards, final state with bands, blockers, weakest PCs, hours, certificate placeholder.

## 27. Attempt limit and lesson sign-in (D32–D35)

**Attempt limit (D32).** `AssessmentPart.max_attempts` and `ProgrammeAssessment.max_attempts` (blank = unlimited; a database check allows a value only on the final, never on the pre-test or mock, and never 0). `services.check_attempt_limit()` runs inside `start()` and `start_programme()` after the learner's row lock and after an open attempt has been resumed, so parallel starts at the limit create at most one attempt and an attempt in progress is never cut off. Every started attempt counts as used (`services.attempt_allowance()`). The part intro, the final intro and the module page show "N of M attempts used"; at the limit Start and "Try again" are replaced by "No attempts left". The best counted attempt still counts. The admin audits a change as `assessment.max_attempts_changed` (old and new values).

**Lesson sign-in (D34).** `content.views.signin_required` wraps every `/learn/` view. The public pages are landing, register, sign-in and privacy (help, terms, grievance and certificate verify when they exist).

**Media (D34, D35).** `deploy/compose.yml` sets `MEDIA_ACCEL_REDIRECT=1` for web; `deploy/compose.edge.yml` mounts `csfr-<env>_media` read-only at `/srv/<env>/media` (created by `deploy.sh` like the static volumes); the Caddyfile's `handle_response` for `X-Accel-Redirect` serves the file with `file_server` (range requests, ETag, Last-Modified) and copies `Cache-Control`, `Content-Disposition` and `X-Content-Type-Options`. In development Django streams the file without range support.

## 28. Stage 6 implementation notes (staff tools)

**Access.** `batches_for` still scopes every mentor query. `apps/staff` adds `staff_required` (mentor or admin; a learner gets 403 and an `access.denied` audit) and `admin_required`. `rules.can_access_final_pool` is the single check for the final pool: `visible_questions` excludes it for mentors, the question pages 403 and log, the Django-admin `QuestionAdmin.get_queryset` hides it, and the editor refuses `pool=final` from a mentor.

**Dashboard (`mentors/dashboard.py`).** One `compute_results` call per batch feeds the roster, heatmap (red below 50, a dash where a module has no assessment), stuck learners and the eligible list. `batch_export` is a POST, scoped by `scoped_batch`, audited with counts only (`batch.exported`), and writes through `export.safe_cell`.

**Mark split (`staff/views.py`, `results/impact.py`).** `compute_results(user_ids, overrides)` applies proposed marks, counted flags and a module's counted flag in memory (`_counted_parts`). `impact()` runs it twice for every learner and compares `meets_requirements`. A change is previewed, then confirmed in a second request that recomputes and applies it inside one transaction with a `marks.changed` audit event (counts and the part values, no names).

**Report.** Per batch: registered, active, eligible, issued (0 until Stage 7), mean knowledge gain against the 25-point target; item statistics (% correct per question, per learner language); the email budget today.

**History.** simple-history records `Batch`, `Enrolment`, `Question` and `AssessmentPart` (`Historical*` tables).

**Attempt limits (D32).** `/staff/attempts/` (admin only) lists every assessment part and the final with one "maximum attempts" box each; blank is unlimited, 1–100 is accepted, anything else saves nothing. A change is saved under a row lock and audited as `assessment.max_attempts_changed` through `services.audit_limit_change`, like the Django-admin forms. The pre-test and mock have no field. The check at the start of an attempt is unchanged (§27).

## 29. Stage 7 implementation notes (certificates, D36)

**App `apps/certificates`.** `models.py`: `Certificate` (§6) and the one-row `CertificateSettings` (NSQF). `codes.py`: the verify code (Crockford base32, `normalise_code` reads case, spaces, hyphens and O/I/L leniently, and never accepts a certificate number), `next_serial()` (`nextval('certificate_serial')`, created by migration `certificates.0001`; `csfr_app` gets USAGE through the default privileges) and `certificate_number()`. `services.py` holds every rule: `issue`, `auto_issue_after_submit`, `awaiting`, `approve`, `revoke`, `erase_holder`, `issue_warnings` (guard A), `current_certificate` / `certificate_state` (the learner's page and dashboard card). `compute_results` now sets `already_issued` and `revoked_blocked` (a revoked certificate with no re-issue allowed) and records when each best attempt was submitted (`achieved_at`, printed as "Completed on").

**PDF (`pdf.py`).** `AllowlistFetcher` subclasses WeasyPrint's `URLFetcher` and answers only the `ccfr-asset:` names built for that certificate: the Latin Baloo 2 / Hind font files (names are in English letters, D37; a render takes under a second), the two partner logos, the signature files that exist (a setting can only name a plain file in `signatures/`) and the QR PNG made in memory. Every other URL, including `file:`, `http(s):`, `data:` and relative paths, is refused and logged. `base_url` is `None`; the template is rendered with `translation.override("en")`. WeasyPrint ignores `font-weight` ranges in `@font-face`, so the template declares one face per weight. The `weasyprint` and `fontTools` loggers are set to WARNING.

**Where it runs.** Auto-issue runs in the web request after the learner's own submit, only when `submit()` actually closed the attempt (so a double tap issues once) and the batch has auto-issue on; a failure is logged, audited as `certificate.issue_failed` and leaves the learner in "Awaiting approval". The `tasks` container has no media volume, so a stale auto-submit never issues; those learners also wait for approval. Issuing takes the learner's row lock, and the partial unique index backs it (Journey 13).

**Pages.** `/certificate/` and `/certificate/download/` (learners), `/verify/` and `/verify/<code>/` (public, also during guardian consent), the mentor batch page's certificate section (`/mentor/batches/<pk>/approve/`, scoped by `scoped_batch` and again in `services.approve`), and the admin: Certificates (read-only; actions "Revoke…" with a reason and an optional re-issue, "Remove holder details…"), Certificate settings (NSQF, audited as `certificate.settings_changed`), and the Batch admin's centre code (admin-only) and "Issue certificates to eligible learners" action. Audit events: `certificate.issued`, `certificate.approved`, `certificate.revoked`, `certificate.holder_erased`, `certificate.issue_failed` (IDs only; a revoke reason is kept on the certificate, not in the log).

**Server.** The image installs Pango and HarfBuzz for WeasyPrint and sets `XDG_CACHE_HOME=/tmp/.cache` for the read-only containers. No compose or Caddy change: PDFs and signatures sit in `media/private/` on the existing media volume. To add the signature images, a person copies the three PNG files into `/app/media/private/signatures/` in the web container (`signature-1.png` … `signature-3.png`, as named in `CERTIFICATE_SIGNATORIES`). Never commit them.

## 30. Stage 8 implementation notes (multilingual)

**Two kinds of text.** UI strings are gettext (`locale/{hi,mr,gu}/LC_MESSAGES/django.po`, compiled `.mo` committed). Course content (modules, units, blocks, assessment part names, questions, hints, fixed notes) is the `Translation` table in `apps/translations`. The certificate stays English (D36, D37).

**Keys (`apps/translations/keys.py`).** §14's `q:` and `blk:` plus `mod:<n>:<path>` (title, tagline, overview), `part:<id>:name` and `note:<name>` (fixed notes written in code, e.g. D33's crossword note). A path is a dotted walk through the JSON (`q:M1-04:options.2.text`, `blk:1.t3:4:items.0`); keys are server-side only. What may be translated is an allow-list per question format (`QUESTION_TEXT`) and per block type (`BLOCK_TEXT`); ids, keys, answers, flags, coordinates and scores are never on it. A paragraph is translated whole (its spans joined); a translated paragraph keeps its formatting only if it had one span. Crosswords have no translatable paths (D33).

**Staleness.** Each row keeps the English it was translated from (`source_text`) and its SHA-256 over normalised whitespace (`source_hash`). `Lookup.get(key, english)` returns the translation only while the current English has that hash; otherwise English. Coverage (Admin → Translations → Translation sheets) counts reviewed, draft, stale and missing lines per module and language.

**Draft and reviewed.** Every upload, admin edit and import saves a **draft** (`rules.save_line`); unchanged text over the same English is left alone. A per-language Reviewer (`translations.review_hi|mr|gu`) marks a line reviewed (admin action), never a line they uploaded and never a stale one (`rules.review_refusal`); audited as `translation.reviewed`. Learning pages (catalogue, module, unit, reveal and myth/fact answers) use drafts and show a "Draft translation" tag. Assessment text — questions, options, hints, part names and lesson practice checks — shows **reviewed lines only** (D24). The D33 note shows reviewed wording only (D7).

**Assessments (`apps/translations/assess.py`).** `display_body(version, fmt)` returns a display copy of the stored body with only allow-listed text leaves replaced; it is passed to `client_projection()` and `formats.label()`. Scoring, response checks and option maps always use the stored `QuestionVersion.body`. Answers are per-attempt tokens, so switching language mid-attempt changes only the words (`tests/test_translated_assessments.py` proves the projection's tokens and structure are identical, no translated hint or `why` reaches the browser, drafts and stale lines never show, and a mid-attempt switch keeps the saved token).

**XLSX round trip (`apps/translations/xlsx.py`).** Admin → Translations → Translation sheets: per module, columns `key`, `English`, then each language and its status. Cells are written as text (never formulas). Import is all-or-nothing and refuses unknown keys, a duplicated key, `[[!markers]]` or `{placeholders}` that differ from the English, `<`/`>` the English does not have, and a blank cell over an existing translation. A line whose English column differs from today's English is saved against the sheet's English, so it shows as stale. Uploading needs `translations.upload_translations` (Translator).

**Draft import (`import_draft_translations`).** Preview by default, `--apply` to save. Reads (private, `content-data/`): the team's pre-filled sheets, the corrected-table drafts, the hint workbook, the prototype's `data/i18n/*.js` and `js/phrases.js`; matches each to keys by English (whitespace, curly quotes and dashes ignored), never overwrites a row, refuses a line in the wrong script, and writes unmatched lines to `content-data/outputs/translation-import-report.csv`. `_framework-labels-verify.csv` has its columns shifted one to the left (English under `id`); the reader detects that. All imported lines are drafts.

**UI catalogues.** `fill_ui_drafts [--extra file.json]` fills empty `.po` entries from the prototype's phrases, its i18n files and the framework-labels sheet, then an optional JSON of further drafts; it never replaces a translation and skips a draft whose placeholders or tags differ. Filled entries carry the translator comment `draft: needs review`. Rosetta (`/rosetta/`, staff with `upload_translations` or superusers) edits the `.po` files of the running checkout; on a server those edits are lost at the next deploy, so download the catalogue from Rosetta and commit it in a PR. The dev image has GNU gettext for `makemessages`/`compilemessages`; production uses the committed `.mo` files.

**Interactive engine.** The engine's interface labels (`apps/questions/engine_labels.py`) reach the page as a `json_script` block (`{% engine_labels %}`); `engine/src/i18n.ts` looks them up and falls back to English. The block is data (never executed), so the CSP stays `script-src 'self'`. Crossword labels stay English (D33).

## 31. Stage 9 implementation notes (landing page and public pages)

**Pages.** `/` is `templates/landing.html` (signed-out visitors see Start certification and Sign in; a signed-in user sees Continue). `/privacy/`, `/terms/`, `/grievance/` and `/help/` are public, also for a learner waiting for guardian consent (the middleware allow-list). Privacy, terms and grievance carry a visible "Draft" notice until CyberPeace legal sends the wording. `404.html` extends the base layout; `500.html` is standalone (no context processors, no database) so an error never depends on what failed. Both are wired as `handler404` / `handler500`.

**D34 on a public page.** Calls to action go to `/register/` and sign-in, never into `/learn/`. The module list on the landing page is a plain list of the live modules (title, hours, 100 marks), not links.

**One FAQ.** `apps/core/faq.py` holds the questions once; the landing page shows those flagged for it, the help page all of them.

**The first-response check** has its own four scenarios written in the landing template. It never reads the question bank, which a test proves (no overlap with banked text, and the landing view imports neither the questions nor the assessments app).

**Who runs it.** A placeholder card until `PEOPLE_CONSENT_GIVEN` is on **and** `bhavesh-patel.jpg`, `nilakshi-jain.jpg` and `vineet-kumar.webp` are all in `PEOPLE_PHOTO_DIR` (default `content-data/people/`). Photos are served by `/people/<slug>/` (404 otherwise), never as static files, and are never in git (D22).

**Assets and CSP.** `static/css/landing.css` (the prototype's sections; the stage strip comes from `stage.css`), `static/js/landing.js` (tabs and one-open FAQ; panels are server-rendered and translated, JavaScript only toggles `hidden`). No inline script or style, which the Caddy CSP forbids. `static/img/favicon.svg`, `favicon-32.png`, `apple-touch-icon.png` and `social-preview.png` come from `tools/make_brand_assets.mjs`; the emblem slot is the text "CCFR" until the emblem exists (D23). `base.html` gains description, Open Graph and Twitter card tags.

**Translation.** 88 new UI strings were added as drafts (`draft: needs review`) in hi, mr and gu through `fill_ui_drafts --extra`.

## 32. Stage 10a implementation notes (launch hardening)

**Security headers.** `apps/core/security.py` (`SecurityHeadersMiddleware`) puts one strict `Content-Security-Policy` on every Django response: `default-src 'self'`, scripts, styles, fonts, media and connections from our own origin only, `img-src 'self' data:`, `frame-src https://www.youtube-nocookie.com`, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`, plus a `Permissions-Policy`. A view whose page embeds a YouTube film calls `allow_youtube_script(request)`, which adds `https://www.youtube.com` to `script-src` for that response only (the IFrame API; none do yet, D35). `/admin/` and `/rosetta/` get a separate policy with `'unsafe-inline'` and `'unsafe-eval'` for django-unfold (staff only, behind 2FA), still limited to our origin. The Caddyfile sets the same strict policy and the other headers with `?` (only when the response has none), so they cover the files Caddy serves itself (`/static`, `/learn/media`) and never double Django's; HSTS is per site (prod 1 year with subdomains, staging 300 s). A test checks the Caddy policy equals Django's. Checked in a browser on the full local course: no CSP violations on the landing page, lessons, films, practice checks, the interactive engine (with autosave), staff, mentor, admin and Rosetta pages.

**Rate limits.** Never django-ratelimit's `key="ip"` (Caddy's address); a test scans every `@ratelimit`. allauth's own limits use the real client because `_hosted.py` sets `ALLAUTH_TRUSTED_PROXY_COUNT = 1` (Caddy 2.11 replaces a client-sent X-Forwarded-For, so it has exactly one entry; the same rule as `client_ip`). Limits (lead, 14 Nov 2026, sized for a whole batch on one network): sign-in 90 a minute per network; failed sign-ins 30 a minute per network and 5 per 5 minutes per email; password reset allauth's defaults; sign-up 90 per batch per 10 minutes (`REGISTER_RATE`); `/verify` 30 per 10 minutes per client IP; `/learn/check` and the block endpoint 120 an hour per learner; saving answers 1200 an hour and submitting 60 an hour per learner (`ANSWER_RATE`, `SUBMIT_RATE`); the mentor reset link 30 an hour per client IP; resending the guardian email 5 an hour per user. Every hit answers **429** with `Retry-After` and says how long to wait (`apps/core/ratelimits.py`: `handler429` for allauth, `RATELIMIT_VIEW` for ours, the sign-up and verify pages compute the minutes from their rate); a wrong-password lock says "wait 5 minutes". On a 429 while saving, `attempt.js` keeps the answer and retries.

**Edge Caddy.** One fixed config outside both env checkouts: `deploy/deploy.sh edge [ref]` (`deploy/edge.sh`, default `main`) checks out `/srv/csfr/edge/src`, validates the new Caddyfile in a throwaway `caddy:2`, installs it into `/srv/csfr/edge/caddy/` (keeping `Caddyfile.prev`), starts `csfr-edge` from `/srv/csfr/edge/compose.edge.yml` (same project name, so the TLS certificate volume is kept) and reloads; a failed reload restores the previous file. `deploy.sh staging|prod` no longer touches Caddy and warns if it is not running. Tested by hand with a throwaway Caddy and a fake upstream (validation gate, headers, reload without recreating, moving the project directory keeps the certificate volume); the one-time server move is in `docs/runbook.md` §1.1.

**Monitoring.** Sentry (off without `SENTRY_DSN`) sends no request bodies, cookies, headers, query strings, user, frame variables or email addresses (masked in messages, exception text and breadcrumbs). `apps/core/monitoring.py::ping` sends a bare GET to a heartbeat URL (off when empty; `<url>/fail` on failure; a failing ping never breaks the caller): `TASKS_PING_URL` after every `tasks` wake-up, `BACKUP_DB_PING_URL` and `BACKUP_MEDIA_PING_URL` from the backup scheduler (curl added to the backup image). `deploy/server/disk-check.sh` runs from the host's cron and pings `DISK_PING_URL` (`/fail` at 80%). The uptime pinger on `/healthz/` and the accounts are set up by a person (`docs/runbook.md` §9).

**Runbook.** `docs/runbook.md`: deploy (with the edge step and its one-time move), the Stage 8 deploy steps, smoke test, roll back, the timed restore drill and a real restore, rotating every secret, a personal-data breach (DPDP: the Board and each person without delay, a detailed report within 72 hours), adding admins and mentors, loading the course onto a server from the private inputs, and monitoring.
