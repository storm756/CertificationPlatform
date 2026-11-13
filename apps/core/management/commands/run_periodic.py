import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core import periodic
from apps.core.monitoring import ping

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Wake every 10 minutes and run each daily job that is due (D27). Runs until stopped."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=600, help="Seconds between wake-ups.")
        parser.add_argument("--once", action="store_true", help="Check once and exit.")

    def handle(self, *args, interval, once, **options):
        logger.info("run_periodic started; checking every %s seconds", interval)
        while True:
            healthy = False
            try:
                close_old_connections()
                results = periodic.run_due()
                ran = {name: r for name, r in results.items() if r != "skipped"}
                if ran:
                    logger.info("run_periodic: %s", ran)
                healthy = "failed" not in results.values()
            except Exception:
                # E.g. the database is briefly down. Keep the loop alive and try again.
                logger.exception("run_periodic wake-up failed")
            # A missing ping means the loop is dead; "/fail" means a job or the wake-up failed.
            ping(settings.TASKS_PING_URL, ok=healthy)
            if once:
                return
            time.sleep(interval)
