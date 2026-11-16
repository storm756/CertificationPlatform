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
   If that file already exists and cannot be overwritten (copied from a PC, another owner), the command writes
   `translation-import-report-<date>-<time>.csv` next to it (or in the system temp folder) and prints the path. **Nothing is lost
   and nothing needs deleting:** the report is written before `--apply`, and `--apply` is safe to run again. If an older run stopped at
   the report, just run the same command again.
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

### 1.4 The staging login (security audit 2026-11)

Staging holds the real course and exam sets, so the edge Caddy asks for one shared login on every staging page except
`/healthz/` (the uptime monitor still works). Prod is not affected. The user name and a bcrypt **hash** of the password live only
in `/srv/csfr/edge/.env` on the server; the password itself goes in the team's password manager. `deploy.sh edge` refuses to
install a Caddyfile while either value is missing, and the running Caddy keeps its old config.

```bash
# on the server, once (and again to change the password)
docker run --rm -it caddy:2 caddy hash-password       # type the password twice; prints a hash starting $2a$
nano /srv/csfr/edge/.env                               # add the two lines below (single quotes: the hash has $ signs)
#   STAGING_AUTH_USER=ccfr-team
#   STAGING_AUTH_HASH='$2a$14$...the hash...'
chmod 600 /srv/csfr/edge/.env
cd ~/csfr-repo && git pull && deploy/deploy.sh edge
curl -s -o /dev/null -w '%{http_code}
' https://staging.cyberfirstresponse.io/          # 401
curl -s https://staging.cyberfirstresponse.io/healthz/                                  # ok
curl -s -o /dev/null -w '%{http_code}
' https://cyberfirstresponse.io/                 # 200 (prod is open)
```

**Gotcha: the single quotes around the hash are required.** A bcrypt hash is full of `$` signs (`$2a$14$…`). `deploy/edge.sh`
reads `/srv/csfr/edge/.env` with `set -u`, so without quotes the shell reads `$2a`, `$14` … as variables and the deploy stops with
an "unbound variable" error (or, if it got past that, Caddy would get a mangled hash and every staging login would fail). Write the
line exactly as `STAGING_AUTH_HASH='$2a$14$...'`: single quotes, not double, no spaces around `=`. Check it without printing the
hash: `grep -cF "STAGING_AUTH_HASH='\$2a\$" /srv/csfr/edge/.env` must print `1` (`-F`: the `$` signs are plain text). If you change the password, run
`deploy/deploy.sh edge` again so Caddy reads the new hash.

The browser asks for the login once per session; links in staging emails work after it. The journeys and the load test pass
it with `E2E_HTTP_USER` / `E2E_HTTP_PASSWORD` and `LT_HTTP_USER` / `LT_HTTP_PASSWORD` (§8).

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
   age -d -i age-identity.txt csfr-prod-<stamp>.dump.age | ssh ccfr \
     'cd /srv/csfr/prod/src/deploy && CSFR_ENV=prod CSFR_ENV_FILE=/srv/csfr/prod/app.env CSFR_DB_ENV_FILE=/srv/csfr/prod/db.env \
      docker compose -f compose.yml exec -T db pg_restore -U csfr_owner -d csfr --no-owner --no-privileges --exit-on-error'
   age -d -i age-identity.txt media-prod-<stamp>.tar.age | ssh ccfr \
     'docker volume create csfr-prod_media >/dev/null; docker run --rm -i -v csfr-prod_media:/media alpine tar -C /media -xf -'
   ```
   Restoring as `csfr_owner` makes it the owner, and the default privileges give `csfr_app` its row access.
6. `deploy/deploy.sh prod <the tag that was live>`: builds, migrates (nothing to do), starts web and tasks.
7. Smoke test (section 1.3), check one learner's results and one certificate's verify page, tell the lead the data-loss window.

### 3.3 Restore one environment's database from a recent dump (no server loss)

Same as 3.2 steps 4–6 on the existing server, after `docker compose -f compose.yml stop web tasks` and with
`pg_restore … --clean --if-exists` instead of a fresh volume. Agree the data loss with the lead first.

### 3.4 Restore drill on the server, into a throwaway database (about 20 minutes)

A shorter check than 3.1: the newest prod dump is restored into a **temporary Postgres container on the VPS** that has no network
and touches neither staging nor prod, its row counts are compared with live prod, and it is deleted. The **age private key and the
B2 login stay on your PC**: the dump is decrypted on the PC and only the decrypted stream goes through `ssh` into the container, so
nothing readable is written to the server's disk except inside that container, which is deleted at the end. Nothing here prints a
secret. Write the start and end times down.

**On the PC, use Git Bash** (PowerShell corrupts binary data in a pipe). You need: Docker Desktop running, this repo up to date,
`ssh ccfr` working, the age identity file (from one of the two key holders), and the Backblaze login.

1. **Download the newest dump.** Sign in at `backblaze.com` → **B2 Cloud Storage → Buckets** → the backup bucket → **Browse
   Files** → `prod` → `db` → `hourly` → sort by date, click the newest `csfr-prod-<stamp>.dump.age` → **Download**. Note the
   `<stamp>` (UTC). Safe to repeat.
2. **Start the throwaway database on the server** (no network, no password, small limits so prod is not slowed):
   ```bash
   ssh ccfr 'df -h / | tail -1; docker run -d --name csfr-drill-db --network none --memory 1g --cpus 1 -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=csfr postgres:17 >/dev/null && for i in $(seq 1 60); do docker exec csfr-drill-db pg_isready -U postgres -d csfr >/dev/null 2>&1 && break; sleep 1; done; docker exec csfr-drill-db pg_isready -U postgres -d csfr'
   ```
   Success: the disk line shows well under 80% used, then `/var/run/postgresql:5432 - accepting connections`. If it says the name
   `csfr-drill-db` is already in use, an earlier drill was not cleaned up: do step 5 first, then this step again.
3. **Decrypt on the PC and restore into it** (replace the two paths; the key file is only mounted read-only into a local container):
   ```bash
   cd /d/CertificationPlatform && git pull
   docker build -q -t csfr-backup:restore deploy/backup
   export MSYS_NO_PATHCONV=1
   KEYDIR="$(cd /c/path/to/key-folder && pwd -W)"          # the folder that holds age-identity.txt
   DUMP=/c/Users/<you>/Downloads/csfr-prod-<stamp>.dump.age
   time (docker run --rm -i --user root --entrypoint age -v "$KEYDIR:/k:ro" csfr-backup:restore -d -i /k/age-identity.txt < "$DUMP" \
     | ssh ccfr 'docker exec -i csfr-drill-db pg_restore -U postgres -d csfr --no-owner --no-privileges --exit-on-error')
   ```
   Success: no output except the `time` lines. Any `pg_restore: error` means the drill **failed**: note the message, do step 5,
   and tell the lead. To run it again, do step 5 and start over from step 2 (restoring twice into the same database fails).
4. **Compare row counts** (read-only on prod):
   ```bash
   ssh ccfr bash -s <<'EOF'
   Q="SELECT 'tables', count(*) FROM information_schema.tables WHERE table_schema='public'
   UNION ALL SELECT 'migrations', count(*) FROM django_migrations
   UNION ALL SELECT 'users', count(*) FROM accounts_user
   UNION ALL SELECT 'enrolments', count(*) FROM batches_enrolment
   UNION ALL SELECT 'questions', count(*) FROM questions_question
   UNION ALL SELECT 'attempts', count(*) FROM assessments_attempt
   UNION ALL SELECT 'attempt items', count(*) FROM assessments_attemptitem
   UNION ALL SELECT 'certificates', count(*) FROM certificates_certificate"
   echo "== restored copy";        docker exec csfr-drill-db psql -U postgres -d csfr -tA -F ' | ' -c "$Q"
   echo "== live prod, read only"; docker exec csfr-prod-db-1 psql -U postgres -d csfr -tA -F ' | ' -c "$Q"
   EOF
   ```
   **Pass:** `tables` and `migrations` are the same in both (unless a deployment ran since the dump), every count in the copy is
   above 0 where prod's is, and none is higher than prod's. Prod may be a little higher: rows added since the dump's `<stamp>`.
   **And** the dump `<stamp>` is at most one hour before the time you started step 3. An older newest dump means the hourly
   backups have stopped: the drill fails, tell the lead. Safe to rerun.
5. **Delete the throwaway database** (and its data volume), then check it is gone:
   ```bash
   ssh ccfr 'docker rm -f -v csfr-drill-db; docker ps -a --filter name=csfr-drill --format "{{.Names}}"'
   ```
   Success: `csfr-drill-db` once (from `rm`), then nothing. Safe to rerun ("No such container" is fine). On the PC, delete the
   downloaded `.dump.age` file. Nothing decrypted was written to the PC's disk.
6. Record the date, who, the dump `<stamp>`, the step 3 time and the counts (numbers only, no names) in `docs/history/` and tick it
   in STATUS.md. The full drill with a server rebuild is still 3.1.

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
scp -r content-data ccfr:/srv/csfr/staging/      # from the PC
ssh ccfr 'chmod -R a+rX /srv/csfr/staging/content-data && mkdir -p /srv/csfr/staging/content-data/outputs'
```

The importers write their reports to `outputs/`, which must belong to the `app` user inside the container (uid 10001). The `deploy`
user has **no sudo**, so never use `sudo chown`. Use a one-off root container instead (helper exports from the top of this file;
use `/srv/csfr/prod/content-data` on prod. The compose file drops all Linux capabilities, so root needs `--cap-add` to change owners):

```bash
docker compose -f compose.yml run --rm --user root --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER -v /srv/csfr/staging/content-data:/app/content-data web \
  chown -R 10001 /app/content-data/outputs
```

`chmod 777` on `outputs/` also works but leaves it writable by everyone; prefer the `chown`. A report file copied from a PC keeps
its old owner and the importer cannot overwrite it: the importer now writes a timestamped report beside it instead of failing.

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
3. Open a test batch, register a test learner (staging mail is in Mailpit: `ssh -L 8025:127.0.0.1:8025 ccfr`, then
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

**The seed prints live credentials.** Every `e2e_seed` / `loadtest_seed` run gives its test accounts a new random password (and the
staff a new authenticator secret) and prints them only in its output. While the data exists, those accounts (including a superuser
for the journeys) can sign in to staging, which is on the public internet. So: keep the manifest private (`umask 077`, never commit
or paste it), run the clean command straight after, and delete the manifest from the server and your PC (security audit 2026-11).

### 8.1 The 16 browser journeys (`e2e/`)

```bash
# on the server
"${MANAGE[@]}" e2e_clean
MANAGE_T=("${MANAGE[@]:0:5}" -T "${MANAGE[@]:5}")   # the same helper without a terminal, so the JSON can be redirected
(umask 077; "${MANAGE_T[@]}" e2e_seed 2>/dev/null > /tmp/e2e-manifest.json)
# copy /tmp/e2e-manifest.json to e2e/manifest.json on your PC (scp), then, on your PC:
cd e2e && npm ci && npx playwright install chromium
E2E_HTTP_USER=ccfr-team E2E_HTTP_PASSWORD='<staging login>' BASE_URL=https://staging.cyberfirstresponse.io npx playwright test
# back on the server, remove everything the run added:
"${MANAGE[@]}" e2e_clean; rm -f /tmp/e2e-manifest.json   # and delete e2e/manifest.json on your PC
```

Journeys 2 and 3 read e-mails from Mailpit and are skipped unless `MAILPIT_URL` is set. **Staging sends no real mail:** every
staging e-mail lands in the staging stack's Mailpit (`deploy.sh staging` turns it on; nothing goes to Brevo). To run the two
journeys, open a tunnel in a second window, `ssh -N -L 8025:127.0.0.1:8025 ccfr`, and add `MAILPIT_URL=http://127.0.0.1:8025` to
the command above; the same address in a browser shows the mails. Or do the two by hand once (register, open the verification link
from Mailpit, and for a 16 or 17-year-old the guardian link). A failed journey leaves a screenshot and a
trace in `e2e/test-results/`. Record the result in `docs/history/`. Details: `e2e/README.md`.

### 8.2 The 60-learner load test (`loadtest/`)

```bash
# on the server
"${MANAGE[@]}" loadtest_seed --count 60     # prints {"password": ...}: a new random one each run
# on your PC (LT_PASSWORD=<that password>, LT_HTTP_USER / LT_HTTP_PASSWORD = the staging login, §1.4) (python -m venv .venv-load; pip install -r loadtest/requirements.txt), one network, all 60 at once:
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

### 9.1 Setting it up, click by click (once; about 45 minutes)

Three free accounts: **UptimeRobot** (is the site up), **Healthchecks.io** (did the jobs run) and **Sentry** (errors). Sign up
with a team address that reaches more than one person (e.g. `support@cyberfirstresponse.io`, forwarded by ImprovMX), not a personal
one, and keep the logins in the team's password manager. Every URL and key below is a secret: paste it only into the file named,
never into chat, git or a ticket.

**A. UptimeRobot: two monitors on `/healthz/`** (nothing goes on the server)

1. Go to `uptimerobot.com` → **Register for FREE** → confirm the e-mail → sign in.
2. **+ New monitor** → Monitor type **HTTP(s)** → Friendly name `CCFR prod` → URL `https://cyberfirstresponse.io/healthz/` →
   Monitoring interval **5 minutes** → under "How will we notify you?" tick the team e-mail → **Create monitor**.
3. Again: **+ New monitor** → HTTP(s) → `CCFR staging` → `https://staging.cyberfirstresponse.io/healthz/` → 5 minutes → the same
   e-mail → **Create monitor**. (`/healthz/` is the one staging path without the login, so no password is needed.)
4. Success: both monitors turn green ("Up") within 5 minutes.

**B. Healthchecks.io: seven heartbeat checks**

1. Go to `healthchecks.io` → **Sign Up** → confirm the e-mail → it creates a project; rename it `CCFR` (**Settings** → Project name).
2. **Integrations** → the e-mail integration is already there for your address; add the second team member's address with
   **Add Integration → Email** if you want two people alerted.
3. Make each check with **+ Add Check** → set **Name**, then **Change Schedule…** → **Simple** → **Period** and **Grace Time** as
   in the table → **Save**. Copy its **ping URL** (`https://hc-ping.com/<uuid>`) from the check's page.

   | Name | Period | Grace | Goes into |
   | --- | --- | --- | --- |
   | `prod tasks` | 10 minutes | 20 minutes | `TASKS_PING_URL=` in `/srv/csfr/prod/app.env` |
   | `prod db backup` | 1 hour | 30 minutes | `BACKUP_DB_PING_URL=` in `/srv/csfr/prod/app.env` |
   | `prod media backup` | 1 day | 2 hours | `BACKUP_MEDIA_PING_URL=` in `/srv/csfr/prod/app.env` |
   | `staging tasks` | 10 minutes | 20 minutes | `TASKS_PING_URL=` in `/srv/csfr/staging/app.env` |
   | `staging db backup` | 1 hour | 30 minutes | `BACKUP_DB_PING_URL=` in `/srv/csfr/staging/app.env` |
   | `staging media backup` | 1 day | 2 hours | `BACKUP_MEDIA_PING_URL=` in `/srv/csfr/staging/app.env` |
   | `server disk` | 15 minutes | 30 minutes | `DISK_PING_URL=` in `/srv/csfr/monitoring.env` |

4. Put the six app URLs on the server. For each environment: `ssh ccfr`, then `nano /srv/csfr/prod/app.env` (then the same for
   staging). Each of the three names already has an empty line (`TASKS_PING_URL=` …): paste the URL after the `=` on that line,
   don't add a second line. Save (Ctrl+O, Enter, Ctrl+X). Check without printing the URLs:
   `grep -c '^TASKS_PING_URL=https' /srv/csfr/prod/app.env` prints `1`; the same for `BACKUP_DB_PING_URL` and
   `BACKUP_MEDIA_PING_URL`. If a name prints `0` and the line is missing, add it.
5. Restart so the containers read the file (per environment; safe to rerun):
   ```bash
   cd /srv/csfr/prod/src/deploy
   export CSFR_ENV=prod CSFR_ENV_FILE=/srv/csfr/prod/app.env CSFR_DB_ENV_FILE=/srv/csfr/prod/db.env
   docker compose -f compose.yml up -d web tasks cron
   ```
   (For staging: `staging` in all four places.) Success: `docker compose -f compose.yml ps` shows web, tasks and cron "Up".
6. The disk check:
   ```bash
   nano /srv/csfr/monitoring.env          # one line: DISK_PING_URL=https://hc-ping.com/<uuid>
   chmod 600 /srv/csfr/monitoring.env
   bash /srv/csfr/edge/src/deploy/server/disk-check.sh; echo "exit $?"   # exit 0 = under 80%, and it pinged
   crontab -e                             # add the line below, save
   #   */15 * * * * bash /srv/csfr/edge/src/deploy/server/disk-check.sh >/dev/null 2>&1
   crontab -l | grep -c disk-check        # 1
   ```
7. Success: within the period each check turns green ("up") in Healthchecks.io. Tasks: within 10 minutes. DB backups: after the
   next `:07`. Media backups: after the next 02:30 UTC (08:00 IST). Disk: within 15 minutes. A check that stays grey ("new") never
   got a ping: recheck that environment's line in step 4 and restart (step 5).

**C. Sentry: one project per environment**

1. Go to `sentry.io` → **Sign up** (free "Developer" plan) → organisation name `ccfr`; choose the **EU** data region if offered.
2. **Projects → Create Project** → platform **Django** → alert frequency "Alert me on every new issue" → project name `ccfr-prod` →
   **Create Project**. Skip the install instructions (the code already has them); copy the **DSN** (`https://…@….ingest.sentry.io/…`,
   also under **Settings → Projects → ccfr-prod → Client Keys (DSN)**).
3. Repeat for `ccfr-staging`.
4. On the server, `nano /srv/csfr/prod/app.env`: paste the prod DSN after `SENTRY_DSN=` on its line (add the line if the file has
   none; never two) (staging: the staging DSN in the staging file). Check: `grep -c '^SENTRY_DSN=https' /srv/csfr/prod/app.env` prints `1`.
5. Restart web and tasks as in B5 (the same command is fine). Success: no error in `docker compose -f compose.yml logs --since 5m web`;
   the first real error will appear in Sentry under that project. Sentry receives no request bodies, cookies, user, e-mail addresses
   or one-time links (scrubbed, architecture §16).

**D. Afterwards**

* Tick launch-checklist item 6 in `docs/STATUS.md` (in a PR) and note the date.
* Keep an offline copy of each `app.env` / `db.env` and `monitoring.env` (section 4): the ping URLs and DSNs are now in them.

---

## 10. Pilot housekeeping (added after the first prod deploy)

### 10.1 The `app.env` shape: backups and email

Each setting appears **once** in `/srv/csfr/<env>/app.env`. A duplicated backup block stops the deploy at the backup upload (it did on
the first prod deploy, and that "stop if the backup fails" behaviour is on purpose). The block is exactly this, with the key, the
secret and the age public key from the password manager. `RCLONE_CONFIG_B2_TYPE` is the word `s3`, never a key:

```
BACKUP_ENV_NAME=prod                      # staging on staging
AGE_PUBLIC_KEY=age1...
BACKUP_REMOTE=b2:<bucket>/<env>           # e.g. b2:Certification-Platform/prod
RCLONE_CONFIG_B2_TYPE=s3
RCLONE_CONFIG_B2_PROVIDER=Other
RCLONE_CONFIG_B2_ENDPOINT=https://s3.us-west-004.backblazeb2.com
RCLONE_CONFIG_B2_ACCESS_KEY_ID=<write-only key id>
RCLONE_CONFIG_B2_SECRET_ACCESS_KEY=<write-only key>
```

Check without printing secrets: `grep -c '^RCLONE_CONFIG_B2_TYPE=' app.env` must print `1`, and `grep '^RCLONE_CONFIG_B2_TYPE=' app.env`
must show `s3`. Copy the whole block from the other environment when in doubt, then fix `BACKUP_ENV_NAME` and `BACKUP_REMOTE`.

Email lines: `DEFAULT_FROM_EMAIL=CCFR <no-reply@cyberfirstresponse.io>` (only the address is read; the sender name is always the programme
short name) and optionally `SUPPORT_EMAIL=...` (default `support@cyberfirstresponse.io`). `SITE_NAME` is no longer read: an old
line does no harm, and you can delete it. The subject prefix is `[CCFR]`.

### 10.2 Remove a test learner

For testing on prod with a Gmail plus-address (`me+test1@gmail.com`) in the OPEN batch. Registration accepts `+` addresses, but **prod
folds Gmail dots and `+tags` into one address** (`EMAIL_NORMALISE_ALIASES`), so only one `+` test account can exist at a time, and **none
if the plain Gmail address is already registered** (the lead's is, so the lead uses a different address for prod tests). Remove the test learner before making the next one. Mail still reaches your inbox.

```bash
# helper exports from the top of this file (prod: replace staging with prod), then:
"${MANAGE[@]}" remove_test_learner me+test1@gmail.com              # preview only: lists what would go
"${MANAGE[@]}" remove_test_learner me+test1@gmail.com --yes        # deletes
```

It works on **learners only** (a mentor or admin is refused). It deletes the account, profile, enrolment and attempts. If the learner
holds a certificate it refuses, because the admin cannot delete such a user either; add `--include-certificate` to delete the
certificate and its PDF too. **That leaves a gap in the serial numbers**: they come from one global sequence and are never reused or
renumbered, so a gap is permanent and the next certificate gets the next number. The command says this before it deletes. The audit
row records only IDs.

### 10.3 Put the signature images and the leadership photos on a server

Both are private (never in git) and live in the media volume. The lead connects with `ssh ccfr` (host, user `deploy` and key are in
`~/.ssh/config`); `deploy` has no sudo, so copy to a folder it owns, then move the files into the volume with a one-off root container.

**Signatures: staging only until the final design and the hi-res images exist.** Nothing in the app stops prod from using signature
files that are on it: a certificate picks up whatever `media/private/signatures/signature-1..3.png` holds at the moment it is issued
(each PDF is then fixed). The only protections are that auto-issue is off and a mentor must approve each certificate (and the warning
shown while signatures are missing or `CERTIFICATE_DESIGN_FINAL` is off). So **do not copy signatures to prod early**; put them there
together with the hi-res images and the final design.

Photos go to staging and prod once all three people have consented (they have, 14 Nov 2026). Photos are `.webp`, the signatures `.png`.

From the PC (PowerShell, in the repo folder):

```powershell
ssh ccfr "mkdir -p /srv/csfr/staging/incoming /srv/csfr/prod/incoming"
scp content-data\signatures\signature-1.png content-data\signatures\signature-2.png content-data\signatures\signature-3.png ccfr:/srv/csfr/staging/incoming/
scp content-data\people\bhavesh-patel.webp content-data\people\nilakshi-jain.webp content-data\people\vineet-kumar.webp ccfr:/srv/csfr/staging/incoming/
scp content-data\people\bhavesh-patel.webp content-data\people\nilakshi-jain.webp content-data\people\vineet-kumar.webp ccfr:/srv/csfr/prod/incoming/
```

Then on the server, once per environment (`ssh ccfr`, then `cd /srv/csfr/<env>/src/deploy` and the helper exports from the top of
this file). Staging (signatures and photos):

```bash
docker compose -f compose.yml run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER -v /srv/csfr/staging/incoming:/incoming:ro web sh -c '
  mkdir -p /app/media/private/signatures /app/media/private/people &&
  cp /incoming/signature-*.png /app/media/private/signatures/ &&
  cp /incoming/*.webp /app/media/private/people/ &&
  chown -R 10001 /app/media/private/signatures /app/media/private/people &&
  chmod 640 /app/media/private/signatures/* /app/media/private/people/* &&
  ls -l /app/media/private/signatures /app/media/private/people'
rm /srv/csfr/staging/incoming/*
```

Success: `ls` lists three `signature-N.png` and three `.webp` files owned by `10001`. Safe to rerun (it overwrites the same files).
Prod (**photos only, no signatures**), with the prod helper exports from `/srv/csfr/prod/src/deploy`:

```bash
docker compose -f compose.yml run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER -v /srv/csfr/prod/incoming:/incoming:ro web sh -c '
  mkdir -p /app/media/private/people &&
  cp /incoming/*.webp /app/media/private/people/ &&
  chown -R 10001 /app/media/private/people &&
  chmod 640 /app/media/private/people/* &&
  ls -l /app/media/private/people'
rm /srv/csfr/prod/incoming/*
```

Then for each environment that has photos, add these two lines to `/srv/csfr/<env>/app.env` (edit with `nano`; never print the file)
and restart:

```
PEOPLE_PHOTO_DIR=/app/media/private/people
PEOPLE_CONSENT_GIVEN=1
```

```bash
docker compose -f compose.yml up -d web tasks
```

Success: the home page shows the three photos under "Who runs it" (`/people/bhavesh-patel/` returns an image). Remove the two lines
and restart to switch the section back to the placeholder. `CERTIFICATE_DESIGN_FINAL` is not touched: the final design is still pending.
