from django.db import migrations

# A unit version's title and blocks never change (CLAUDE.md "Never"). Status and publish fields may
# change (draft -> published -> superseded), so the trigger guards the text and refuses deletes.
SQL = """
CREATE FUNCTION content_version_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'UnitVersion rows are kept as history';
  END IF;
  IF NEW.title IS DISTINCT FROM OLD.title OR NEW.blocks IS DISTINCT FROM OLD.blocks
     OR NEW.unit_id IS DISTINCT FROM OLD.unit_id OR NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'UnitVersion text is immutable: add a new version instead';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER content_version_guard_trg BEFORE UPDATE OR DELETE ON content_unitversion
  FOR EACH ROW EXECUTE FUNCTION content_version_guard();
"""
REVERSE = "DROP TRIGGER content_version_guard_trg ON content_unitversion; DROP FUNCTION content_version_guard();"


class Migration(migrations.Migration):
    dependencies = [("content", "0003_lessons")]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE)]
