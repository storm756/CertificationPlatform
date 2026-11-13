#!/usr/bin/env bash
# Restore an encrypted DB backup into a THROWAWAY Postgres (never staging or prod) and sanity-check it.
#
#   deploy/restore.sh --identity /path/to/age-identity.txt  csfr-prod-20261108T120700Z.dump.age
#
# --identity  the age PRIVATE key (kept offline by two named people). Read-only mount; never copied.
# The backup file is downloaded from the bucket beforehand (with a read-capable key, not the
# write-only one used by the server).
# --keep      leave the throwaway database running afterwards for inspection.
set -euo pipefail

IDENTITY=""; KEEP=0; FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --identity) IDENTITY="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) FILE="$1"; shift ;;
  esac
done
[ -n "$IDENTITY" ] && [ -f "$IDENTITY" ] || { echo "need --identity <age private key file>" >&2; exit 2; }
[ -n "$FILE" ] && [ -f "$FILE" ] || { echo "need a backup file (*.dump.age)" >&2; exit 2; }

# pwd -W gives a native path under Git Bash on Windows (docker.exe cannot read /d/...); plain pwd elsewhere.
absdir() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }
HERE="$(absdir "$(dirname "$0")")"
RUN_ID="restore-$(date +%s)-$$"
PG="csfr-$RUN_ID-db"
NET="csfr-$RUN_ID"
IMG="csfr-backup:restore"
PW="$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"

cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo "kept: container $PG on network $NET (password $PW). Remove with: docker rm -f $PG; docker network rm $NET"
  else
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# MSYS_NO_PATHCONV keeps Git Bash on Windows from rewriting container paths.
export MSYS_NO_PATHCONV=1

echo "==> building tool image (age + pg client)"
docker build -q -t "$IMG" "$HERE/backup" >/dev/null

echo "==> starting throwaway Postgres 17"
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=csfr postgres:17 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$PG" pg_isready -U postgres -d csfr >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$PG" pg_isready -U postgres -d csfr >/dev/null

echo "==> decrypting and restoring"
IDENTITY_ABS="$(absdir "$(dirname "$IDENTITY")")/$(basename "$IDENTITY")"
FILE_ABS="$FILE"
docker run --rm -i --user root --entrypoint age -v "$IDENTITY_ABS:/identity:ro" "$IMG" -d -i /identity < "$FILE_ABS" \
  | docker exec -i "$PG" pg_restore -U postgres -d csfr --no-owner --no-privileges --exit-on-error

echo "==> checks"
q() { docker exec "$PG" psql -U postgres -d csfr -tAc "$1"; }
tables="$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
[ "$tables" -gt 0 ] || { echo "FAIL: restored database has no tables" >&2; exit 1; }
echo "tables restored: $tables"
echo "users:           $(q 'SELECT count(*) FROM accounts_user')"
echo "migrations:      $(q 'SELECT count(*) FROM django_migrations')"
echo "RESTORE OK (throwaway stack, nothing else was touched)"
