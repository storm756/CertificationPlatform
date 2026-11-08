"""Staff must have TOTP set up before they can reach anything (architecture 5, 7.4)."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

# Paths a staff member without an authenticator is still allowed to use.
_ALLOWED_PREFIXES = ("/accounts/", "/static/", "/healthz/", "/i18n/")


def has_authenticator(user) -> bool:
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


class StaffMFARequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.is_staff:
            request.session.set_expiry(settings.STAFF_SESSION_AGE)
            if not request.path.startswith(_ALLOWED_PREFIXES) and not has_authenticator(user):
                return redirect(reverse("mfa_activate_totp"))
        return self.get_response(request)
