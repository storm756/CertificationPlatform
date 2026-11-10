from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="PeriodicRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job", models.CharField(max_length=60, unique=True)),
                ("last_success_at", models.DateTimeField()),
            ],
        ),
    ]
