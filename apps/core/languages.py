"""The languages visitors may use: settings.LANGUAGES limited by settings.LANGUAGES_ENABLED.

settings.LANGUAGES stays complete (Rosetta, the translation review and the stored profile choices
need every language). Everything a visitor sees or chooses goes through these helpers instead.
"""

from django.conf import settings


def enabled_codes() -> list[str]:
    return list(getattr(settings, "LANGUAGES_ENABLED", None) or [settings.LANGUAGE_CODE])


def is_enabled(code: str | None) -> bool:
    return bool(code) and code in enabled_codes()


def enabled_languages() -> list[tuple[str, str]]:
    """(code, name) pairs in settings.LANGUAGES order, limited to the enabled ones."""
    codes = enabled_codes()
    return [(code, name) for code, name in settings.LANGUAGES if code in codes]


def site_language(code: str | None) -> str:
    """The language to serve for a requested code: itself if enabled, English otherwise."""
    return code if is_enabled(code) else settings.LANGUAGE_CODE


def switcher_shown() -> bool:
    return len(enabled_codes()) > 1
