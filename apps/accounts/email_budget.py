"""Email budgets (architecture 7.2): Brevo allows 300/day.

registration 150 · reset + guardian 100 · reserve 50. At most 1 email per address per 24 h on
the duplicate and reset paths. Admins are alerted once a day when the total reaches 150.
"""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailLog

REGISTRATION = "registration"  # verification emails
DUPLICATE = "duplicate"  # "you already have an account" notice
RESET = "reset"
GUARDIAN = "guardian"
ALERT = "alert"

# Which daily pool each kind draws from.
POOL_OF = {
    REGISTRATION: "registration",
    DUPLICATE: "registration",
    RESET: "reset_guardian",
    GUARDIAN: "reset_guardian",
    ALERT: "reserve",
}
# Kinds that may be sent to one address at most once in 24 hours.
ONCE_PER_ADDRESS = {DUPLICATE, RESET}


def _hash(address: str) -> str:
    return hashlib.sha256(address.strip().lower().encode()).hexdigest()


def _since_midnight(now=None):
    local = timezone.localtime(now or timezone.now())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def sent_today(now=None) -> dict[str, int]:
    """Per-pool and total counts since local midnight, for the admin dashboard."""
    counts = {"registration": 0, "reset_guardian": 0, "reserve": 0}
    for log in EmailLog.objects.filter(sent_at__gte=_since_midnight(now)).values_list(
        "kind", flat=True
    ):
        counts[POOL_OF.get(log, "reserve")] += 1
    counts["total"] = sum(counts.values())
    return counts


def has_room(kind: str, now=None) -> bool:
    limits = settings.EMAIL_DAILY_BUDGET
    pool = POOL_OF[kind]
    return sent_today(now)[pool] < limits[pool]


def can_send(kind: str, address: str, now=None) -> bool:
    now = now or timezone.now()
    if not has_room(kind, now):
        return False
    if kind in ONCE_PER_ADDRESS:
        recent = EmailLog.objects.filter(
            kind=kind, address_hash=_hash(address), sent_at__gte=now - timedelta(hours=24)
        )
        if recent.exists():
            return False
    return True


def record(kind: str, address: str) -> None:
    EmailLog.objects.create(kind=kind, address_hash=_hash(address))
    _maybe_alert_admins()


def _maybe_alert_admins() -> None:
    from django.core.mail import send_mail

    from .models import Role, User

    total = sent_today()["total"]
    if total < settings.EMAIL_ALERT_AT:
        return
    start = _since_midnight()
    if EmailLog.objects.filter(kind=ALERT, sent_at__gte=start).exists():
        return
    EmailLog.objects.create(kind=ALERT, address_hash=_hash("admins"))
    admins = list(
        User.objects.filter(role=Role.ADMIN, is_active=True).values_list("email", flat=True)
    )
    if admins:
        send_mail(
            "Daily email budget: 150 sent",
            f"{total} emails have been sent today. The Brevo limit is 300 a day.",
            settings.DEFAULT_FROM_EMAIL,
            admins,
            fail_silently=True,
        )
