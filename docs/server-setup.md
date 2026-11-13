# Server setup runbook (Stage 0)

VPS: Hostinger KVM 2, Ubuntu 24.04, `189.72.144.197` (`srv2130801.hstgr.cloud`).

## 0. What the lead must provide

| Need | Used for |
| --- | --- |
| SSH access as root for the first run (key or the Hostinger console) | `deploy/server/bootstrap.sh` |
| The public key of the machine that will deploy (`ssh-ed25519 ...`) | becomes the `deploy` user's only login |
| DNS A records at Hostinger: `cyberfirstresponse.io`, `www`, `staging` -> `189.72.144.197` (the apex currently points to 2.57.91.91) | Caddy gets Let's Encrypt certificates once these resolve |
| Backblaze B2 bucket **with Object Lock enabled**, plus a **write-only** application key (writeFiles only, no list/read/delete) | off-site backups |
| An `age` key pair. Generate on a trusted offline machine: `age-keygen -o age-identity.txt`. Send only the **public** key (`age1...`). The private file is held offline by two named people. | backup encryption |
| Brevo SMTP login (prod only) | verification and reset emails |
| Sentry DSN (optional) | error reporting |

## 1. Harden the server (once)

```bash
ssh root@189.72.144.197
curl -fsSL https://raw.githubusercontent.com/storm756/CertificationPlatform/main/deploy/server/bootstrap.sh -o bootstrap.sh
less bootstrap.sh    # read it first
DEPLOY_SSH_PUBKEY="ssh-ed25519 AAAA... you@laptop" bash bootstrap.sh
```

Keep that session open. From your laptop: `ssh deploy@189.72.144.197` must work and `ssh root@189.72.144.197` must be refused.

## 2. Create the env files (once per environment)

As `deploy`, for `staging` then `prod` (different secrets in each):

```bash
mkdir -p /srv/csfr/staging && cd /srv/csfr/staging
# copy deploy/env.staging.example -> app.env and deploy/env.db.example -> db.env, then edit both
chmod 600 app.env db.env
```

`DB_PASSWORD` in `app.env` must equal `DB_APP_PASSWORD` in `db.env`. The two Postgres roles (`csfr_owner` for migrations, `csfr_app` at runtime) are created the first time the db container starts.

## 3. Deploy

```bash
git clone https://github.com/storm756/CertificationPlatform.git ~/csfr-repo   # only to get deploy.sh
~/csfr-repo/deploy/deploy.sh edge              # the shared Caddy, from main, in /srv/csfr/edge (Stage 10)
~/csfr-repo/deploy/deploy.sh staging           # then check https://staging.cyberfirstresponse.io
~/csfr-repo/deploy/deploy.sh prod              # takes a DB dump first
```

The script clones its own checkout into `/srv/csfr/<env>/src`. `deploy.sh prod v1.2.0` deploys a tag (rollback = deploy the previous tag). `deploy.sh staging|prod` never touches Caddy; `deploy.sh edge` does. Day-to-day operations (deploy, roll back, restore, secrets, incidents, admins, loading the course, monitoring) are in [`runbook.md`](runbook.md).

First admin: `docker compose -p csfr-staging ... run --rm web python manage.py createsuperuser`, i.e. from `/srv/csfr/staging/src/deploy`:

```bash
export CSFR_ENV=staging CSFR_ENV_FILE=/srv/csfr/staging/app.env CSFR_DB_ENV_FILE=/srv/csfr/staging/db.env
docker compose run --rm -e DB_USER=csfr_owner -e DB_PASSWORD=<owner pw> web python manage.py createsuperuser
```

The admin is forced to set up TOTP on first login. Staging mail is caught by Mailpit: `ssh -L 8025:127.0.0.1:8025 deploy@189.72.144.197`, then open http://localhost:8025.

## 4. Backups

The `cron` container writes an age-encrypted `pg_dump` every hour (at :07 UTC) and a media archive nightly (02:30 UTC), and uploads them with `rclone` to `$BACKUP_REMOTE` under:

| Prefix | Written | Suggested B2 lifecycle (delete after) |
| --- | --- | --- |
| `db/hourly/` | every hour | 2 days |
| `db/daily/` | 00:xx UTC | 14 days |
| `db/weekly/` | Sunday 00:xx UTC | 56 days |
| `media/daily/` | nightly | 14 days |

Set the bucket's default Object Lock retention to a value not longer than the shortest lifecycle (e.g. 2 days) so nothing can be deleted early by a compromised server but old files still expire. The server's key is write-only, so it cannot list, read or delete anything.

Restore drill (on any machine with Docker, never on staging/prod): download a `*.dump.age` file from B2 with a read-capable key, then:

```bash
deploy/restore.sh --identity /path/to/age-identity.txt csfr-prod-20261108T120700Z.dump.age
```

It decrypts into a throwaway Postgres, restores, prints table/user counts and removes itself.

## 5. Stage 0 "Done when" status

See the PR description. Items that need the server, DNS or accounts above are checked there with how they were (or were not) verified.
