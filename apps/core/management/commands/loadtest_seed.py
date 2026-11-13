"""Add (or remove) invented learners for the load test in loadtest/ (dev and staging only).

    manage.py loadtest_seed [--count 60]       # 60 learners with the final open, batch LT-01
    manage.py loadtest_seed --clean            # remove them (and their attempts)

The exam set they sit (E2EJ) is shared with `e2e_seed`; use `e2e_clean` to remove it.
"""

import json

from django.core.management.base import BaseCommand

from apps.core import e2e_data


class Command(BaseCommand):
    help = "Create (or remove) invented learners for the 60-learner load test."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=60)
        parser.add_argument("--clean", action="store_true")

    def handle(self, *args, **options):
        if options["clean"]:
            e2e_data.guard()
            done = e2e_data.clean_marked([e2e_data.LOAD_DOMAIN], [e2e_data.LOAD_BATCH])
        else:
            done = e2e_data.seed_load(options["count"])
        self.stdout.write(json.dumps(done))
