from apps.accounts.models import Role

from .models import Batch


def batches_for(user):
    """Every mentor-facing query goes through here: admins see all, mentors see their own."""
    if not user.is_authenticated:
        return Batch.objects.none()
    if user.role == Role.ADMIN:
        return Batch.objects.all()
    if user.role == Role.MENTOR:
        return Batch.objects.filter(batch_mentors__mentor=user)
    return Batch.objects.none()
