"""The small daily-job runner behind `manage.py run_periodic` (D27). Not a job queue.

A job is due when today's scheduled time (PERIODIC_RUN_AT, Asia/Kolkata) has passed and its last
successful run was before it. A run missed because of a restart therefore happens once on the next
wake-up, with no pile-up. A failing job is logged and never stops the others or the loop.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .models import PeriodicRun

logger = logging.getLogger(__name__)


def _purge_unverified():
    from apps.accounts.purge import purge_stale_accounts

    counts = purge_stale_accounts()
    logger.info(
        "purge_unverified: deleted %(count)d (unverified %(unverified)d, "
        "guardian expired %(guardian_expired)d)",
        counts,
    )


# Add new daily jobs here (Stage 2 adds auto-submit of stale attempts).
JOBS = {"purge_unverified": _purge_unverified}


def scheduled_time_today(now):
    local = timezone.localtime(now)
    run_at = settings.PERIODIC_RUN_AT
    return timezone.make_aware(
        datetime.combine(local.date(), run_at), timezone.get_current_timezone()
    )


def is_due(job, now) -> bool:
    scheduled = scheduled_time_today(now)
    if now < scheduled:
        return False
    last = PeriodicRun.objects.filter(job=job).values_list("last_success_at", flat=True).first()
    return last is None or last < scheduled


def run_due(now=None, jobs=None) -> dict:
    """Run every due job once. Returns {job: "ok" | "failed" | "skipped"}."""
    now = now or timezone.now()
    results = {}
    for name, func in (JOBS if jobs is None else jobs).items():
        if not is_due(name, now):
            results[name] = "skipped"
            continue
        try:
            func()
        except Exception:
            logger.exception("periodic job %s failed; it will be retried on the next wake-up", name)
            results[name] = "failed"
            continue
        PeriodicRun.objects.update_or_create(job=name, defaults={"last_success_at": now})
        results[name] = "ok"
    return results
