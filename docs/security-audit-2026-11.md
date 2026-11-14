# Security audit and code review: November 2026

**Auditor:** Claude (Opus 5.5), a fresh session that did not write this code. **Date:** 15 Nov 2026.
**Audited:** `origin/main` at `daa46de` (after the pilot fixes, PR #21), in a clean git worktree with no gitignored files.
**Not audited:** prod (never touched); the server itself, beyond the read-only output the lead pastes back (§6); content data (`content-data/`).

## 1. How it was done

* **Static review** of every view, decorator, service and template that handles access, exams, auth, uploads, media, certificates and
  privacy, plus the Docker, Caddy, backup and CI files. Checklists came from the Cloudflare `security-audit` skill (its attack classes,
  web/auth, data isolation, cloud/deployment and supply chain lists) and from ECC's Django security and security-review files. Both were
  read as Markdown only; nothing from either was installed or run.
* **Tools** (each a throwaway container; nothing installed on the PC):
  * `pip-audit 2.7.3` over `requirements-dev.txt` and `loadtest/requirements.txt`: one vulnerable package (Pillow, H2).
  * `gitleaks v8.21.2 --redact` over a mirror of the full GitHub history (all branches and PR refs, 122 commits): **no leaks**.
  * A path scan of all of history for `.env`, dumps, keys, signatures and photos: none committed. The handout PDFs are in git (I3).
* **Passive checks of staging:** response headers (`curl -sI`) on `/`, sign-in, `/admin/`, `/verify/` and `/learn/media/1/`, plus reading
  `/healthz/` and `/register/`. Headers are correct everywhere (CSP, HSTS 300 s, frame deny, nosniff, `noindex`). A signed-out
  `/learn/media/1/` goes to sign-in. **`/register/` on staging shows an open batch ("STG1 · Staging test")**, which matters for H3.
* No load tests, no brute force, nothing against prod. Any other dynamic test is proposed in §6, for the lead to approve one at a time.

Severity: **Critical** = exploitable now by anyone, serious impact. **High** = serious impact, a likely precondition. **Medium** = real
but limited impact or harder to reach. **Low** = defence in depth. **Info** = no fix needed, worth knowing.

## 2. Summary

| # | Severity | Finding | Status |
| --- | --- | --- | --- |
| H1 | **High** (Critical while seeded) | The journey and load-test seeds create a staging **superuser** whose password and TOTP secret are in the public repo | Fixed in PR `security-fixes` |
| H2 | **High** | Pillow 12.0.0 has 61 published advisories and decodes every uploaded picture | Fixed in PR `security-fixes` |
| H3 | **High** (conditional) | The final's overall % is an answer oracle with unlimited attempts, and staging's open registration lets anyone farm it | Final limit 3 on prod and staging, STG1 closed (lead, 15 Nov); staging login in PR `staging-login` |
| M1 | Medium | The daily email budget can be drained by strangers, blocking real resets, guardian consent and sign-up verification | Fix proposed for the second PR |
| M2 | Medium | The sign-up rate limit is keyed on the raw `batch` value, so `01`, `001` … each get a fresh bucket | Fix proposed for the second PR |
| M3 | Medium | An email change does not notify the old address (architecture §7.4 says it does), and accounts may add unlimited addresses | Fix proposed for the second PR |
| L1 | Low | Open redirect in `POST /notice/dismiss/` (`next`) | Fix proposed for the second PR |
| L2 | Low | One-time tokens in gunicorn access logs; Docker log rotation unknown | Server check (§6) |
| L3 | Low | No retention for audit IPs, `EmailLog`, consent IPs; expired sessions are never cleared | Needs a retention decision |
| L4 | Low | UI translations (`.po`, Rosetta) are rendered unescaped, so a translator can inject HTML | Report only |
| L5 | Low | `mc` with `keep_order` and `settings` options are shown in authoring order | Content check |
| L6 | Low | The backup container gets the whole `app.env` (Django secret key, SMTP key) | Report only |
| L7 | Low | Images are not pinned by digest; Actions are pinned to major tags | Report only |
| L8 | Low | Staging and prod web containers share the `csfr-edge` network | Report only |
| L9 | Low | A new staff account's first sign-in enrols TOTP, so whoever signs in first owns the second factor | Runbook note |
| I1–I4 | Info | See §4 | — |

## 3. Findings

### H1. Public credentials for a staging superuser (High; Critical whenever the seed data exists)

* **Where:** `apps/core/e2e_data.py` (`PASSWORD = "e2e-…"`, `TOTP_SECRET = "JBSWY3DPEHPK3PXP"`; `_user()` calls `create_superuser` for
  `admin@e2e.example.com`, and the load seed makes `lt-admin@load.example.com` the same way); `loadtest/locustfile.py` (the same
  password as default). Runbook §8 runs `e2e_seed` and `loadtest_seed` **on staging**, which is on the public internet.
* **Reproduce (staging only, do not actually do it):** while the seed data exists, anyone who reads this public repo can sign in at
  `https://staging.cyberfirstresponse.io/accounts/login/` as `admin@e2e.example.com` with the password from the file, and compute the
  6-digit code from the secret in the file (the secret is the best-known example value used in TOTP tutorials).
* **Impact:** full superuser on staging. Per STATUS, staging holds the real course and the released **final exam sets B and D**, the same
  papers prod uses, with their answer keys (`/admin/`, `/preview/exam/final/?set=B`). It also gives every learner and mentor row on
  staging, Rosetta, and the power to create more staff. The exposure lasts from `e2e_seed` until `e2e_clean` succeeds; if a clean step
  was skipped or failed, it is still open. The seeded mentors and learners have the same password.
* **Fix (done):** every seed run makes a new random password (`secrets.token_urlsafe(24)`) and a new random TOTP secret (160 bits), sets
  them on every marked account it touches (a rerun retires the old ones), and prints them only in its manifest. The load-test admin gets
  no usable password and no authenticator (nobody signs in as it). `locustfile.py` has no default password any more and stops with a
  clear message if `LT_PASSWORD` is missing. The runbook and `e2e/README.md` now say the manifest holds live credentials: write it with
  `umask 077`, never commit or paste it, run the clean command straight after, delete it. The journeys already read the password and
  secret from the manifest, so they need no change.
* **Tests:** `tests/test_e2e_seed.py`: a second run gives different credentials and the first run's password stops working (admin and
  learner); one authenticator with this run's secret; the load admin cannot sign in; no fixed credentials anywhere in the code.
* **Lead, now:** check whether marked accounts exist on staging (§6, command S8). If they do, run `e2e_clean` / `loadtest_seed --clean`
  there, or at least deploy this fix and re-run the seed (which retires the public password). Then check the admin audit log for
  sign-ins by `@e2e.example.com` / `@load.example.com` accounts from addresses that aren't yours.

### H2. Pillow 12.0.0 with 61 known advisories (High)

* **Where:** `requirements.txt` (`Pillow==12.0.0`). pip-audit lists 61 PYSEC/GHSA advisories, fixed in 12.1.1 to 13.0.0. Pillow decodes
  every uploaded picture: lesson images and posters (`apps/content/media.py`), hotspot art (`apps/questions/images.py`) and the pictures
  inside an uploaded Word file (`apps/content/docx.py`).
* **Reproduce:** `pip-audit -r requirements.txt` (no staging test needed).
* **Impact:** only staff can upload, so the realistic route is a crafted picture, for example inside a Word file a mentor is sent and
  uploads. Image-decoder bugs range from crashes (a worker held up) to memory corruption. The code's own checks (pixel cap, `verify()`,
  re-encoding) run *inside* Pillow, so they don't protect against a decoder bug.
* **Fix (done):** `Pillow==13.0.0` (released 16 Oct 2026; WeasyPrint 70 needs Pillow ≥ 9.1). The full test suite passes with it, including
  the upload, hotspot and certificate PDF tests.
* **Test:** `tests/test_dependency_floors.py` fails if Pillow is ever pinned below 13.0.0. **Follow-up:** add `pip-audit` to CI (§5) so the
  next advisory shows up on a PR, not in an audit.

### H3. The final's overall score is an answer oracle, and staging lets anyone farm it (High, conditional)

* **Where:** design, not a bug in one line: D31 (a batch's final is always the same 50 questions of its set), D3/D32 (unlimited attempts
  unless an admin sets a maximum; the cooldown is off by default), and `templates/assessments/programme_result.html` (the overall % is
  shown). Bands per module (§9.5) were meant to stop learners working out single answers, but the **overall %** already moves by exactly
  2 points per question.
* **How it works (do not run):** a learner who reaches the final submits it once, then repeatedly changes one answer and resubmits. Each
  change of ±2 % says whether that option is right. With 50 single-choice questions that is about 75–100 attempts. Scripted, the save
  (1200/h) and submit (60/h) limits allow that in a few hours per account. Accounts are free.
* **Why staging makes it worse:** staging registration is open to anyone ("STG1 · Staging test" on `/register/`), staging sends real
  verification email (architecture §33; if staging uses Mailpit instead, strangers can't verify and this part falls away), the final unlocks once every module part has been **submitted with every question answered** (not passed), and
  per STATUS staging has the real sets B and D released. If STG1 (or any open staging batch) has set B or D assigned and no attempt
  limit, a stranger can derive the real answer keys for prod's final on staging, where nobody is watching. On prod the same attack works
  for any registered learner unless the final has a maximum.
* **Fix (lead's decision; nothing changed in code):**
  1. **Prod and staging now:** Staff tools → Attempts (`/staff/attempts/`) → set a **maximum** for the final (e.g. 3) and, if you want, a
     cooldown on the final's row in the admin (e.g. 24 h). This is the D32 setting and needs no deploy. It does not stop a single attempt being shared, but it stops the oracle.
  2. **Staging:** don't leave real exam sets reachable from an open public batch. Either close STG1 when nobody is testing, or assign it an
     invented set, or (recommended) put staging behind a login in Caddy (`basic_auth` on the staging site, with `/healthz/` left open for
     the uptime monitor). I can prepare the Caddy change and the Playwright/locust credentials for it in a PR if you say so.
  3. **Optional, product call:** show the final result without the exact % (pass/fail and the bands), or round it to the nearest 10 %.
     That would change D14/§9.5, so it's for the lead and the programme team.

### M1. Strangers can drain the daily email budget (Medium)

* **Where:** `apps/accounts/adapter.py`, `apps/accounts/email_budget.py`. Budgets per day: registration 150, reset + guardian 100. allauth
  sends an "unknown account" email for a reset request to an address with no account (`ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS` default on), and
  PR #21 counts that email against the reset pool (so the second-request message is the same for known and unknown addresses).
* **Reproduce (staging, needs approval, T4 in §6):** request a password reset for 100 made-up addresses. allauth allows 20 a minute per
  network, so it takes about 5 minutes. After that, a real learner's reset request sends nothing until midnight IST, and nor does a
  guardian consent email. The same works for the 150 sign-up verifications through an open batch (and M2 removes the per-batch brake),
  or through `/accounts/email/` (M3) from one verified account.
* **Impact:** a cheap, repeatable denial of service on sign-up, password reset and guardian consent during a pilot week. It also sends
  mail from our domain to addresses an attacker chooses, which hurts the sender reputation.
* **Fix (second PR):** stop sending the unknown-account email (it's a courtesy, not a requirement). Instead, record a marker row that
  belongs to no pool, so the "already sent today" message still shows identically for known and unknown addresses (the PR #21 test stays
  green). Add a per-network daily cap on reset emails (e.g. 30 a day per client IP) on top of allauth's per-minute limit. Keep the 150
  alert. Tests: an unknown-address reset sends no mail and uses no budget, the page is identical, and 100 unknown resets leave the pool
  untouched.

### M2. The sign-up rate limit can be dodged (Medium)

* **Where:** `apps/accounts/views.py::_rate_key` returns `request.POST.get("batch")` as-is. `ModelChoiceField` accepts `2`, `02`, `002`
  and `2 ` for the same batch, and each string is a separate django-ratelimit bucket.
* **Reproduce (staging, T5):** POST `/register/` with `batch=02`, `batch=002` …: each starts a fresh 90-per-10-minutes allowance.
* **Impact:** the only brake on mass sign-ups to an open batch disappears, which feeds M1 and fills the database with throwaway accounts
  (purged after 7 days).
* **Fix (second PR):** key on the integer batch id (`int(value)` or `"invalid"`), with a test that `02` and `2` share one bucket.

### M3. Email changes are silent to the old address (Medium)

* **Where:** `config/settings/base.py` sets neither `ACCOUNT_EMAIL_NOTIFICATIONS` nor `ACCOUNT_CHANGE_EMAIL` nor
  `ACCOUNT_MAX_EMAIL_ADDRESSES`. Architecture §7.4 says an email change is re-verified at the new address and **the old address is
  notified**; only the first half happens.
* **Impact:** someone who gets into a learner's or mentor's session (a shared lab PC, a lost phone) can add their own address, verify it,
  make it primary and remove the owner's, and the owner is never told. They can then reset the password at will. Each added address also
  sends a verification email (M1).
* **Fix (second PR):** `ACCOUNT_CHANGE_EMAIL = True` (one address, a change replaces it after verification), `ACCOUNT_EMAIL_NOTIFICATIONS =
  True` (the old address hears about email and password changes), and count those notices against the reset pool. Tests: a change sends
  a notice to the old address; an account cannot hold a third address.

### L1. Open redirect after dismissing the reset notice (Low)

* **Where:** `apps/accounts/views.py::dismiss_reset_notice`: `redirect(request.POST.get("next") or "start")`.
* **Impact:** low, because it is POST-only and needs the CSRF token, so another site can't trigger it. It is still an open redirect if
  anything on our own pages ever lets a user choose `next`.
* **Fix (second PR):** accept `next` only if `url_has_allowed_host_and_scheme()`; otherwise go to `start`. Test with `https://evil.example/`.

### L2. One-time tokens in access logs (Low)

* **Where:** `Dockerfile` (`gunicorn --access-logfile -`). Every request path is logged, including `/reset/<token>/` (mentor reset),
  `/guardian/<token>/`, `/accounts/password/reset/key/<key>/` and `/verify/<code>/`. They go to Docker's log driver.
* **Impact:** anyone with `docker logs` (the `deploy` user, a log shipper later) sees live one-time links for up to an hour (mentor reset)
  or 14 days (guardian). The default `json-file` driver also never rotates, so logs can fill the disk.
* **Fix:** check rotation on the server (§6, S6). Recommended: in `/etc/docker/daemon.json`, `"log-opts": {"max-size": "20m", "max-file":
  "5"}` (needs root, so it's a hosting task), and drop gunicorn's access log (Caddy can keep one with `log` and a path filter) or log
  paths with tokens masked.

### L3. Personal data with no retention limit (Low, DPDP)

* **Where:** `AuditEvent.ip` on every audited action, `ConsentRecord.ip`, `EmailLog` (hashed addresses), and the `django_session` table
  (`clearsessions` is never run: `apps/core/periodic.py` has two jobs).
* **Impact:** IP addresses are personal data under DPDP. Architecture §16 says data is kept 3 years after programme end, but nothing
  enforces any limit. Expired sessions pile up and keep each user's id.
* **Fix:** decide a retention period for IPs (for example, blank `ip` on audit rows after 180 days) and add it, with `clearsessions`, to the
  `tasks` loop (D27 allows more daily jobs). A small PR once the period is decided.

### L4. Translations can inject HTML (Low)

* **Where:** Django treats a translated template literal (`{% translate "…" %}`, `{% blocktranslate %}`) as safe, so `msgstr` text from
  `locale/*.po` is not escaped. Translators edit those files in Rosetta (`can_use_rosetta`: staff with `upload_translations`), and the
  drafts come from tools.
* **Impact:** a translator, or a bad draft merged without review, can put links, forms or fake notices into any page. The strict CSP
  blocks scripts and form posts to other sites, so it's phishing-grade, not XSS. Course text in the `Translation` table goes through
  normal escaped variables and is not affected.
* **Fix:** keep the people review (D7). Optionally add a CI check that fails if any `msgstr` contains `<` where its `msgid` doesn't.

### L5. Some option lists keep their authoring order (Low)

* **Where:** `apps/questions/formats.py`: `MC.make_map` doesn't shuffle when `keep_order` is set (the legacy importer sets it when any
  option has a colour, and the colour triage order is deliberate), and `Settings.make_map` never shuffles choice options. Tokens are
  random, but the **position** on screen is the authored one.
* **Impact:** if authors list the right choice first (CLAUDE.md says they usually do), position leaks it for those questions.
* **Fix:** content check: list the live `mc` questions with `keep_order` and the `settings` questions, and confirm their right answer isn't
  always in the same place. If it is, shuffle `settings` options (they have no natural order), and keep `keep_order` only for triage.

### L6. The backup container holds every secret (Low)

* **Where:** `deploy/compose.yml`, `cron` service: `env_file: ${CSFR_ENV_FILE}` (the whole `app.env`). It needs `DB_*`, `AGE_PUBLIC_KEY`,
  `BACKUP_*` and `RCLONE_CONFIG_*`, not `DJANGO_SECRET_KEY` or `EMAIL_HOST_PASSWORD`.
* **Fix:** a separate `backup.env` (or `environment:` with only those names). It's a change to the server's env files, so it's a planned
  step, not urgent.

### L7. Unpinned images and actions (Low)

* `python:3.12-slim`, `postgres:17`, `caddy:2` and `axllent/mailpit:latest` are tags, not digests; GitHub Actions use `@v4`/`@v5`. A
  compromised or broken upstream tag reaches the next build. CI has `permissions: contents: read` and no secrets, so the blast radius in
  CI is small. **Fix:** pin images by digest (Dependabot or Renovate can bump them) and actions by commit SHA.

### L8. Staging and prod share a network (Low)

* `web-staging` and `web-prod` are both on `csfr-edge`, so code running in the staging container can call prod's gunicorn directly,
  skipping Caddy and sending any `X-Forwarded-For` it likes (rate limits and audit IPs trust that header). The databases are separate
  and private. **Fix:** one edge network per environment (`csfr-edge-staging`, `csfr-edge-prod`), both joined by Caddy.

### L9. First sign-in of a new staff account (Low)

* `StaffMFARequiredMiddleware` sends a staff user without TOTP to set it up, so whoever signs in first with the password enrols the second
  factor. **Fix (runbook):** hand over the first password in person or by a different channel than the address, and have the person enrol
  TOTP straight away. Check Admin → MFA that each staff member has exactly one authenticator.

## 4. Information (no fix needed)

* **I1.** The staff session's 12 hours slides with activity (`set_expiry` on every request), so an active staff session never ends. Fine for
  now; make it absolute if a policy needs it.
* **I2.** Settings order: `staging.py`/`prod.py` import `_hosted` before `base`, so `base` would win if it ever defined a hardening name.
  Today none overlap (checked). Swapping the two imports would make that impossible.
* **I3.** The handout PDFs (`apps/content/data/handouts/`) are in the public repo, so D34's sign-in for handouts doesn't keep them private.
  Fine if they're meant to be shareable.
* **I4.** Static 404s from Caddy carry `Server: Caddy`. Harmless.

## 5. Recommended follow-ups (not findings)

* Add `pip-audit` to CI (one job, a few seconds) and turn on Dependabot alerts for the repo.
* Branch protection: require the `lint`, `test`, `e2e` and `deploy-files` checks (STATUS says no required checks yet).
* CodeRabbit: `.coderabbit.yaml` is added in the fix PR (Django and security focus, ignores `design-reference/` and `locale/`).

## 6. Server and staging checks for the lead

**Read-only server commands** (`ssh ccfr`; none prints a secret):

* S1 `git -C /srv/csfr/staging/src log -1 --oneline; git -C /srv/csfr/prod/src log -1 --oneline`
* S2 `ss -tlnp` (expect only 22, 80, 443 on public addresses, plus Mailpit on 127.0.0.1)
* S3 `docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'`
* S4 `docker inspect --format '{{.Name}} user={{.Config.User}} privileged={{.HostConfig.Privileged}} readonly={{.HostConfig.ReadonlyRootfs}}' $(docker ps -q)`
* S5 `stat -c '%a %U:%G %n' /srv/csfr/*/app.env /srv/csfr/*/db.env` (expect 600 or 640, owner `deploy`)
* S6 `docker inspect --format '{{.Name}} {{.HostConfig.LogConfig.Type}} {{.HostConfig.LogConfig.Config}}' $(docker ps -q)` (L2)
* S7 `grep -hE '^\s*(PasswordAuthentication|PermitRootLogin|KbdInteractiveAuthentication)' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf; systemctl is-active unattended-upgrades fail2ban`
* S8 (H1): `docker exec csfr-staging-web-1 python manage.py shell -c "from apps.accounts.models import User; print(User.objects.filter(email__iendswith='@e2e.example.com').count(), User.objects.filter(email__iendswith='@load.example.com').count())"` (prints two numbers; use the staging web container's name from S3 if it differs)
* S9 (H3), in the staging admin: which exam set is assigned to STG1, and does the Final have a maximum number of attempts?
* The firewall: `ufw status` needs root, so please read the firewall rules on hPanel's VPS page.
* Backblaze B2: check that the backup key is limited to the backup bucket with `writeFiles` (and list) only, no `deleteFiles`, and that the
  bucket has object lock. That is what architecture §17 promises.

**Dynamic tests on staging (each only after you approve it):**

* T1. Signed-out media: `GET /learn/media/<id>/` → sign-in redirect. **Done passively; passed.**
* T2. A second test learner tries to open the first learner's `/attempt/<id>/`, `/attempt/<id>/result/` and `/attempt/<id>/q/1/data/`:
  expect 404. (Needs two throwaway staging learners. The code and tests already show the owner filter, so this is confirmation only.)
* T3. A test mentor opens `/preview/exam/final/` and `/staff/questions/<a final-pool id>/`: expect 403. (Confirmation only.)
* T4 (M1). Five reset requests for made-up `@example.invalid` addresses, then compare the admin dashboard's "sent today" count before and
  after. Five, not 100: that proves the mechanism without draining the budget.
* T5 (M2). Two `/register/` POSTs with `batch=02` and `batch=002` and an invalid form (so no account is made), checking that neither gets
  the 429 a third request on `batch=2` would. Optional: the code already shows it.

My suggestion: only T4 is worth running. T2, T3 and T5 confirm what the code and the test suite already show.
