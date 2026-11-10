from ._hosted import *  # noqa: F403
from .base import *  # noqa: F403
from .sentry import init_sentry

EMAIL_NORMALISE_ALIASES = True  # Gmail dots and +tags count as one address
SECURE_HSTS_SECONDS = 31536000
init_sentry(SENTRY_DSN, environment="prod")  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # staging is also HTTPS-only
SILENCED_SYSTEM_CHECKS = ["security.W021"]  # HSTS preload is a deliberate, irreversible step
