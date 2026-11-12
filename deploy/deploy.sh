#!/usr/bin/env bash
# Deploy one stack on the VPS.   Usage: deploy/deploy.sh <staging|prod> [git-ref]
#   pull -> build -> (prod: DB dump first) -> migrate as csfr_owner -> collectstatic -> restart web + tasks
# Run as the `deploy` user on the server. See docs/server-setup.md for the directory layout:
#   /srv/csfr/<env>/src       git checkout (cloned by this script on first run)
#   /srv/csfr/<env>/app.env   web + cron secrets          (never in git)
#   /srv/csfr/<env>/db.env    Postgres superuser + role passwords (never in git)
set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in staging|prod) ;; *) echo "usage: $0 <staging|prod> [git-ref]" >&2; exit 2 ;; esac
REF="${2:-main}"

ROOT="${CSFR_ROOT:-/srv/csfr}"
REPO_URL="${CSFR_REPO_URL:-https://github.com/storm756/CertificationPlatform.git}"
SRC="$ROOT/$ENV_NAME/src"
export CSFR_ENV="$ENV_NAME"
export CSFR_ENV_FILE="$ROOT/$ENV_NAME/app.env"
export CSFR_DB_ENV_FILE="$ROOT/$ENV_NAME/db.env"

for f in "$CSFR_ENV_FILE" "$CSFR_DB_ENV_FILE"; do
  [ -f "$f" ] || { echo "missing $f (see deploy/env.$ENV_NAME.example)" >&2; exit 1; }
done

echo "==> [$ENV_NAME] fetching $REF"
if [ ! -d "$SRC/.git" ]; then
  mkdir -p "$(dirname "$SRC")"
  git clone "$REPO_URL" "$SRC"
fi
git -C "$SRC" fetch --tags --prune origin
git -C "$SRC" checkout --force "$REF"
# On a branch: fast-forward to the remote; on a tag/sha: stay put.
if git -C "$SRC" symbolic-ref -q HEAD >/dev/null; then
  git -C "$SRC" reset --hard "origin/$REF"
fi
cd "$SRC/deploy"

COMPOSE=(docker compose -f compose.yml)
[ "$ENV_NAME" = "staging" ] && COMPOSE+=(--profile mailpit)

echo "==> shared network, static and media volumes"
docker network inspect csfr-edge >/dev/null 2>&1 || docker network create csfr-edge >/dev/null
for v in csfr-staging_static csfr-prod_static csfr-staging_media csfr-prod_media; do
  docker volume inspect "$v" >/dev/null 2>&1 || docker volume create "$v" >/dev/null
done

echo "==> building images"
"${COMPOSE[@]}" build

echo "==> starting database"
"${COMPOSE[@]}" up -d --wait db

if [ "$ENV_NAME" = "prod" ]; then
  echo "==> pre-deploy database dump"
  # Runs the same encrypted dump the hourly job does (also uploads off-site).
  "${COMPOSE[@]}" up -d cron
  "${COMPOSE[@]}" exec -T cron db-backup.sh
fi

owner_pw="$(grep -E '^DB_OWNER_PASSWORD=' "$CSFR_DB_ENV_FILE" | head -1 | cut -d= -f2-)"
[ -n "$owner_pw" ] || { echo "DB_OWNER_PASSWORD missing in $CSFR_DB_ENV_FILE" >&2; exit 1; }
RUN_OWNER=("${COMPOSE[@]}" run --rm --no-deps -e DB_USER=csfr_owner -e "DB_PASSWORD=$owner_pw" web)

echo "==> migrating (as csfr_owner)"
"${RUN_OWNER[@]}" python manage.py migrate --noinput

echo "==> collectstatic"
"${RUN_OWNER[@]}" python manage.py collectstatic --noinput

echo "==> restarting"
"${COMPOSE[@]}" up -d --remove-orphans
docker compose -f compose.edge.yml up -d
"${COMPOSE[@]}" up -d --wait web
# tasks runs the same image as web; `up -d` recreates it with the new image, so it never runs old code.
"${COMPOSE[@]}" up -d tasks

echo "==> done: $ENV_NAME is running $(git -C "$SRC" rev-parse --short HEAD)"
docker image prune -f >/dev/null
