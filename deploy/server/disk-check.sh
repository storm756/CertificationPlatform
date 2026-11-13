#!/usr/bin/env bash
# Disk alert at 80% (architecture §17). Run by the host's cron, as the deploy user, every 15 minutes:
#   */15 * * * * /srv/csfr/edge/src/deploy/server/disk-check.sh
# Reads DISK_PING_URL (and optionally DISK_ALERT_PERCENT, default 80) from /srv/csfr/monitoring.env.
# Under the limit it pings the URL; at or over it pings "<url>/fail", so the heartbeat service alerts
# a person. With no URL it only prints (cron mails the output, if mail is set up).
set -euo pipefail

CONF="${CSFR_MONITORING_ENV:-/srv/csfr/monitoring.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
LIMIT="${DISK_ALERT_PERCENT:-80}"
URL="${DISK_PING_URL:-}"

# The fullest of / and Docker's data directory (volumes, images, backups live there).
paths=(/)
[ -d /var/lib/docker ] && paths+=(/var/lib/docker)
used="$(df -P "${paths[@]}" | awk 'NR > 1 { gsub("%", "", $5); if ($5 > max) max = $5 } END { print max + 0 }')"

if [ "$used" -ge "$LIMIT" ]; then
  echo "DISK ${used}% used (limit ${LIMIT}%) on $(hostname)" >&2
  [ -n "$URL" ] && curl -fsS -m 10 --retry 3 -o /dev/null "${URL%/}/fail"
  exit 1
fi
[ -n "$URL" ] && curl -fsS -m 10 --retry 3 -o /dev/null "$URL"
exit 0
