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


_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_PLAIN = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/")


def _decode_plain(match):
    """%72 -> r: unreserved characters (RFC 3986 §2.3) and "/", which Django decodes before routing,
    so /%72eset/<token>/ reaches the same view as /reset/<token>/. Everything else stays encoded."""
    char = chr(int(match.group(1), 16))
    return char if char in _PLAIN else match.group(0)


def redact(text):
    """`text` with every one-time token in a path or query string replaced by ***."""
    if not isinstance(text, str) or "/" not in text and "=" not in text and "%" not in text:
        return text
    if "%" in text:
        text = _ESCAPE.sub(_decode_plain, text)
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
        if record.exc_info:
            # The formatter reuses exc_text instead of formatting the traceback again.
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        return True
