"""Add the invented data the browser journeys (e2e/) need. Development and staging only.

    docker compose -f deploy/compose.dev.yml exec -T web \
        python manage.py e2e_seed > e2e/manifest.json

Prints one JSON manifest on stdout (ids and addresses the tests use) and nothing else there.
Safe to run again: it only adds what is missing. Remove it all with `manage.py e2e_clean`.
"""

import json
import sys

from django.core.management.base import BaseCommand

from apps.core import e2e_data


class Command(BaseCommand):
    help = (
        "Create invented batches, learners, a mentor and an exam set for the Playwright journeys."
    )

    def handle(self, *args, **options):
        manifest = e2e_data.seed_journeys()
        sys.stderr.write("e2e_seed done: remove it with `manage.py e2e_clean`.\n")
        self.stdout.write(json.dumps(manifest, indent=2))
