from django.db import migrations

# Modules 1-9 are the graded learning modules; module 10 is the capstone, a learning module that is
# not graded (D26). Titles and units arrive in Stage 4 (title_key is the translation key).
def seed(apps, schema_editor):
    Module = apps.get_model("content", "Module")
    for n in range(1, 11):
        Module.objects.update_or_create(
            number=n,
            defaults={
                "slug": f"module-{n}",
                "title_key": f"module.{n}.title",
                "kind": "capstone" if n == 10 else "learning",
                "counted": n != 10,
                "order": n,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("content", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
