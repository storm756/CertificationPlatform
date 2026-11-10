"""Guardian consent for 16-17-year-olds (D16). The consent *method* is pending CyberPeace
legal, so everything that could change lives in this module and the GuardianConsent model."""

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


def send_request(consent: GuardianConsent, raw_token: str) -> bool:
    """Email the guardian. Returns False if the daily budget is used up."""
    if not email_budget.can_send(email_budget.GUARDIAN, consent.guardian_email):
        return False
    body = render_to_string(
        "accounts/email/guardian_request.txt",
        {"consent": consent, "url": consent_url(raw_token), "learner": consent.user.profile},
    )
    send_mail(
        "Please confirm consent for your child to join Cyber First Response",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [consent.guardian_email],
    )
    email_budget.record(email_budget.GUARDIAN, consent.guardian_email)
    consent.sent_at = timezone.now()
    consent.save(update_fields=["sent_at", "updated_at"])
    return True


def resend(user) -> bool:
    """Issue a fresh link (the old one stops working) and email it."""
    consent = user.guardian_consent
    if consent.confirmed_at:
        return False
    raw, hashed = new_token()
    consent.token_hash = hashed
    consent.save(update_fields=["token_hash", "updated_at"])
    return send_request(consent, raw)


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
