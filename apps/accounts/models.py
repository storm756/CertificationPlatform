from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Role(models.TextChoices):
    LEARNER = "learner", "Learner"
    MENTOR = "mentor", "Mentor"
    ADMIN = "admin", "Admin"


class UserStatus(models.TextChoices):
    PENDING_GUARDIAN = "pending_guardian", "Waiting for guardian"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


def normalise_email(email: str) -> str:
    """Lower-case. With EMAIL_NORMALISE_ALIASES (on in prod, off on staging) also fold Gmail
    dots, `+tag` and googlemail.com, so one person cannot register twice (architecture 7.2)."""
    email = email.strip().lower()
    if not getattr(settings, "EMAIL_NORMALISE_ALIASES", False) or "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.ADMIN)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff=True and is_superuser=True")
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user: email is the login. No username."""

    email = models.EmailField(unique=True)
    email_normalized = models.EmailField(unique=True, editable=False)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.LEARNER)
    status = models.CharField(max_length=20, choices=UserStatus.choices, default=UserStatus.ACTIVE)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def save(self, *args, **kwargs):
        self.email_normalized = normalise_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    HINDI = "hi", "हिन्दी"
    MARATHI = "mr", "मराठी"
    GUJARATI = "gu", "ગુજરાતી"


class Profile(models.Model):
    """Erasable personal data, kept apart from the login record."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    certificate_name = models.CharField(max_length=120)
    date_of_birth = models.DateField()
    preferred_language = models.CharField(
        max_length=5, choices=Language.choices, default=Language.ENGLISH
    )
    phone = models.CharField(max_length=20, blank=True)  # optional, unused for now
    # Set when a mentor's one-time link was used; drives the banner and the email-change block.
    mentor_reset_at = models.DateTimeField(null=True, blank=True)
    mentor_reset_notice = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of user {self.user_id}"


class ConsentRecord(models.Model):
    """Append-only: a consent is never edited, a new row is added instead."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    notice_version = models.CharField(max_length=20)
    purpose = models.CharField(max_length=60)
    given = models.BooleanField()
    at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.purpose} v{self.notice_version} user {self.user_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Consent records are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Consent records are append-only")


class GuardianConsent(models.Model):
    """Guardian consent for 16-17-year-olds. The method is pending CyberPeace legal (D16), so
    everything about it lives here and in apps/accounts/guardian.py."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="guardian_consent")
    guardian_name = models.CharField(max_length=120)
    guardian_email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_name = models.CharField(max_length=120, blank=True)
    declaration_text_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Guardian consent for user {self.user_id}"


class MentorResetLink(models.Model):
    """One-time password-reset link a mentor hands over in person (architecture 7.4)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mentor_reset_links")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reset link for user {self.user_id}"


class EmailLog(models.Model):
    """One row per email sent; drives the per-address limit and the daily budgets (7.2)."""

    kind = models.CharField(max_length=20, db_index=True)
    address_hash = models.CharField(max_length=64, db_index=True)  # sha256, not the address
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.kind} at {self.sent_at}"
