"""Gunicorn settings for the web container (Dockerfile CMD: gunicorn -c config/gunicorn.conf.py).

Same bind, workers and stdout/stderr logging as before, plus one change (security audit L2): every
access-log and error-log line passes through apps.core.redact, so one-time links such as
/reset/<token>/ or /accounts/password/reset/key/<key>/ are written as /reset/***/.
"""

import os
import sys

from gunicorn.glogging import Logger

# Gunicorn reads this file before it adds the app directory to sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.core.redact import RedactTokensFilter  # noqa: E402

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
accesslog = "-"
errorlog = "-"


class RedactingLogger(Logger):
    """Gunicorn's logger with the token filter on every handler, also after a reopen (HUP)."""

    def setup(self, cfg):
        super().setup(cfg)
        for log in (self.access_log, self.error_log):
            for handler in log.handlers:
                if not any(isinstance(f, RedactTokensFilter) for f in handler.filters):
                    handler.addFilter(RedactTokensFilter())


logger_class = RedactingLogger
