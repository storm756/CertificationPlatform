"""Certificate numbers and verify codes (§12, D36)."""

import re
import secrets

from django.db import connection

# Crockford base32: no I, L, O or U, so a code read aloud or typed from paper is hard to get wrong.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 10  # 50 random bits; the verify page is also rate-limited
_CODE_RE = re.compile(f"^[{ALPHABET}]{{{CODE_LENGTH}}}$")
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def new_verify_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(raw: str) -> str | None:
    """The code as stored, or None if it can't be one. Case, spaces and hyphens don't matter, and
    O / I / L are read as 0 / 1 / 1. A certificate number never normalises to a code, so there is
    no lookup by number."""
    code = re.sub(r"[\s-]", "", raw or "").upper().translate(_LOOKALIKES)
    return code if _CODE_RE.match(code) else None


def next_serial() -> int:
    """The next value of the global `certificate_serial` sequence. Never reset, never reused."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('certificate_serial')")
        return cursor.fetchone()[0]


def certificate_number(prefix: str, year: int, centre_code: str, serial: int) -> str:
    """CCFR-2026-SAKEC-000001: prefix, issue year, the batch's centre code, a 6-digit serial."""
    return f"{prefix}-{year}-{centre_code}-{serial:06d}"
