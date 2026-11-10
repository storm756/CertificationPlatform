from django.db import migrations

# A QuestionVersion is never edited or deleted (CLAUDE.md). The model refuses it, and this trigger
# makes the database refuse it too, for scripts, the admin and any runtime role.
SQL = """
CREATE FUNCTION questions_version_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'QuestionVersion rows are immutable: add a new version instead';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER questions_version_no_update_delete
  BEFORE UPDATE OR DELETE ON questions_questionversion
  FOR EACH ROW EXECUTE FUNCTION questions_version_immutable();
"""
REVERSE = """
DROP TRIGGER questions_version_no_update_delete ON questions_questionversion;
DROP FUNCTION questions_version_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("questions", "0001_initial")]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE)]
