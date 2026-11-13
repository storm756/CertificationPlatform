from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

CENTRE_CODE_PATTERN = r"^[A-Z0-9]{2,6}$"
centre_code_validator = RegexValidator(
    CENTRE_CODE_PATTERN, "Use 2 to 6 capital letters or digits, for example SAKEC."
)


def default_centre_code() -> str:
    return settings.CERTIFICATE_DEFAULT_CENTRE


class BatchStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class Batch(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    centre = models.CharField(max_length=120, blank=True)
    # Printed in the certificate number (D36). Admins set it; a new batch gets the default.
    centre_code = models.CharField(
        max_length=6,
        default=default_centre_code,
        validators=[centre_code_validator],
        help_text="2 to 6 capital letters or digits. It is part of every certificate number "
        "issued to this batch, e.g. CCFR-2026-SAKEC-000001.",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # Registration is closed by default (D9): nothing accepts sign-ups until someone opens it.
    accepting = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    seat_limit = models.PositiveIntegerField(default=40)
    is_open_pool = models.BooleanField(default=False)
    auto_issue = models.BooleanField(default=False)
    # The final exam set this batch sits (admin-only, audited). Only a released set can be assigned.
    exam_set = models.ForeignKey(
        "assessments.ExamSet",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="batches",
    )
    status = models.CharField(
        max_length=10, choices=BatchStatus.choices, default=BatchStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "batches"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_open_pool"],
                condition=Q(is_open_pool=True),
                name="only_one_open_pool",
            ),
            models.CheckConstraint(
                condition=Q(centre_code__regex=CENTRE_CODE_PATTERN),
                name="batch_centre_code_format",
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"


class BatchMentor(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="batch_mentors")
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentored"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "mentor"], name="unique_batch_mentor")
        ]

    def __str__(self):
        return f"{self.mentor_id} mentors {self.batch_id}"


class Enrolment(models.Model):
    """One current batch per learner; the history of moves lives in the audit log."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrolment"
    )
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="enrolments")
    joined_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"user {self.user_id} in batch {self.batch_id}"
