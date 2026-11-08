from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.services import audit


class Command(BaseCommand):
    help = (
        "Delete learner accounts that never verified their email within 7 days (architecture 7.2)."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.UNVERIFIED_ACCOUNT_DAYS)
        verified = EmailAddress.objects.filter(user=OuterRef("pk"), verified=True)
        stale = User.objects.filter(role=Role.LEARNER, created_at__lt=cutoff).exclude(
            Exists(verified)
        )
        count = 0
        for user in stale:
            audit("account.purged_unverified", target=user, user_id=user.pk)
            user.delete()
            count += 1
        self.stdout.write(f"Deleted {count} unverified account(s).")
