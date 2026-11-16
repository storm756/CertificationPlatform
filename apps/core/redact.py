"""Keep one-time links out of logs (security audit L2).

Mentor reset links, guardian consent links, allauth's password-reset and email-confirm keys and
certificate verify codes are secrets while they are valid. Gunicorn's access log, Django's own
"Not Found: /reset/…" lines and Sentry would otherwise keep them. `redact()` replaces the token part
with `***`; `RedactTokensFilter` applies it to every log record that passes a handler.

Plain Python only (no Django import): gunicorn loads this before Django is set up.
"""

import logging
import re

MASK = "***"

# Leftmost match wins, so the long allauth prefixes are found before the short "/reset/". The
# lookbehind keeps "/accounts/password/reset/" (the request form, no key) intact.
_PATH = re.compile(
    r"(/accounts/password/reset/key/"
    r"|/accounts/confirm-email/"
    r"|(?<!/password)/reset/"
    r"|/guardian/"
    r"|/verify/)"
    r"[^/\s?#\"'&]+"
)
_QUERY = re.compile(r"([?&](?:key|token|code|uid|uidb36)=)[^&\s#\"']+", re.IGNORECASE)


def redact(text):
    """`text` with every one-time token in a path or query string replaced by ***."""
    if not isinstance(text, str) or "/" not in text and "=" not in text:
        return text
    return _QUERY.sub(rf"\g<1>{MASK}", _PATH.sub(rf"\g<1>{MASK}", text))


class RedactTokensFilter(logging.Filter):
    """Formats the record's message once, redacts it and drops the args. Never drops a record."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # a broken format string: leave it for the handler to report
            return True
        cleaned = redact(message)
        if cleaned != message or record.args:
            record.msg, record.args = cleaned, None
        return True
