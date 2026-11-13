#!/bin/bash
# Tiny scheduler (no cron daemon needed, so the container can stay non-root and read-only).
#   hourly at :07 UTC  -> db-backup.sh
#   daily  at 02:30 UTC -> media-backup.sh
# After each run it pings a heartbeat URL if one is set (BACKUP_DB_PING_URL, BACKUP_MEDIA_PING_URL in
# app.env): the URL on success, "<url>/fail" on failure. A missing ping alerts a person. Off when unset.
set -u

last_db=""
last_media=""
echo "backup scheduler started ($(date -u +%FT%TZ)), env=${BACKUP_ENV_NAME:-unknown}"

ping() { # ping <url> <ok|fail>
  [ -n "$1" ] || return 0
  local url="${1%/}"
  [ "$2" = "fail" ] && url="$url/fail"
  curl -fsS -m 10 --retry 3 -o /dev/null "$url" || echo "heartbeat ping failed" >&2
}

run() { # run <script> <ping-url> <label>
  if "$1"; then
    ping "$2" ok
  else
    echo "$3 BACKUP FAILED at $(date -u +%FT%TZ)" >&2
    ping "$2" fail
  fi
}

while true; do
  hour_key="$(date -u +%Y%m%d%H)"
  minute="$(date -u +%M)"
  day_key="$(date -u +%Y%m%d)"
  if [ "$minute" -ge 7 ] && [ "$last_db" != "$hour_key" ]; then
    last_db="$hour_key"
    run db-backup.sh "${BACKUP_DB_PING_URL:-}" DB
  fi
  if [ "$(date -u +%H%M)" -ge 0230 ] && [ "$last_media" != "$day_key" ]; then
    last_media="$day_key"
    run media-backup.sh "${BACKUP_MEDIA_PING_URL:-}" MEDIA
  fi
  sleep 30
done
