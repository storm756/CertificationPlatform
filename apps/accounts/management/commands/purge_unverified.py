from django.core.management.base import BaseCommand

from apps.accounts.purge import purge_stale_accounts


class Command(BaseCommand):
    help = (
        "Delete learner accounts that never verified their email, or whose guardian never "
        "confirmed, 7 days after the deadline (architecture 7.2). Also run daily by run_periodic."
    )

    def handle(self, *args, **options):
        counts = purge_stale_accounts()
        self.stdout.write(
            f"Deleted {counts['count']} account(s): {counts['unverified']} unverified, "
            f"{counts['guardian_expired']} guardian consent expired."
        )
