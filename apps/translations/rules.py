"""Who may change and review translations (architecture §14, D7).

* A translator (`upload_translations`) uploads lines; every new or changed line is a draft.
* A per-language Reviewer (`review_hi`, `review_mr`, `review_gu`) marks a draft reviewed, but never
  a line they uploaded themselves, and never a stale line (its English changed since).
"""

from django.db import transaction
from django.utils import timezone

from apps.audit.services import audit

from . import keys
from .models import TRANSLATED_LANGUAGES, Translation, TranslationStatus


def can_upload(user) -> bool:
    return bool(user and user.is_active and user.has_perm("translations.upload_translations"))


def can_use_rosetta(user) -> bool:
    """Rosetta (UI .po strings) is for staff translators and admins only."""
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and (user.is_superuser or user.has_perm("translations.upload_translations"))
    )


def is_reviewer(user, language: str) -> bool:
    return bool(
        user
        and user.is_active
        and language in TRANSLATED_LANGUAGES
        and user.has_perm(f"translations.review_{language}")
    )


def review_refusal(user, row: Translation, current_english: str | None) -> str | None:
    """Why `user` cannot mark `row` reviewed, or None when they can."""
    if not is_reviewer(user, row.language):
        return f"You are not a reviewer for {row.get_language_display()}."
    if row.uploaded_by_id is not None and row.uploaded_by_id == user.pk:
        return "You uploaded this line, so someone else must review it."
    if row.status == TranslationStatus.REVIEWED:
        return "This line is already reviewed."
    if current_english is None:
        return "This key is no longer in the course."
    if keys.source_hash(current_english) != row.source_hash:
        return "The English changed since this was translated. Upload a new translation first."
    return None


def mark_reviewed(user, row: Translation, current_english: str | None, request=None) -> None:
    reason = review_refusal(user, row, current_english)
    if reason:
        raise PermissionError(reason)
    with transaction.atomic():
        row.status = TranslationStatus.REVIEWED
        row.reviewed_by = user
        row.reviewed_at = timezone.now()
        row.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        audit(
            "translation.reviewed",
            actor=user,
            target=row,
            request=request,
            key=row.key,
            language=row.language,
        )


def save_line(
    *, key: str, language: str, text: str, english: str, user, origin: str
) -> tuple[Translation, str]:
    """Create or change one line as a draft. Returns (row, "created" | "changed" | "same").

    An unchanged text over the same English is left alone (a reviewed line stays reviewed).
    """
    digest = keys.source_hash(english)
    row = Translation.objects.filter(key=key, language=language).first()
    if row and row.text == text and row.source_hash == digest:
        return row, "same"
    outcome = "changed" if row else "created"
    row = row or Translation(key=key, language=language)
    row.text = text
    row.source_text = english
    row.source_hash = digest
    row.status = TranslationStatus.DRAFT
    row.origin = origin
    row.uploaded_by = user
    row.reviewed_by = None
    row.reviewed_at = None
    row.save()
    return row, outcome
