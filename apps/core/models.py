from django.db import models


class PeriodicRun(models.Model):
    """When each daily job last succeeded, so a restart catches up exactly once (D27)."""

    job = models.CharField(max_length=60, unique=True)
    last_success_at = models.DateTimeField()

    def __str__(self):
        return f"{self.job} at {self.last_success_at:%Y-%m-%d %H:%M}"
