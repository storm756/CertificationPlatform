"""Batch business rules as plain functions (architecture 7.1)."""

from datetime import timedelta

from django.db.models import Exists, OuterRef, Q

from .models import BatchStatus, Enrolment

UNVERIFIED_SEAT_HOURS = 48


def seats_used(batch, now) -> int:
    """Verified enrolments plus unverified ones younger than 48 hours."""
    from allauth.account.models import EmailAddress

    verified = EmailAddress.objects.filter(user=OuterRef("user"), verified=True)
    cutoff = now - timedelta(hours=UNVERIFIED_SEAT_HOURS)
    return (
        Enrolment.objects.filter(batch=batch)
        .filter(Exists(verified) | Q(joined_at__gte=cutoff))
        .count()
    )


def is_accepting(batch, now) -> bool:
    if batch.status != BatchStatus.ACTIVE or not batch.accepting:
        return False
    if batch.opens_at and batch.opens_at > now:
        return False
    if batch.closes_at and now >= batch.closes_at:
        return False
    return seats_used(batch, now) < batch.seat_limit


def accepting_batches(now):
    """Every batch that passes is_accepting, for the registration dropdown."""
    from .models import Batch

    candidates = Batch.objects.filter(status=BatchStatus.ACTIVE, accepting=True)
    return [b for b in candidates if is_accepting(b, now)]
