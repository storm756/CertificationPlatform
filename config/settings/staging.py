from ._hosted import *  # noqa: F403
from .base import *  # noqa: F403
from .sentry import init_sentry

SECURE_HSTS_SECONDS = 300  # short while we are still testing
init_sentry(SENTRY_DSN, environment="staging")  # noqa: F405
