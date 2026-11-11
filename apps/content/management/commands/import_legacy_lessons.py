"""Import the legacy lesson content (55 reading topics, handouts, film shells). Counts only.

python manage.py import_legacy_lessons --source content-data/legacy/lessons [--dry-run]
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.content import legacy


class Command(BaseCommand):
    help = "Import the private legacy lesson files as published units. Create-only."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, source, dry_run, **options):
        path = Path(source)
        if not path.is_dir():
            raise CommandError("Source folder not found.")
        try:
            if dry_run:
                result = legacy.report(legacy.plan(legacy.load_sources(path)))
            else:
                result = legacy.run(path)
        except legacy.ImportRefused as exc:
            raise CommandError(str(exc)) from None
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")
