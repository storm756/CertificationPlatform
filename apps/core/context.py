from django.conf import settings
from django.utils.translation import get_language


def programme(request):
    """Programme name and language list for every page (D23: never hard-coded in templates)."""
    return {
        "PROGRAMME_NAME": settings.PROGRAMME_NAME,
        "PROGRAMME_SHORT": settings.PROGRAMME_SHORT,
        "SUPPORT_EMAIL": getattr(settings, "SUPPORT_EMAIL", "support@cyberfirstresponse.io"),
        # The header select shows short labels, like the prototype: EN, हिन्दी, मराठी, ગુજરાતી.
        "LANGUAGE_CHOICES": [
            (code, "EN" if code == "en" else name) for code, name in settings.LANGUAGES
        ],
        "CURRENT_LANGUAGE": get_language() or settings.LANGUAGE_CODE,
    }
