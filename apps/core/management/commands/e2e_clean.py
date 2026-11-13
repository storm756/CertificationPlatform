"""Remove everything `e2e_seed` added, including accounts the journeys registered.

Only rows with the e2e marker go (addresses ending @e2e.example.com, batches E2E-*, parts
"E2E-J *", questions "E2EJ-*", exam set E2EJ, module 91). Development and staging only.

A released exam set and question versions are fixed by database triggers, so removing the invented
ones needs the database owner (your development database). On staging they stay, and the output
says so; they are inert.
"""

import json

from django.core.management.base import BaseCommand

from apps.core import e2e_data


class Command(BaseCommand):
    help = "Delete the invented journey data."

    def handle(self, *args, **options):
        done = e2e_data.clean_marked([e2e_data.JOURNEY_DOMAIN], ["E2E-"])
        done.update(e2e_data.clean_course())
        self.stdout.write(json.dumps(done))
