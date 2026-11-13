"""Content translations (architecture §14, D7, D24).

One row per key and language. The row remembers the English it was translated from
(`source_text`, `source_hash`); when the English changes the row is *stale* and English is shown
until a new translation is uploaded and reviewed. UI strings are gettext (.po), not this table.
"""

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

TRANSLATED_LANGUAGES = ("hi", "mr", "gu")


class TranslationLanguage(models.TextChoices):
    HINDI = "hi", "Hindi"
    MARATHI = "mr", "Marathi"
    GUJARATI = "gu", "Gujarati"


class TranslationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    REVIEWED = "reviewed", "Reviewed"


class Translation(models.Model):
    key = models.CharField(max_length=200)
    language = models.CharField(max_length=5, choices=TranslationLanguage.choices)
    text = models.TextField()
    source_text = models.TextField()  # the English this was translated from
    source_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=10, choices=TranslationStatus.choices, default=TranslationStatus.DRAFT
    )
    origin = models.CharField(max_length=40, blank=True)  # e.g. "prototype", "sheet", "xlsx"
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["key", "language"]
        constraints = [
            models.UniqueConstraint(fields=["key", "language"], name="translation_key_language"),
            models.CheckConstraint(
                condition=~models.Q(status="reviewed") | models.Q(reviewed_by__isnull=False),
                name="translation_reviewed_has_reviewer",
            ),
        ]
        permissions = [
            ("upload_translations", "Translator: upload translation sheets"),
            ("review_hi", "Reviewer: Hindi"),
            ("review_mr", "Reviewer: Marathi"),
            ("review_gu", "Reviewer: Gujarati"),
        ]

    def __str__(self):
        return f"{self.key} [{self.language}] ({self.status})"
