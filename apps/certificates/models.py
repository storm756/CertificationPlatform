"""Issued certificates (architecture §12, D10, D28, D36).

A certificate is a snapshot: once issued, its number, verify code, snapshot and PDF never change.
Revoking changes only its status. Erasing the holder's details (DPDP) blanks the name and removes
the PDF but keeps the record, so the code printed on paper still answers on the verify page.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

VERIFY_CODE_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{10}$"  # Crockford base32, 10 characters


class CertificateStatus(models.TextChoices):
    ISSUED = "issued", "Issued"
    REVOKED = "revoked", "Revoked"


class Certificate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="certificates"
    )
    # From the global `certificate_serial` sequence: never reset, never reused (D36).
    serial = models.PositiveBigIntegerField(unique=True, editable=False)
    certificate_no = models.CharField(max_length=40, unique=True, editable=False)
    verify_code = models.CharField(max_length=10, unique=True, editable=False)
    status = models.CharField(
        max_length=10, choices=CertificateStatus.choices, default=CertificateStatus.ISSUED
    )
    snapshot = models.JSONField(editable=False)
    pdf_path = models.CharField(max_length=200, blank=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    issued_at = models.DateTimeField(editable=False)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    auto_issued = models.BooleanField(default=False, editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    revoked_reason = models.TextField(blank=True, editable=False)
    # A revoked certificate blocks a new one (§10.2) unless the admin allowed a re-issue, for
    # example to correct the printed name. The new certificate gets a new number.
    reissue_allowed = models.BooleanField(default=False, editable=False)
    holder_erased_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-serial"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status=CertificateStatus.ISSUED),
                name="one_issued_certificate_per_user",
            ),
            models.CheckConstraint(
                condition=Q(verify_code__regex=VERIFY_CODE_PATTERN),
                name="certificate_verify_code_format",
            ),
        ]

    def __str__(self):
        return self.certificate_no

    @property
    def is_issued(self) -> bool:
        return self.status == CertificateStatus.ISSUED

    @property
    def holder_erased(self) -> bool:
        return self.holder_erased_at is not None

    @property
    def grade(self) -> str:
        return self.snapshot.get("grade", "")

    @property
    def holder_name(self) -> str:
        return "" if self.holder_erased else self.snapshot.get("certificate_name", "")


class CertificateSettings(models.Model):
    """One row of admin-editable certificate settings. Changes affect new issues only."""

    nsqf_approved = models.BooleanField(
        "NSQF approved",
        default=False,
        help_text="Turn on only after the competent authority has approved the NSQF level and "
        "credits. Until then certificates say they will be shown after approval.",
    )
    nsqf_level = models.CharField("NSQF level", max_length=20, blank=True)
    nsqf_credits = models.CharField("NSQF credits", max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "certificate settings"
        verbose_name_plural = "certificate settings"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="certificate_settings_single_row"),
            models.CheckConstraint(
                condition=Q(nsqf_approved=False) | (~Q(nsqf_level="") & ~Q(nsqf_credits="")),
                name="nsqf_approved_needs_level_and_credits",
            ),
        ]

    def __str__(self):
        return "Certificate settings"

    @classmethod
    def load(cls) -> "CertificateSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.nsqf_approved and not (self.nsqf_level.strip() and self.nsqf_credits.strip()):
            raise ValidationError("Fill in the NSQF level and credits before turning this on.")
