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
| — | **Safety gate:** an attempt containing a choice that would endanger a citizen (e.g. asking for an OTP) is shown with its score but **never counts**. |
| — | Module 10 (capstone) = a learning module, not graded. The old mixed 20-challenge set = a practice mock before the final. The Module 8 crosswords move to practice. |
