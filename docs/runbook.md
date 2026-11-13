# Operations runbook

For the **people** who run the servers (D29: Claude never deploys, never runs `ssh` and never merges).
Stage 10. The server set-up from scratch is in [`server-setup.md`](server-setup.md); this file covers day-to-day
operations and emergencies.

**Layout on the VPS** (user `deploy`):

| Path | What |
| --- | --- |
| `/srv/csfr/edge/` | The shared Caddy (front door for both sites): `src/` (checkout, `main`), `caddy/Caddyfile`, `caddy/Caddyfile.prev`, `compose.edge.yml`, optional `.env` |
| `/srv/csfr/staging/`, `/srv/csfr/prod/` | One app stack each: `src/` (checkout), `app.env`, `db.env` (secrets, `chmod 600`, never in git) |
| `/srv/csfr/<env>/content-data/` | Private course inputs while loading the course (section 7). Delete afterwards. |
| `/srv/csfr/monitoring.env` | `DISK_PING_URL` for the disk check (section 9) |
| `~/csfr-repo` | A clone of the repository, only to have `deploy/deploy.sh` at hand |

Helper used below, from the env's checkout (replace `staging` with `prod` where needed):

```bash
cd /srv/csfr/staging/src/deploy
export CSFR_ENV=staging CSFR_ENV_FILE=/srv/csfr/staging/app.env CSFR_DB_ENV_FILE=/srv/csfr/staging/db.env
OWNER_PW="$(grep '^DB_OWNER_PASSWORD=' "$CSFR_DB_ENV_FILE" | cut -d= -f2-)"
MANAGE=(docker compose -f compose.yml run --rm -e DB_USER=csfr_owner -e "DB_PASSWORD=$OWNER_PW" web python manage.py)
```

---

## 1. Deploy

Order for a release: **edge (only if the Caddyfile changed) → staging → check → prod.**

```bash
cd ~/csfr-repo && git pull
deploy/deploy.sh edge            # the shared Caddy, from main (validate -> install -> reload)
deploy/deploy.sh staging         # pull -> build -> migrate -> collectstatic -> restart web + tasks
# check https://staging.cyberfirstresponse.io (section 1.3), then:
deploy/deploy.sh prod            # same, plus an encrypted DB dump first
```

* `deploy.sh staging|prod [ref]` **never touches Caddy** any more. It prints a warning if the edge Caddy is not running.
* `deploy.sh edge [ref]` (default `main`) installs `deploy/caddy/Caddyfile` and `deploy/compose.edge.yml` from that ref into
  `/srv/csfr/edge/`. It validates the new file in a throwaway Caddy first: an invalid file is never installed and the running
  config stays. If the reload fails it puts `Caddyfile.prev` back. Run it whenever a PR changes `deploy/caddy/` or
  `deploy/compose.edge.yml` (the PR description says so).
* Deploy a tag or commit: `deploy/deploy.sh prod v1.3.0`. Tag prod releases: `git tag v1.3.0 <sha> && git push origin v1.3.0`.

### 1.1 One-time move of the edge Caddy (Stage 10)

Before Stage 10, the running Caddy (`csfr-edge`) was started from whichever env checkout deployed last. Move it once:

```bash
cd ~/csfr-repo && git pull                # main with Stage 10 merged
deploy/deploy.sh edge                     # creates /srv/csfr/edge, validates, starts csfr-edge from there, reloads
docker inspect csfr-edge-caddy-1 --format '{{range .Mounts}}{{.Source}} {{end}}' | tr ' ' '\n' | grep caddy
# expect /srv/csfr/edge/caddy ; the caddy-data volume (TLS certificates) is kept, same project name
curl -sI https://cyberfirstresponse.io/healthz/ | head -1 ; curl -sI https://staging.cyberfirstresponse.io/healthz/ | head -1
```

The container is recreated once (a few seconds without the sites). Do it at a quiet time. Production still answers 502 before launch;
that is expected.

### 1.2 Stage 8 (multilingual) deploy steps, once per environment

1. Deploy as above (the image is rebuilt by `deploy.sh`; the `.mo` catalogues are committed, nothing to compile).
2. Give reviewers their permission: **Admin → Users → (person) → User permissions**: "Reviewer: Hindi", "Reviewer: Marathi" or
   "Reviewer: Gujarati"; translators get "Translator: upload translation sheets". A reviewer never reviews their own upload.
3. Import the draft course translations (needs the private inputs on the server, section 7.1):
   `"${MANAGE[@]}" import_draft_translations` (preview), then `"${MANAGE[@]}" import_draft_translations --apply`, with the
   `-v /srv/csfr/<env>/content-data:/app/content-data` mount from section 7.2. Lines it could not match go to
   `content-data/outputs/translation-import-report.csv` (private).
4. Rosetta edits on a server are lost at the next deploy: download the catalogue from Rosetta and commit it in a PR.

### 1.3 Smoke test after every deploy

| Check | Expected |
| --- | --- |
| `/healthz/` | 200 |
| `/` (landing), `/register/`, `/verify/` | 200 |
| `/learn/` signed out | redirect to sign-in |
| Sign in as a test learner, open a film and a practice check | plays / answers |
| `curl -sI https://<site>/ \| grep -i content-security-policy` | `default-src 'self'; script-src 'self'; …` |
| Browser DevTools console on a lesson and an assessment | no "Content Security Policy" errors |

---

## 2. Roll back

1. Redeploy the previous tag: `deploy/deploy.sh prod v1.2.0` (staging the same way). Migrations stay backward-compatible for one
   release (architecture §17), so the previous code runs on the migrated database.
2. If a migration must be reversed, **stop and ask the lead**: restore from the pre-deploy dump (section 3.3) only after
   agreeing what data since the deploy will be lost.
3. Caddy: `deploy/deploy.sh edge <previous-ref>`, or by hand
   `cp /srv/csfr/edge/caddy/Caddyfile.prev /srv/csfr/edge/caddy/Caddyfile` then
   `docker compose --project-directory /srv/csfr/edge -f /srv/csfr/edge/compose.edge.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile --force`.

---

## 3. Backups and restore

Backups (server-setup §4): an age-encrypted `pg_dump` every hour at :07 UTC, media nightly at 02:30 UTC, uploaded to B2 with a
**write-only** key and Object Lock. The **age private key is offline with two named people**. Downloading needs a **read** key,
also held by people, never on the server. Targets (architecture §18, journey 17): **back within 2 hours, losing at most 1 hour.**

### 3.1 Restore drill (timed, before launch and every term)

Never on staging or prod: on a laptop with Docker and a checkout of `main` (Git Bash on Windows works). Write the times down.

| Step | Command / action | Start | End |
| --- | --- | --- | --- |
| T0 | Start the clock. Pick "the server was lost now". | | |
| 1 | Download the newest `db/hourly/csfr-prod-*.dump.age` and the newest `media/daily/media-prod-*.tar.age` from B2 (read key) | | |
| 2 | `deploy/restore.sh --identity /path/to/age-identity.txt --keep <dump file>` → expect `RESTORE OK` and the table / user counts | | |
| 3 | Media: `age -d -i /path/to/age-identity.txt <media file> \| tar -tvf - \| tail` → the films, handouts and `private/` files are listed | | |
| 4 | Full app check (stop any other local stack on port 8000 first): `docker compose -p csfr-drill -f deploy/compose.dev.yml up -d --wait db`, then `age -d -i <key> <dump> \| docker compose -p csfr-drill -f deploy/compose.dev.yml exec -T db pg_restore -U postgres -d csfr --no-owner --no-privileges --exit-on-error`, then `docker compose -p csfr-drill -f deploy/compose.dev.yml up -d web`. Sign in at http://localhost:8000 as a real admin (2FA from the authenticator app), open a batch, one learner's results and **Admin → Certificates**. Don't extract the media into the checkout's `media/` folder: a local course database may use it. | | |
| 5 | Note the dump's timestamp: data lost = T0 − dump time (must be ≤ 1 hour) | | |
| End | Total time from T0 (must be ≤ 2 hours for the real thing, which also needs a new VPS: section 3.2) | | |
| Clean up | `docker rm -f` the kept restore container (its command is printed), `docker compose -p csfr-drill -f deploy/compose.dev.yml down -v` (**only the `csfr-drill` project**), delete the downloaded files and the extracted media | | |

Record the result in `docs/history/` (date, who, times, problems) and in STATUS.md. The drill **passes** when step 2 says
`RESTORE OK`, step 4 shows real data, data loss ≤ 1 hour and the total fits in 2 hours with a server rebuild (section 3.2 times).

### 3.2 Real restore after losing the server

1. New VPS: `server-setup.md` §1 (harden), DNS A records to the new IP if it changed.
2. Recreate `/srv/csfr/<env>/app.env` and `db.env` from the **offline copy of the secrets** (section 4 says who holds it).
3. `deploy/deploy.sh edge`.
4. Start only the database (fresh volume; `init-roles.sh` creates the two roles):
   ```bash
   git clone https://github.com/storm756/CertificationPlatform.git /srv/csfr/prod/src
   git -C /srv/csfr/prod/src checkout <the tag that was live>
   cd /srv/csfr/prod/src/deploy
   docker network create csfr-edge 2>/dev/null || true   # deploy.sh edge made it already
   export CSFR_ENV=prod CSFR_ENV_FILE=/srv/csfr/prod/app.env CSFR_DB_ENV_FILE=/srv/csfr/prod/db.env
   docker compose -f compose.yml up -d --wait db
   ```
5. Restore from the key holder's laptop, so the private key and the plaintext never touch the server's disk:
   ```bash
   age -d -i age-identity.txt csfr-prod-<stamp>.dump.age | ssh deploy@<server> \
     'cd /srv/csfr/prod/src/deploy && CSFR_ENV=prod CSFR_ENV_FILE=/srv/csfr/prod/app.env CSFR_DB_ENV_FILE=/srv/csfr/prod/db.env \
      docker compose -f compose.yml exec -T db pg_restore -U csfr_owner -d csfr --no-owner --no-privileges --exit-on-error'
   age -d -i age-identity.txt media-prod-<stamp>.tar.age | ssh deploy@<server> \
     'docker volume create csfr-prod_media >/dev/null; docker run --rm -i -v csfr-prod_media:/media alpine tar -C /media -xf -'
   ```
   Restoring as `csfr_owner` makes it the owner, and the default privileges give `csfr_app` its row access.
6. `deploy/deploy.sh prod <the tag that was live>`: builds, migrates (nothing to do), starts web and tasks.
7. Smoke test (section 1.3), check one learner's results and one certificate's verify page, tell the lead the data-loss window.

### 3.3 Restore one environment's database from a recent dump (no server loss)

Same as 3.2 steps 4–6 on the existing server, after `docker compose -f compose.yml stop web tasks` and with
`pg_restore … --clean --if-exists` instead of a fresh volume. Agree the data loss with the lead first.

---

## 4. Rotate secrets

Secrets live only in `/srv/csfr/<env>/app.env` and `db.env` (and an **offline copy** kept by the lead and one other named person;
update it after every rotation). Staging and prod never share a secret. After editing a file:
`docker compose -f compose.yml up -d` from the env's `src/deploy` (with the helper exports) recreates the containers with it.

| Secret | How | Effect |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | New value (`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`), restart | Everyone is signed out; open password-reset and guardian links stop working (people request new ones) |
| `DB_APP_PASSWORD` / `DB_PASSWORD` | `docker compose -f compose.yml exec db psql -U postgres -d csfr -c "ALTER ROLE csfr_app PASSWORD '<new>'"`; put the same value in `db.env` (`DB_APP_PASSWORD`) and `app.env` (`DB_PASSWORD`); restart | Short blip while web restarts |
| `DB_OWNER_PASSWORD` | `ALTER ROLE csfr_owner PASSWORD '<new>'` the same way; update `db.env` | Used only by deploys |
| `POSTGRES_PASSWORD` | `ALTER ROLE postgres PASSWORD '<new>'`; update `db.env` | None |
| Brevo SMTP key (`EMAIL_HOST_PASSWORD`) | Create a new key in Brevo, update `app.env`, restart, send a test reset, delete the old key | None |
| B2 write-only key (`RCLONE_CONFIG_B2_*`) | New application key (write-only, bucket-scoped), update `app.env`, restart `cron`, wait for the next :07 backup, delete the old key | None |
| Backup encryption (`AGE_PUBLIC_KEY`) | Two key holders make a new pair offline (`age-keygen`), put the public key in `app.env`, restart `cron` | **Keep the old private key** until the last backup made with it has expired (8 weeks) |
| `SENTRY_DSN`, ping URLs | New values from the services, restart | None |
| Deploy SSH key | Add the new public key to `~deploy/.ssh/authorized_keys`, test, remove the old one | None |
| A staff member's 2FA | Admin → MFA → Authenticators → delete theirs; they must set up TOTP again at their next sign-in | They can't reach staff pages until done |

Rotate everything in the table **at once after any suspected leak**, and whenever someone with server access leaves the team.

---

## 5. Incident (personal data breach, DPDP)

The Digital Personal Data Protection Act requires telling the **Data Protection Board of India** and **each affected person**
without delay, with a **detailed report to the Board within 72 hours** of becoming aware. CyberPeace legal and the named
grievance officer own the notices; check the current DPDP Rules wording with them.

| When | Who | What |
| --- | --- | --- |
| Hour 0 | Whoever notices | Tell the lead and the grievance officer at once. Write down the time you became aware. |
| 0–2 h | Lead + a person with server access | Contain: rotate the affected secrets (section 4), block the access path, put the site in maintenance if needed (`docker compose -f compose.yml stop web` → Caddy shows 502). **Keep evidence:** copy logs (`docker compose logs --no-color > incident-<date>.log`), the audit table and the last backups before changing anything else. |
| 2–24 h | Lead + Claude (in a PR) | Find the cause and scope: which people, which fields (registration data, results, certificates), which dates. `AuditEvent` rows (`apps.audit`) and Sentry help. |
| ≤ 72 h | Grievance officer + CyberPeace legal | Notice to the Board (nature, extent, timing, likely impact, measures taken) and to each affected person in plain language (what happened, what it means for them, what they should do, whom to contact). Guardians for learners under 18. |
| After | Lead | A short write-up in `docs/history/`, fixes in a PR, then a restore drill if backups were involved. |

Also an incident (but not a breach) when no personal data was exposed: the site is down, a wrong certificate was issued, a backup
failed for a day. Use the same first two rows.

---

## 6. Add (or remove) an admin or mentor

**Admin** (full access): from the env's helper,

```bash
"${MANAGE[@]}" createsuperuser       # asks for the email and password; makes role=admin, is_staff, is_superuser
```

**Mentor**: an admin creates the user in **Admin → Users** with role *Mentor* (a verified email address under
*Email addresses*), then adds them to their batches (**Admin → Batches → Batch mentors**). Mentors see only their own batches.

Every admin and mentor must set up TOTP 2FA at their first sign-in (they are sent to the set-up page until they do), and their
session lasts 12 hours. **Remove** someone: untick *Active* on their user (keeps the audit trail); never delete staff users.

---

## 7. Load the course onto a server (staging first)

A merge copies **code** only. The course (lessons, 509 questions with hints, 18 graded parts, practice checks, films, handouts)
is loaded from private inputs that are never in git (D22). Do it on **staging** first; prod only after the lead approves.

### 7.1 Copy the private inputs

From the lead's PC (the private shared drive has them), copy into `/srv/csfr/<env>/content-data/` with the same paths as
`content-data/` locally:

| Path | Used by |
| --- | --- |
| `legacy/lessons/` (`booklet_text.json`, `modules.php`, `modules_ext.json`, `videos/…`) | `import_legacy_lessons` |
| `legacy/bank_booklet.json` | `import_legacy_mcq` |
| `legacy/interactive.json` | `import_legacy_interactive` |
| `ccfr-release/approved-hints.json` and `question-edits.json` | `publish_ccfr_course` |
| `film-source/module-<N>-*.mp4` (one per module) | `publish_ccfr_course --films` |
| `translations/…`, `prototype/data/i18n/`, `ccfr-release/ccfr-table-translations.draft.json`, the hint workbook | `import_draft_translations` (section 1.2) |
| The final-exam workbook (Sets B and D) | `import_final_sets` |

```bash
scp -r content-data deploy@<server>:/srv/csfr/staging/      # from the PC
ssh deploy@<server> 'chmod -R a+rX /srv/csfr/staging/content-data && mkdir -p /srv/csfr/staging/content-data/outputs && sudo chown 10001 /srv/csfr/staging/content-data/outputs'
```

(10001 is the `app` user inside the container; the importers write their reports to `outputs/`.)

### 7.2 Run the loaders, in this order, preview before apply

```bash
# helper exports from the top of this file, then:
LOAD=(docker compose -f compose.yml run --rm -v /srv/csfr/staging/content-data:/app/content-data web python manage.py)
"${LOAD[@]}" import_legacy_lessons --source content-data/legacy/lessons   # modules: 9, reading_topics: 55, created: 82
"${LOAD[@]}" import_legacy_mcq                                           # per-module lines, "405 … have no hint"
"${LOAD[@]}" import_legacy_interactive                                   # "By pool: module_quiz 80, practice 24"
"${LOAD[@]}" publish_ccfr_course                                         # preview: "Verified without saving: 20 corrected tables, 509 questions, 18 graded parts, …"
"${LOAD[@]}" publish_ccfr_course --apply                                 # "Published: …"
"${LOAD[@]}" import_final_sets --source content-data/<final-exam workbook>.xlsx            # preview
"${LOAD[@]}" import_final_sets --source content-data/<final-exam workbook>.xlsx --apply
"${LOAD[@]}" import_draft_translations && "${LOAD[@]}" import_draft_translations --apply  # Stage 8 drafts
```

Every importer also takes `--dry-run`. If a preview fails, stop and send the output to the lead (never the private files).
The films and handouts are stored in the env's media volume; `publish_ccfr_course --apply` can be run again safely.

### 7.3 Then

1. Create an admin with 2FA (section 6).
2. **Admin → Exam sets → Check → Release** each set (released papers are fixed, D31), then pick the set on each batch.
3. Open a test batch, register a test learner (staging mail is in Mailpit: `ssh -L 8025:127.0.0.1:8025 deploy@<server>`, then
   http://localhost:8025), and check: `/learn/m4/t3/` (a corrected table), `/learn/m8/film/` (plays, English and Hindi captions),
   `/learn/m8/handout/` (PDF), Module 8 Part A and Part B (start, save, submit).
4. Delete the inputs: `rm -rf /srv/csfr/staging/content-data` (keep the `outputs/` report if the team needs it, off the server).

---

## 8. Automated checks against staging (Stage 10b)

Run by a person, after the course is loaded (§7), the exam sets are released and the smoke test (§1.3) passes. Nobody else should be using
staging: journey 15 changes the module 1 mark split for a few seconds and puts it back, and the load test uses the whole server.
Both use invented accounts that the app adds and removes (`e2e_seed`, `e2e_clean`, `loadtest_seed`); they refuse to run on prod.
Use the `MANAGE` helper from the top of this file (it runs as the database owner, which `e2e_clean` needs to remove the released
test exam set).

### 8.1 The 16 browser journeys (`e2e/`)

```bash
# on the server
"${MANAGE[@]}" e2e_clean
MANAGE_T=("${MANAGE[@]:0:5}" -T "${MANAGE[@]:5}")   # the same helper without a terminal, so the JSON can be redirected
"${MANAGE_T[@]}" e2e_seed 2>/dev/null > /tmp/e2e-manifest.json
# copy /tmp/e2e-manifest.json to e2e/manifest.json on your PC (scp), then, on your PC:
cd e2e && npm ci && npx playwright install chromium
BASE_URL=https://staging.cyberfirstresponse.io npx playwright test
# back on the server, remove everything the run added:
"${MANAGE[@]}" e2e_clean
```

Journeys 2 and 3 read e-mails from Mailpit and are skipped on staging (real mail is sent): do those two by hand once (register, open
the verification link, and for a 16 or 17-year-old the guardian link), or set `MAILPIT_URL`. A failed journey leaves a screenshot and a
trace in `e2e/test-results/`. Record the result in `docs/history/`. Details: `e2e/README.md`.

### 8.2 The 60-learner load test (`loadtest/`)

```bash
# on the server
"${MANAGE[@]}" loadtest_seed --count 60
# on your PC (python -m venv .venv-load; pip install -r loadtest/requirements.txt), one network, all 60 at once:
locust -f loadtest/locustfile.py --headless --host https://staging.cyberfirstresponse.io -u 60 -r 60 --run-time 20m --csv loadtest/results
# back on the server:
"${MANAGE[@]}" loadtest_seed --clean; "${MANAGE[@]}" e2e_clean
```

Pass: the last line says `VERDICT: PASS` (p95 of the exam requests under 1 s, no failures). Watch `docker stats` on the server while it
runs. If it fails, do not raise the line: send the numbers back for a fix PR. Details: `loadtest/README.md`.

---

## 9. Monitoring

| What | Set up by a person | Where the value goes |
| --- | --- | --- |
| **Uptime pinger** (every 5 minutes) | A monitor on `https://cyberfirstresponse.io/healthz/` and `https://staging.cyberfirstresponse.io/healthz/` in an uptime service (e.g. UptimeRobot or Better Stack), alerting the lead by email | The service only |
| **Sentry** (errors, scrubbed: no request bodies, cookies, user, local variables or email addresses) | A Sentry project per environment | `SENTRY_DSN=` in `/srv/csfr/<env>/app.env`, then restart web and tasks. Empty = off. Sentry is listed as a processor in the privacy notice. |
| **Heartbeats** | Checks in a heartbeat service (e.g. Healthchecks.io): tasks loop (period 10 min, grace 20 min), DB backup (1 h, grace 30 min), media backup (1 day, grace 2 h), disk (15 min, grace 30 min) | `TASKS_PING_URL`, `BACKUP_DB_PING_URL`, `BACKUP_MEDIA_PING_URL` in `app.env`; `DISK_PING_URL` in `/srv/csfr/monitoring.env` |
| **Disk alert at 80%** | `crontab -e` as `deploy`: `*/15 * * * * /srv/csfr/edge/src/deploy/server/disk-check.sh` | Pings `<url>/fail` at ≥ 80% (`DISK_ALERT_PERCENT` to change) |
| **Email budget** | Built in: admins get one email a day when 150 emails were sent (architecture 7.2) | — |

A ping sends nothing but a GET to the secret URL; no personal data. A failed run pings `<url>/fail`, a dead service sends nothing,
and the heartbeat service alerts in both cases.
