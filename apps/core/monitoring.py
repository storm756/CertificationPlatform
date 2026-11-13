"""Dead-man pings (architecture §17 monitoring, Stage 10).

A heartbeat service (for example Healthchecks.io) expects a GET to a secret URL on a schedule and
alerts a person when one is missing, or when "<url>/fail" arrives. The `tasks` loop pings after
every wake-up (every 10 minutes). Nothing is sent but the GET itself: no body, no personal data.
Off when the URL is empty. A failing ping is logged and never stops the caller.
"""

import logging
import urllib.request

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


def ping(url: str, ok: bool = True) -> bool:
    if not url:
        return False
    target = url.rstrip("/") + ("" if ok else "/fail")
    try:
        with urllib.request.urlopen(target, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            response.read(0)
        return True
    except Exception:  # the network or the pinger is down: never break the job that pings
        logger.warning("heartbeat ping failed", exc_info=True)
        return False
