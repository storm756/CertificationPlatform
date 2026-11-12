from django.db import migrations

# A released exam paper is fixed (D31). The models refuse changes, and these triggers make the
# database refuse them too, for scripts and queryset updates: released membership, the released set
# itself, the marks / format / module / pool / status of its questions, and new versions of them.
SQL = """
CREATE FUNCTION assessments_examsetitem_guard() RETURNS trigger AS $$
DECLARE sid bigint;
BEGIN
  IF TG_OP = 'INSERT' THEN sid := NEW.exam_set_id; ELSE sid := OLD.exam_set_id; END IF;
  IF EXISTS (SELECT 1 FROM assessments_examset WHERE id = sid AND status = 'released')
     OR (TG_OP = 'UPDATE' AND EXISTS (
          SELECT 1 FROM assessments_examset WHERE id = NEW.exam_set_id AND status = 'released')) THEN
    RAISE EXCEPTION 'A released exam set is fixed: start a new draft set instead';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER assessments_examsetitem_guard_trg
  BEFORE INSERT OR UPDATE OR DELETE ON assessments_examsetitem
  FOR EACH ROW EXECUTE FUNCTION assessments_examsetitem_guard();

CREATE FUNCTION assessments_examset_guard() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'released' AND (
       TG_OP = 'DELETE' OR NEW.status <> 'released' OR NEW.code <> OLD.code) THEN
    RAISE EXCEPTION 'A released exam set cannot be changed, withdrawn or deleted';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER assessments_examset_guard_trg
  BEFORE UPDATE OR DELETE ON assessments_examset
  FOR EACH ROW EXECUTE FUNCTION assessments_examset_guard();

CREATE FUNCTION questions_question_released_guard() RETURNS trigger AS $$
BEGIN
  IF (NEW.pool <> OLD.pool OR NEW.module_id <> OLD.module_id OR NEW.format <> OLD.format
      OR NEW.points <> OLD.points OR NEW.status <> OLD.status)
     AND EXISTS (
       SELECT 1 FROM assessments_examsetitem i
       JOIN assessments_examset s ON s.id = i.exam_set_id
       WHERE i.question_id = OLD.id AND i.state = 'member' AND s.status = 'released') THEN
    RAISE EXCEPTION 'This question is on a released exam set: start a new draft instead';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER questions_question_released_guard_trg
  BEFORE UPDATE ON questions_question
  FOR EACH ROW EXECUTE FUNCTION questions_question_released_guard();

CREATE FUNCTION questions_version_released_guard() RETURNS trigger AS $$
BEGIN
  IF EXISTS (
       SELECT 1 FROM assessments_examsetitem i
       JOIN assessments_examset s ON s.id = i.exam_set_id
       WHERE i.question_id = NEW.question_id AND i.state = 'member' AND s.status = 'released') THEN
    RAISE EXCEPTION 'This question is on a released exam set: start a new draft instead';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER questions_version_released_guard_trg
  BEFORE INSERT ON questions_questionversion
  FOR EACH ROW EXECUTE FUNCTION questions_version_released_guard();
"""
REVERSE = """
DROP TRIGGER questions_version_released_guard_trg ON questions_questionversion;
DROP FUNCTION questions_version_released_guard();
DROP TRIGGER questions_question_released_guard_trg ON questions_question;
DROP FUNCTION questions_question_released_guard();
DROP TRIGGER assessments_examset_guard_trg ON assessments_examset;
DROP FUNCTION assessments_examset_guard();
DROP TRIGGER assessments_examsetitem_guard_trg ON assessments_examsetitem;
DROP FUNCTION assessments_examsetitem_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("assessments", "0005_exam_set_fixed_papers")]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE)]
