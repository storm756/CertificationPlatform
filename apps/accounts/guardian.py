"""Guardian consent for 16-17-year-olds (D16). The consent *method* is pending CyberPeace
legal, so everything that could change lives in this module and the GuardianConsent model."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.audit.services import audit

from . import email_budget
from .models import GuardianConsent, User, UserStatus
from .tokens import hash_token, new_token

logger = logging.getLogger(__name__)

DECLARATION_VERSION = "1"


def create_pending(user, guardian_name: str, guardian_email: str) -> str:
    """Create the consent request and return the raw token for the guardian's link."""
    raw, hashed = new_token()
    GuardianConsent.objects.create(
        user=user,
        guardian_name=guardian_name,
        guardian_email=guardian_email,
        token_hash=hashed,
    )
    return raw


def consent_url(raw_token: str) -> str:
    scheme = "http" if settings.DEBUG else "https"
    return f"{scheme}://{settings.SITE_DOMAIN}{reverse('guardian_consent', args=[raw_token])}"


def send_request(consent: GuardianConsent, raw_token: str, *, new_hash: str | None = None) -> bool:
    """Email the guardian. Returns False if the daily budget is used up.

    With `new_hash` (a resend) the new link replaces the old one only once the email has really
    gone out, so a failed send leaves the guardian's earlier link working.
    """
    if not email_budget.can_send(email_budget.GUARDIAN, consent.guardian_email):
        return False
    body = render_to_string(
        "accounts/email/guardian_request.txt",
        {"consent": consent, "url": consent_url(raw_token), "learner": consent.user.profile},
    )
    send_mail(
        f"Please confirm consent for your child to join {settings.PROGRAMME_NAME}",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [consent.guardian_email],
    )
    fields = ["sent_at", "updated_at"]
    consent.sent_at = timezone.now()
    if new_hash:
        consent.token_hash = new_hash
        fields.append("token_hash")
    consent.save(update_fields=fields)
    email_budget.record(email_budget.GUARDIAN, consent.guardian_email)
    return True


def resend(user) -> bool:
    """Email the guardian a fresh link. The old link keeps working until the new one is sent,
    so a full budget or a mail failure never leaves the learner without a working link."""
    consent = user.guardian_consent
    if consent.confirmed_at:
        return False
    raw, hashed = new_token()
    try:
        return send_request(consent, raw, new_hash=hashed)
    except Exception:
        logger.exception("guardian resend failed for consent %s", consent.pk)
        return False


def find_by_token(raw_token: str, now=None) -> GuardianConsent | None:
    """The pending, unexpired consent for this link, or None."""
    now = now or timezone.now()
    consent = (
        GuardianConsent.objects.select_related("user", "user__profile")
        .filter(token_hash=hash_token(raw_token), confirmed_at__isnull=True)
        .first()
    )
    if consent is None:
        return None
    base = consent.sent_at or consent.created_at
    if now > base + timedelta(days=settings.GUARDIAN_LINK_DAYS):
        return None
    return consent


@transaction.atomic
def confirm(consent: GuardianConsent, typed_name: str, request=None) -> None:
    now = timezone.now()
    consent.confirmed_at = now
    consent.confirmed_name = typed_name
    consent.declaration_text_version = DECLARATION_VERSION
    consent.save()
    User.objects.filter(pk=consent.user_id, status=UserStatus.PENDING_GUARDIAN).update(
        status=UserStatus.ACTIVE
    )
    audit("guardian.confirmed", target=consent.user, request=request)
