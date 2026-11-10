"""Request gates for signed-in users.

* Staff, mentors and admins must have TOTP set up before they can reach anything but the auth
  pages (architecture 5, 7.4). Mentors don't use Django admin, so this keys on the role, not
  only on `is_staff`.
* A learner waiting for guardian consent can only see the waiting page (D16).
* After a mentor-issued reset link, the email can't be changed for 7 days (architecture 7.4).
"""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import UserStatus
from .rules import requires_mfa

# Paths a user without an authenticator is still allowed to use.
_ALLOWED_PREFIXES = ("/accounts/", "/static/", "/healthz/", "/i18n/")
_GUARDIAN_WAIT_PREFIXES = (
    "/accounts/",
    "/static/",
    "/healthz/",
    "/waiting/",
    "/guardian/",
    "/privacy/",
)
EMAIL_CHANGE_BLOCK = timedelta(days=7)


def has_authenticator(user) -> bool:
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


class StaffMFARequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if requires_mfa(user):
            request.session.set_expiry(settings.STAFF_SESSION_AGE)
            if not request.path.startswith(_ALLOWED_PREFIXES) and not has_authenticator(user):
                return redirect(reverse("mfa_activate_totp"))
        return self.get_response(request)


class LearnerGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        waiting = user.is_authenticated and user.status == UserStatus.PENDING_GUARDIAN
        if waiting and not request.path.startswith(_GUARDIAN_WAIT_PREFIXES):
            return redirect("waiting_for_guardian")
        if (
            user.is_authenticated
            and request.method == "POST"
            and request.path == reverse("account_email")
            and _email_change_blocked(user)
        ):
            messages.error(
                request,
                "Your email can't be changed for 7 days after a password reset by your mentor.",
            )
            return redirect("account_email")
        return self.get_response(request)


def _email_change_blocked(user) -> bool:
    profile = getattr(user, "profile", None)
    reset_at = profile.mentor_reset_at if profile else None
    return bool(reset_at and timezone.now() < reset_at + EMAIL_CHANGE_BLOCK)
