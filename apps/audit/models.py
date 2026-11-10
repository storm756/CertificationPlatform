from django.db import models


class AuditEvent(models.Model):
    """Append-only record of domain events. `data` holds IDs, never names or emails (DPDP)."""

    actor_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=60, db_index=True)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=60, blank=True)
    data = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.target_type}:{self.target_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Audit events are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only")
