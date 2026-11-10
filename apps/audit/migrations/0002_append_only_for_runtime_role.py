from django.db import migrations

# The runtime role (csfr_app) may only INSERT and SELECT audit rows (architecture 6).
# The role doesn't exist in dev/CI (they connect as a superuser), so this is conditional.
REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'csfr_app') THEN
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM csfr_app;
  END IF;
END
$$;
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(REVOKE, reverse_sql=migrations.RunSQL.noop)]
