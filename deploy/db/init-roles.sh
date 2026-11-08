#!/bin/sh
# Runs once, when the Postgres data directory is first created.
#   csfr_owner  owns the schema; used ONLY for migrations
#   csfr_app    runtime role; can read/write rows but cannot change the schema
# Passwords come from the stack's .env file (DB_OWNER_PASSWORD, DB_APP_PASSWORD).
set -eu

: "${DB_OWNER_PASSWORD:?}" "${DB_APP_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$DB_OWNER_PASSWORD" -v app_pw="$DB_APP_PASSWORD" -v dbname="$POSTGRES_DB" <<'SQL'
CREATE ROLE csfr_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE csfr_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;

ALTER DATABASE :"dbname" OWNER TO csfr_owner;
ALTER SCHEMA public OWNER TO csfr_owner;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO csfr_app;
GRANT USAGE ON SCHEMA public TO csfr_app;

-- Tables and sequences that csfr_owner creates later are usable by csfr_app automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE csfr_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO csfr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE csfr_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO csfr_app;
SQL
