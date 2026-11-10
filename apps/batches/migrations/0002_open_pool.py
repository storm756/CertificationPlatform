from django.db import migrations


def create_open_pool(apps, schema_editor):
    """The catch-all "Open Enrolment" pool. Closed by default like every batch (D9)."""
    Batch = apps.get_model("batches", "Batch")
    Batch.objects.get_or_create(
        is_open_pool=True,
        defaults={"code": "OPEN", "name": "Open Enrolment", "accepting": False},
    )


class Migration(migrations.Migration):
    dependencies = [("batches", "0001_initial")]
    operations = [migrations.RunPython(create_open_pool, migrations.RunPython.noop)]
