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
    """Stage 0: lower-case only. Stage 1 adds the Gmail dot / +tag rule behind a setting."""
    return email.strip().lower()


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
