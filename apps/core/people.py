"""The "Who runs it" people on the landing page (Stage 9).

The three have not all agreed yet to appear, so the page shows a placeholder card. It switches on
only when PEOPLE_CONSENT_GIVEN is set AND every photo file is present in PEOPLE_PHOTO_DIR
(content-data/people/ locally; never in git). Photos are served by `people_photo`, never as static
files, so a deploy never carries them by accident.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

# slug -> (photo file, name, role). Names and roles match the certificate signatories (D36).
PEOPLE = [
    ("bhavesh-patel", "bhavesh-patel.jpg", "Dr. Bhavesh Patel", _("Principal, SAKEC")),
    (
        "nilakshi-jain",
        "nilakshi-jain.jpg",
        "Dr. Nilakshi Jain",
        _("Head, Department of Cyber Security, SAKEC"),
    ),
    ("vineet-kumar", "vineet-kumar.webp", "Maj. Vineet Kumar", _("Founder, CyberPeace Foundation")),
]
CONTENT_TYPES = {".jpg": "image/jpeg", ".webp": "image/webp", ".png": "image/png"}


def photo_path(slug: str):
    for s, filename, *_rest in PEOPLE:
        if s == slug:
            path = settings.PEOPLE_PHOTO_DIR / filename
            return path if path.is_file() else None
    return None


def people_to_show() -> list[dict]:
    """The real cards, or an empty list (placeholder) unless consent is on and all photos exist."""
    if not settings.PEOPLE_CONSENT_GIVEN:
        return []
    if any(photo_path(slug) is None for slug, *_ in PEOPLE):
        return []
    return [{"slug": s, "name": name, "role": role} for s, _f, name, role in PEOPLE]
