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

# allauth works out the client IP for its sign-in and reset limits. Behind Caddy, REMOTE_ADDR is
# Caddy's own address, so read X-Forwarded-For: Caddy 2.11 replaces any client-sent value with the
# real client, giving exactly one entry. Same rule as apps.audit.services.client_ip. If a CDN or
# another proxy is ever put in front of Caddy, raise this and revisit client_ip (STATUS, PR #15).
ALLAUTH_TRUSTED_PROXY_COUNT = 1
