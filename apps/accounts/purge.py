"""Remove learner accounts that never finished signing up (DPDP data minimisation).

Two rules, both sending no email:
1. Email still unverified UNVERIFIED_ACCOUNT_DAYS (7) after sign-up.
2. Still waiting for guardian consent UNVERIFIED_ACCOUNT_DAYS after the consent link expired
   (so 14 + 7 = 21 days after the link was sent).
Seats are freed much sooner by is_accepting(); this only clears the personal data.
"""

from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db import transaction
from django.db.models import DateTimeField, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit.services import audit

from .models import GuardianConsent, Role, User, UserStatus

AUDIT_ACTION = "system.purge_unverified"


def unverified_stale(now):
    cutoff = now - timedelta(days=settings.UNVERIFIED_ACCOUNT_DAYS)
    verified = EmailAddress.objects.filter(user=OuterRef("pk"), verified=True)
    return User.objects.filter(role=Role.LEARNER, created_at__lt=cutoff).exclude(Exists(verified))


def guardian_expired_stale(now):
    """Users still pending_guardian whose consent link expired more than 7 days ago."""
    grace = timedelta(days=settings.GUARDIAN_LINK_DAYS + settings.UNVERIFIED_ACCOUNT_DAYS)
    sent = Coalesce("sent_at", "created_at", output_field=DateTimeField())
    stale_consents = (
        GuardianConsent.objects.filter(confirmed_at__isnull=True)
        .annotate(base=sent)
        .filter(base__lt=now - grace)
        .values("user_id")
    )
    return User.objects.filter(
        role=Role.LEARNER, status=UserStatus.PENDING_GUARDIAN, pk__in=stale_consents
    )


def purge_stale_accounts(now=None) -> dict:
    """Delete both groups. Returns the counts; the audit event holds counts only."""
    now = now or timezone.now()
    with transaction.atomic():
        unverified_ids = list(unverified_stale(now).values_list("pk", flat=True))
        User.objects.filter(pk__in=unverified_ids).delete()
        guardian_ids = list(guardian_expired_stale(now).values_list("pk", flat=True))
        User.objects.filter(pk__in=guardian_ids).delete()
        counts = {"unverified": len(unverified_ids), "guardian_expired": len(guardian_ids)}
        counts["count"] = counts["unverified"] + counts["guardian_expired"]
        audit(AUDIT_ACTION, **counts)
    return counts
