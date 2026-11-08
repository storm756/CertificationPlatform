# CSFR Certification Platform: Architecture v2 (consolidated)

* **Status:** Approved design. This is the single source of truth.
* **Date:** 2026-11-07
* **Binding requirements:** `docs/decisions.md`.

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
| Pages | Django templates + **HTMX** | Fast on cheap phones, one codebase |
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

**Not used:** Redis, Celery, a background worker, Wagtail, a React SPA, JWT. Each was considered and rejected; the review history has the reasons.

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
├── templates/ static/ locale/
├── tests/                    pytest (unit, integration) · Playwright (journeys in §18)
├── deploy/                   compose.yml (per-env stack), compose.edge.yml (shared Caddy), compose.dev.yml, Caddyfile, backup/ + restore.sh, server/bootstrap.sh
└── docs/design/              these documents
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
| Batch | name, code ★unique, centre, start/end dates, accepting (on/off), opens_at, closes_at, seat_limit (default 40), is_open_pool ★only one, auto_issue (off), status (active / archived) |
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
| Certificate | user, certificate_no ★unique (from a DB sequence), verify_code ★unique (random), status (`issued` / `revoked`), snapshot JSONB, pdf_path, pdf_sha256, issued_by (user or "auto"), revoked_reason. ★ **partial unique: one `issued` certificate per user.** |
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

### 8.1 Module page

* Film (YouTube)
* Handout (web text + PDF)
* Online units (reading, check, practice quiz)
* Assessment parts, each with its best % and a Retake button

Nothing is locked.

### 8.2 Films on YouTube (D18)

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
 (final only) cooldown_hours > 0 and last final attempt too recent? → "Next attempt available at …"
 draw:
   part.selection = all / all_shuffled → its questions
   part.selection = draw → random draw_n from part.pool with ≥ min_per_tag per tag,
                           excluding questions in this learner's previous attempt where possible
   final → blueprint per_module counts from the final pool + all anchors, random order
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
| Questions | `per_module` counts from the **final** pool. Today: 6/6/5/6/6/6/5/5/5 = 50, which already includes the anchors (e.g. 2 per module = 18). | The anchors only |
| Pool rules | A question shown in any non-final attempt **can't be moved** into the final pool (enforced on save). The blueprint must be updated when the counted modules change. | — |
| Timer | Shows "about 60 min", not enforced | Shows a count-up |
| Feedback | Overall % + bands (§9.5) | Score only. **Anchors are never given feedback anywhere.** |
| Attempts | Unlimited, cooldown setting (0) | One attempt (resumable) |

**Knowledge gain (CSR ≥25%)** = anchor score in the learner's **first** final attempt − anchor score in the pre-test. It is reported per batch.

---

## 12. Certificates

```text
issue(user)   ← called by auto-issue (on submit) or by the mentor's "Approve batch" action
  lock user row
  re-run compute_results; not eligible → stop
  certificate_no = next value of a DB sequence → CCIFR-<year>-<centre>-<6-digit serial>
  verify_code    = 10 random chars (Crockford base32)
  snapshot = {certificate_name, batch, centre, dates, module %s, final %, overall %, grade, hours, policy_version}
  PDF = WeasyPrint(template, snapshot)  — url_fetcher allows bundled fonts/logos only; English only
        QR (segno) → https://<domain>/verify/<verify_code>
  save PDF (private media), sha256; Certificate(status=issued); audit
revoke(cert, reason)  ← admin only; verify page then shows "Revoked"
```

* **Learner:** a "Your certificate" card with a Download button (served through Django to the owner only). There is no email.
* **Mentor:** an "Awaiting approval" list (eligible learners in batches with auto-issue off) and an "Issued this week" list.
* **Switching auto-issue on** for a batch does **not** bulk-issue the people already waiting. The mentor clicks "Approve all" once, deliberately.
* **The public verify page** (rate-limited) shows name, qualification, grade, issue date and status. There is **no lookup by certificate number**, so no one can walk the list and harvest names.
  If the holder has requested erasure, it says *"Issued; holder details removed at the holder's request."*
* **NSQF wording:** *"NSQF level and credits shown after approval by the competent authority"* until an admin turns `nsqf_approved` on, which affects new issues only.

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
                  draft → shown in learning units with a "draft translation" tag; assessments fall back to English
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
* **Crossword:** practice mode only. Module 8's graded set needs about 6 replacement challenges (teammates).
* **Fonts:** Baloo 2 + Hind (Latin and Devanagari), Hind Vadodara (Gujarati), self-hosted.
* **Certificate:** English only.

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
| Web | CSP (self + youtube-nocookie frames), HSTS, frame-deny, CSRF, auto-escaping, nh3 sanitising, WeasyPrint url_fetcher allowlist, HTMX eval off |
| Accounts | allauth, Argon2, staff MFA, rate limits, no account enumeration, mentor-reset safeguards |
| Server | SSH keys only, ufw 22/80/443, fail2ban, unattended upgrades, non-root containers, separate secrets per environment, two DB roles |
| Media | `/media` served by Caddy only after a Django `forward_auth` check. Certificates are served only by Django to the owner. |
| DPDP | Minimum fields; pseudonymous audit; erasable Profile; guardian consent and no tracking for minors; processors listed in the notice (Brevo, Sentry, YouTube, the backup provider and region); 72-hour incident runbook; a named grievance officer (CyberPeace); retention of 3 years after programme end |

---

## 17. Deployment and operations

| Topic | Plan |
| --- | --- |
| Pipeline | git push → GitHub Actions (ruff, pytest with Postgres, Playwright) → deploy script over SSH to **staging** → manual check → same script to **prod** (DB dump taken first) |
| Deploy script | `git pull → docker compose build → migrate (as csfr_owner) → collectstatic → restart`. **No content loading.** |
| Stacks | Staging and prod are two separate instances of `deploy/compose.yml` (own project name, `.env`, DB, volumes). One shared Caddy (`deploy/compose.edge.yml`) owns ports 80/443 and routes by host name over the `csfr-edge` network. See `docs/server-setup.md`. |
| One-time import | `importers/` loads the existing material once. It refuses to run if any content version was edited in the app. |
| Backups | Hourly `pg_dump` + nightly media to off-site storage with **write-only credentials and object lock**. Encrypted to a public key; the **private key is held offline by two named people**. Kept for 48 hours (hourly), 14 days (daily) and 8 weeks (weekly). |
| Restore drill | In a throwaway stack (never staging), before launch and every term |
| Monitoring | An uptime pinger (5 min), Sentry (scrubbed), a disk alert at 80%, the email budget alert |
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
   * Module 8 replacement challenges
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
* `purge_unverified` (management command) deletes learner accounts unverified after 7 days. It is not scheduled yet.
* **Audit**: `apps.audit.AuditEvent` + `audit()`; the migration revokes UPDATE/DELETE/TRUNCATE from `csfr_app` (skipped where that role doesn't exist, e.g. dev and CI).
* `accounts.rules.may_track_time(user, today)` is the single question the Stage 4 heartbeat must ask (false under 18).
* After sign-in everyone goes through `/start/`: pending learners to the waiting page, mentors to their batches, learners to a welcome page whose pre-test prompt is a placeholder until Stage 5.
