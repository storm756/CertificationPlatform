"""Hardening shared by staging and prod (both sit behind Caddy over HTTPS)."""

from .base import env

SENTRY_DSN = env("SENTRY_DSN", "")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # the container healthcheck speaks plain HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
