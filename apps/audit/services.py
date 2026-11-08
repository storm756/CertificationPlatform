from .models import AuditEvent


def client_ip(request) -> str | None:
    if request is None:
        return None
    # Caddy sets X-Forwarded-For; the left-most entry is the original client.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def audit(action: str, *, actor=None, target=None, request=None, **data) -> AuditEvent:
    """Record a domain event. Pass IDs in `data`, never names or email addresses."""
    return AuditEvent.objects.create(
        actor_id=getattr(actor, "pk", None),
        action=action,
        target_type=type(target).__name__ if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        data=data,
        ip=client_ip(request),
    )
