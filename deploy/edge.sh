#!/usr/bin/env bash
# The shared front door (edge Caddy) for staging AND prod.   Usage: deploy/deploy.sh edge [git-ref]
# Called by deploy.sh; not meant to be run on its own.
#
# Staging and prod share one Caddy. Its config used to come from whichever env checkout deployed last,
# so a staging deploy could change (or break) prod's routing. Now it lives in one fixed place,
# outside both env checkouts, and only this step changes it:
#   /srv/csfr/edge/src                 git checkout used only to read the edge files (default ref: main)
#   /srv/csfr/edge/caddy/Caddyfile     the config Caddy runs (mounted read-only as /etc/caddy)
#   /srv/csfr/edge/caddy/Caddyfile.prev  the one before, for a quick manual roll back
#   /srv/csfr/edge/compose.edge.yml    copied from the checkout; project name csfr-edge (keeps TLS certs)
#   /srv/csfr/edge/.env                optional: PROD_DOMAIN / STAGING_DOMAIN overrides (not in git)
#
# Order: fetch -> validate the NEW file in a throwaway Caddy -> install -> start -> reload.
# A file that fails validation is never installed; a reload that fails puts the previous file back.
set -euo pipefail

REF="${1:-main}"
ROOT="${CSFR_ROOT:-/srv/csfr}"
REPO_URL="${CSFR_REPO_URL:-https://github.com/storm756/CertificationPlatform.git}"
EDGE="$ROOT/edge"
SRC="$EDGE/src"
CADDY_IMAGE="${CSFR_CADDY_IMAGE:-caddy:2}"

echo "==> [edge] fetching $REF"
if [ ! -d "$SRC/.git" ]; then
  mkdir -p "$EDGE"
  git clone "$REPO_URL" "$SRC"
fi
git -C "$SRC" fetch --tags --prune origin
git -C "$SRC" checkout --force "$REF"
if git -C "$SRC" symbolic-ref -q HEAD >/dev/null; then
  git -C "$SRC" reset --hard "origin/$REF"
fi
REV="$(git -C "$SRC" rev-parse --short HEAD)"

mkdir -p "$EDGE/caddy"
NEW="$EDGE/caddy/Caddyfile.new"
cp "$SRC/deploy/caddy/Caddyfile" "$NEW"

# The same domain values the running Caddy gets (compose defaults, or .env next to compose.edge.yml).
set -a
# shellcheck disable=SC1091
[ -f "$EDGE/.env" ] && . "$EDGE/.env"
set +a
PROD_DOMAIN="${PROD_DOMAIN:-cyberfirstresponse.io}"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.cyberfirstresponse.io}"

echo "==> [edge] validating the new Caddyfile ($REV) in a throwaway Caddy"
if ! docker run --rm \
  -e PROD_DOMAIN="$PROD_DOMAIN" -e STAGING_DOMAIN="$STAGING_DOMAIN" -e SCHEME="${SCHEME:-}" \
  -v "$NEW:/etc/caddy/Caddyfile:ro" "$CADDY_IMAGE" \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  rm -f "$NEW"
  echo "Caddyfile at $REV is invalid: nothing was installed; Caddy still runs its previous config" >&2
  exit 1
fi

echo "==> [edge] shared network and volumes"
docker network inspect csfr-edge >/dev/null 2>&1 || docker network create csfr-edge >/dev/null
for v in csfr-staging_static csfr-prod_static csfr-staging_media csfr-prod_media; do
  docker volume inspect "$v" >/dev/null 2>&1 || docker volume create "$v" >/dev/null
done

echo "==> [edge] installing"
LIVE="$EDGE/caddy/Caddyfile"
[ -f "$LIVE" ] && cp "$LIVE" "$EDGE/caddy/Caddyfile.prev"
cp "$SRC/deploy/compose.edge.yml" "$EDGE/compose.edge.yml"
# Rewrite the file in place (same inode), so Caddy's read-only directory mount sees the new content.
cat "$NEW" > "$LIVE"
rm -f "$NEW"

COMPOSE=(docker compose --project-directory "$EDGE" -f "$EDGE/compose.edge.yml")
"${COMPOSE[@]}" up -d --remove-orphans
CADDY=("${COMPOSE[@]}" exec -T caddy caddy)
echo "==> [edge] reloading Caddy"
if ! "${CADDY[@]}" reload --config /etc/caddy/Caddyfile --adapter caddyfile --force; then
  echo "reload failed: putting the previous Caddyfile back" >&2
  if [ -f "$EDGE/caddy/Caddyfile.prev" ]; then
    cat "$EDGE/caddy/Caddyfile.prev" > "$LIVE"
    "${CADDY[@]}" reload --config /etc/caddy/Caddyfile --adapter caddyfile --force || true
  fi
  exit 1
fi
echo "==> [edge] done: Caddy runs the Caddyfile from $REV"
