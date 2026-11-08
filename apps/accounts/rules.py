"""Age and role rules as plain functions (D16, architecture 5 and 7.3)."""

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
