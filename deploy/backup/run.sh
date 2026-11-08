#!/bin/bash
# Tiny scheduler (no cron daemon needed, so the container can stay non-root and read-only).
#   hourly at :07 UTC  -> db-backup.sh
#   daily  at 02:30 UTC -> media-backup.sh
set -u

last_db=""
last_media=""
echo "backup scheduler started ($(date -u +%FT%TZ)), env=${BACKUP_ENV_NAME:-unknown}"

while true; do
  hour_key="$(date -u +%Y%m%d%H)"
  minute="$(date -u +%M)"
  day_key="$(date -u +%Y%m%d)"
  if [ "$minute" -ge 7 ] && [ "$last_db" != "$hour_key" ]; then
    last_db="$hour_key"
    db-backup.sh || echo "DB BACKUP FAILED at $(date -u +%FT%TZ)" >&2
  fi
  if [ "$(date -u +%H%M)" -ge 0230 ] && [ "$last_media" != "$day_key" ]; then
    last_media="$day_key"
    media-backup.sh || echo "MEDIA BACKUP FAILED at $(date -u +%FT%TZ)" >&2
  fi
  sleep 30
done
