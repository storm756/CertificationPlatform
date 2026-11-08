#!/bin/bash
# Nightly: tar + age-encrypt the media volume and upload it off-site (write-only key, so a full
# encrypted archive each night rather than a sync, which would need list/delete rights).
set -euo pipefail

: "${AGE_PUBLIC_KEY:?AGE_PUBLIC_KEY is required}"
: "${BACKUP_ENV_NAME:?}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="media-${BACKUP_ENV_NAME}-${stamp}.tar.age"
out="/backups/${name}"

tar -C /media -cf - . | age -r "$AGE_PUBLIC_KEY" -o "${out}.tmp"
mv "${out}.tmp" "$out"
echo "wrote ${out} ($(stat -c %s "$out") bytes)"

if [ -n "${BACKUP_REMOTE:-}" ]; then
  rclone copyto --s3-no-head --no-check-dest --s3-no-check-bucket "$out" "${BACKUP_REMOTE}/media/daily/${name}"
  echo "uploaded to ${BACKUP_REMOTE}"
fi

find /backups -name 'media-*.tar.age' -mmin +4320 -delete
touch /backups/.last_ok_media
