from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"  # Mailpit in compose.dev.yml
