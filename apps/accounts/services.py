"""Registration (architecture 7.2): one locked transaction, then the emails."""

import logging
from dataclasses import dataclass
from enum import Enum

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.services import audit, client_ip
from apps.batches.models import Batch, Enrolment
from apps.batches.rules import is_accepting

from . import email_budget, guardian
from .models import ConsentRecord, Profile, User, UserStatus, normalise_email
from .rules import AGE_GUARDIAN, age_band

log = logging.getLogger(__name__)


class Outcome(Enum):
    CREATED = "created"
    EXISTING_EMAIL = "existing_email"  # shown to the visitor exactly like CREATED
    BATCH_CLOSED = "batch_closed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class Registration:
    outcome: Outcome
    user: User | None = None
    guardian_token: str | None = None


def register(data: dict, request) -> Registration:
    """`data` is the cleaned RegistrationForm. Nothing is created unless the batch is still
    accepting at the moment the batch row is locked."""
    now = timezone.now()
    email = data["email"].strip().lower()
    user = token = None
    try:
        with transaction.atomic():
            batch = Batch.objects.select_for_update().get(pk=data["batch"].pk)
            if not is_accepting(batch, now):
                return Registration(Outcome.BATCH_CLOSED)
            if not email_budget.has_room(email_budget.REGISTRATION, now):
                return Registration(Outcome.BUDGET_EXHAUSTED)
            norm = normalise_email(email)
            existing = User.objects.filter(
                Q(email_normalized=norm) | Q(email__iexact=email)
            ).exists()
            if not existing:
                user, token = _create_account(data, batch, email, request)
    except IntegrityError:  # two sign-ups with the same email raced each other
        existing = True

    if existing:
        _send_already_registered(email)
        return Registration(Outcome.EXISTING_EMAIL)

    # Emails go out only after the transaction has committed.
    EmailAddress.objects.get(user=user, email=email).send_confirmation(request, signup=True)
    if token:
        guardian.send_request(user.guardian_consent, token)
    return Registration(Outcome.CREATED, user=user, guardian_token=token)


def _create_account(data, batch, email, request):
    band = age_band(data["date_of_birth"], timezone.localdate())
    needs_guardian = band == AGE_GUARDIAN
    user = User.objects.create_user(
        email,
        data["password"],
        status=UserStatus.PENDING_GUARDIAN if needs_guardian else UserStatus.ACTIVE,
    )
    Profile.objects.create(
        user=user,
        certificate_name=data["certificate_name"],
        date_of_birth=data["date_of_birth"],
        preferred_language=data["preferred_language"],
    )
    Enrolment.objects.create(user=user, batch=batch)
    ConsentRecord.objects.create(
        user=user,
        notice_version=settings.PRIVACY_NOTICE_VERSION,
        purpose="privacy_notice",
        given=True,
        ip=client_ip(request),
    )
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    token = None
    if needs_guardian:
        token = guardian.create_pending(user, data["guardian_name"], data["guardian_email"])
    audit(
        "registration.created",
        actor=user,
        target=user,
        request=request,
        batch_id=batch.pk,
        needs_guardian=needs_guardian,
    )
    return user, token


def _send_already_registered(email: str) -> None:
    """Same page for the visitor either way; the real owner gets a note, once a day."""
    if not email_budget.can_send(email_budget.DUPLICATE, email):
        return
    body = render_to_string("accounts/email/already_registered.txt", {"site": settings.SITE_NAME})
    send_mail("You already have an account", body, settings.DEFAULT_FROM_EMAIL, [email])
    email_budget.record(email_budget.DUPLICATE, email)
