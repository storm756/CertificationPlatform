# Settled decisions

These are product decisions. **Build to them.** If one seems impossible or harmful, raise it. Don't work around it.

| # | Decision |
| --- | --- |
| D1 | Certificate result = **50% module assessments + 50% final exam**. This is the whole result (it replaces the booklet's 20/30/30/20). |
| D2 | **Learning is never locked.** Learners see their % per module and for the final. Final pass mark: **50%**. Module pass mark: **50%**. |
| D3 | **Unlimited attempts; the best counted attempt per part counts.** A timer is shown but not enforced (a setting exists for later). |
| D4 | Learners **self-register with their own email** and pick a batch from a dropdown. |
| D6 | Practicum, portfolio and viva come **later**. Don't build them now, but don't design anything that blocks adding them. |
| D7 | Languages: **English, Hindi, Marathi, Gujarati**. The team reviews every translation. |
| D8 | Custom Django platform. **No Moodle.** |
| D9 | **Registration is closed by default**, for every batch including the catch-all "Open Enrolment" pool. Only a batch that a mentor or admin has opened (optionally for a time window) accepts sign-ups. The server re-checks this on submit. |
| D10 | Certificates are **English only, delivered on the website** (no email). Each batch has an **auto-issue** switch; otherwise the mentor approves batch by batch. Email (Brevo, 300/day) is used **only** for verification, password reset and guardian consent. |
| D11 | Staff can add content (Word, text, images, PDF, video links) and questions (form or spreadsheet) **without developers**. **Every module = 100 marks**, split across its assessment parts (today MCQ 50 + Interactive 50). |
| D13 | After an assessment: score, ✓/✗ per question, and a **hint**. **Never the correct option.** Full worked answers appear only in practice. |
| D14 | Final exam: a random draw per learner, questions and options shuffled, per-module results shown as **bands** (strong / OK / needs work), no answers shown. A wait between attempts is a setting, **off** by default. |
| D15 | A module submission counts toward unlocking the final only if **every question was answered**. |
| D16 | **Minimum age 16.** 16–17-year-olds need **guardian consent** (by email) before activation and get **no time-on-task tracking** (DPDP). The consent method is pending confirmation by CyberPeace legal, so keep it isolated in `GuardianConsent`. |
| D17 | **The certificate name is typed at registration** and shown as a preview. After that only a mentor or admin can change it. |
| D18 | **Films are on YouTube** (unlisted, `youtube-nocookie.com` embed). An MP4 upload is the fallback. No video processing on our server. |
| D19 | Repo `storm756/CertificationPlatform`, domain **cyberfirstresponse.io** (staging: `staging.cyberfirstresponse.io`). The old 405 MCQs are public, so they go into the module-quiz and practice pools only. **The final pool is written fresh** by the content team. |
| D25 | **Safety gate:** an attempt containing a choice that would endanger a citizen (e.g. asking for an OTP) is shown with its score but **never counts**. |
| D20 | **Visual direction is the team's standalone frontend prototype** (cream header with both partner logos, navy hero, mustard primary button, Learn → Practise → Assess → Certify stages). It lives in `design-reference/frontend-prototype/` as the reference for every page. It is the look, not production code. |
| D21 | **No dark mode in v1.** Remove the prototype's night-mode toggle. One light theme only, to halve the design and testing work. |
| D22 | **Both repos stay public until launch.** Before the first batch, the old `csfr_Project` repo is deleted. Until then: no secrets, no question data, no answer keys in git. |
| D23 | **Programme name: Community Cyber First Responder, short form CCFR** (decided 10 Nov 2026). Code reads it from `settings.PROGRAMME_NAME` / `PROGRAMME_SHORT`, never hard-coded. The prototype says "CSFR" in places, and every one of those becomes CCFR. **The programme gets its own emblem** (wanted, design pending). Keep a slot for it in the header, on the landing page and on the certificate. The certificate's qualification title and its signatories are still open (STATUS.md). |
| D24 | **Assessments may be shown in Hindi, Marathi or Gujarati once a reviewer has approved that wording.** Until then they show in English (architecture §14). They are not English-only forever. |
| D26 | Module 10 (capstone) = a learning module, not graded. The old mixed 20-challenge set = a practice mock before the final. The Module 8 crosswords move to practice. |
| D27 | **A `tasks` service for daily jobs is allowed.** It runs on the web image with a `run_periodic` loop (every 10 minutes, jobs scheduled in Asia/Kolkata time, catch-up once after a restart). It is **not** a job queue: Redis and Celery stay rejected. Today's jobs are `purge_unverified` (Stage 1) and auto-submitting stale attempts (Stage 2). |
| D28 | **The certificate-number prefix comes from settings** (`CERTIFICATE_PREFIX`, today `CCIFR-<year>-<centre>-<serial>` as in architecture §12). The lead confirms the final prefix, qualification title, wording and signatories before Stage 7. |
| D29 | **Only a person merges, deploys, or pushes to `main`.** Claude prepares branches and PRs; the builder reviews and merges them. `.claude/settings.json` blocks `deploy/deploy.sh`, `ssh` and `gh pr merge` for Claude, and branch protection on `main` requires a PR and a green CI (0 approvals, so the builder can merge her own PRs). |
| D30 | **The CCFR rename covers user-facing text only** (pages, emails, PDFs, page titles). Internal names such as the `csfr_owner` / `csfr_app` DB roles, container names and cookie or storage keys stay as they are. |

D5 and D12 aren't used. Numbers are never reused.

## Where decisions change `docs/architecture.md`

Until these are folded into architecture.md, **the decision wins.** The Stage 1.5 PR folds them in, after `stage-1` is merged, so the two don't conflict.

| Architecture section | Change |
| --- | --- |
| §1 title and text | "CSFR" becomes Community Cyber First Responder (CCFR) (D23, D30) |
| §2 overview, §3 "Not used", §17 containers | Add the `tasks` service (D27). "No background worker" still holds for job queues. |
| §2.2 styling, §14 fonts | The look comes from the prototype (D20). Fonts are Baloo 2, Baloo Bhai 2, Hind and Hind Vadodara. One light theme (D21). |
| §4 code layout | Apps live in `apps/` (`apps/accounts`, `apps/batches` …), and the docs live in `docs/`, not `docs/design/`. |
| §12 certificate number | The prefix comes from settings (D28). |
| §14 translations | Reviewed translations may show in assessments (D24). |
| §17 deploys | "Deploy script over SSH" means **a person** runs `deploy/deploy.sh` (D29). |
