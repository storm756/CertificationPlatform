#!/bin/bash
# One encrypted pg_dump, kept locally for 48 h and uploaded off-site.
# Off-site layout (retention is enforced by B2 lifecycle + object-lock rules, see docs/server-setup.md):
#   hourly/  every run      daily/  the 00:xx UTC run      weekly/  the Sunday 00:xx UTC run
# Needs: DB_HOST DB_NAME DB_USER DB_PASSWORD AGE_PUBLIC_KEY BACKUP_ENV_NAME; optional BACKUP_REMOTE (+ RCLONE_CONFIG_* env).
set -euo pipefail

: "${AGE_PUBLIC_KEY:?AGE_PUBLIC_KEY is required}"
: "${BACKUP_ENV_NAME:?}"
export PGPASSWORD="${DB_PASSWORD:?}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="csfr-${BACKUP_ENV_NAME}-${stamp}.dump.age"
out="/backups/${name}"

# Never leaves plaintext on disk: dump is piped straight into age.
pg_dump -h "${DB_HOST:-db}" -U "${DB_USER}" -d "${DB_NAME:-csfr}" -Fc --no-owner \
  | age -r "$AGE_PUBLIC_KEY" -o "${out}.tmp"
mv "${out}.tmp" "$out"
echo "wrote ${out} ($(stat -c %s "$out") bytes)"

if [ -n "${BACKUP_REMOTE:-}" ]; then
  # --s3-no-head / --no-check-dest / --s3-no-check-bucket: the B2 key is write-only, so rclone must not read, list or create buckets.
  up() { rclone copyto --s3-no-head --no-check-dest --s3-no-check-bucket "$out" "${BACKUP_REMOTE}/db/$1/${name}"; }
  up hourly
  if [ "$(date -u +%H)" = "00" ]; then
    up daily
    if [ "$(date -u +%u)" = "7" ]; then up weekly; fi
  fi
  echo "uploaded to ${BACKUP_REMOTE}"
else
  echo "WARNING: BACKUP_REMOTE not set, backup is local only" >&2
fi

# Local copies: 48 hours only (the off-site copies are the real archive).
find /backups -name 'csfr-*.dump.age' -mmin +2880 -delete
touch /backups/.last_ok_db
