#!/bin/sh
# Development only (mounted by compose.dev.yml). In dev, web and the tests connect as the
# `postgres` superuser, so the tables are created by `postgres`, not `csfr_owner`. Give the
# runtime role `csfr_app` the same table rights it gets in production, so the `tasks`
# service can run as csfr_app here too.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO csfr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO csfr_app;
SQL
