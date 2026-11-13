"""Age and role rules as plain functions (D16, architecture 5 and 7.3)."""

import re
from datetime import date

from .models import Role

MIN_AGE = 16
ADULT_AGE = 18

AGE_REFUSE = "refuse"
AGE_GUARDIAN = "guardian"
AGE_ADULT = "adult"


def age_on(date_of_birth: date, today: date) -> int:
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years


def age_band(date_of_birth: date, today: date) -> str:
    age = age_on(date_of_birth, today)
    if age < MIN_AGE:
        return AGE_REFUSE
    if age < ADULT_AGE:
        return AGE_GUARDIAN
    return AGE_ADULT


def may_track_time(user, today: date) -> bool:
    """Time-on-task heartbeats are recorded for adults only (D16, DPDP). Unknown age = no."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return False
    return age_on(profile.date_of_birth, today) >= ADULT_AGE


def requires_mfa(user) -> bool:
    """Staff, mentors and admins must use TOTP (architecture 5). Mentors don't use Django admin
    so `is_staff` alone is not enough."""
    return user.is_authenticated and (user.is_staff or user.role in (Role.MENTOR, Role.ADMIN))


def can_access_final_pool(user) -> bool:
    """Final-pool questions are admin-only (§5, D19): mentors never see or edit them."""
    return bool(user and user.is_authenticated and user.role == Role.ADMIN)


# The certificate name is printed on an English certificate (D10), in English letters only (D37):
# A-Z and the accented Latin letters the bundled certificate fonts can print (À-ÿ), with spaces,
# full stops, hyphens and apostrophes between them. Digits and other scripts are refused.
_NAME_LETTERS = "A-Za-zÀ-ÖØ-öø-ÿ"
_CERTIFICATE_NAME = re.compile(
    rf"^[{_NAME_LETTERS}](?:[{_NAME_LETTERS} .'’-]*[{_NAME_LETTERS}.])?$"
)
CERTIFICATE_NAME_RULE = (
    "Type your name in English letters (A to Z), exactly as it should appear on your certificate."
)


def certificate_name_ok(name: str) -> bool:
    """True if the name uses only English letters (D37), so the certificate can print it."""
    name = " ".join((name or "").split())
    return len(name) >= 2 and bool(_CERTIFICATE_NAME.match(name))
