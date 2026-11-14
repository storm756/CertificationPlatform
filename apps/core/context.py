from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language


def programme(request):
    """Programme name and language list for every page (D23: never hard-coded in templates)."""
    extra = {}
    if request.path == reverse("account_reset_password_done"):
        # Set by the account adapter when the day's one reset email already went to this address.
        from apps.accounts.adapter import RESET_LIMITED_KEY

        extra["reset_limited"] = bool(request.session.pop(RESET_LIMITED_KEY, False))
    return {
        **extra,
        "PROGRAMME_NAME": settings.PROGRAMME_NAME,
        "PROGRAMME_SHORT": settings.PROGRAMME_SHORT,
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        # The header select shows short labels, like the prototype: EN, हिन्दी, मराठी, ગુજરાતી.
        "LANGUAGE_CHOICES": [
            (code, "EN" if code == "en" else name) for code, name in settings.LANGUAGES
        ],
        "CURRENT_LANGUAGE": get_language() or settings.LANGUAGE_CODE,
    }
