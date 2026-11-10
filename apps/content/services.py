"""Content rules (architecture §8, §13.1): versions, publish/restore, completion, hours, checks.

Business rules live here, not in views or templates.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Max, Sum
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.rules import may_track_time
from apps.audit.services import audit

from .blocks import validate_blocks
from .models import (
    TimeLog,
    Unit,
    UnitProgress,
    UnitType,
    UnitVersion,
    VersionSource,
    VersionStatus,
)

ACTIVE_WINDOW = timedelta(minutes=5)  # a heartbeat counts only after a recent server interaction
BEAT_SECONDS = 30
DAILY_CAP_SECONDS = getattr(settings, "TIMELOG_DAILY_CAP_SECONDS", 6 * 3600)


# --- versions ------------------------------------------------------------------------------------


def add_version(unit: Unit, title: str, blocks, *, source: str, author=None) -> UnitVersion:
    """A new draft version. Blocks are validated first; an invalid draft is never stored."""
    clean = validate_blocks(blocks)
    with transaction.atomic():
        Unit.objects.select_for_update().get(pk=unit.pk)
        last = unit.versions.aggregate(n=Max("version"))["n"] or 0
        return UnitVersion.objects.create(
            unit=unit,
            version=last + 1,
            title=" ".join(title.split())[:200] or unit.slug,
            blocks=clean,
            source=source,
            author=author,
        )


def can_publish(user) -> bool:
    """Admins, or a mentor given the "Content publisher" permission (§13.1)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.role == Role.ADMIN:
        return True
    return user.role == Role.MENTOR and user.has_perm("content.publish_unit")


@transaction.atomic
def publish(version: UnitVersion, user, *, request=None, system=False) -> UnitVersion:
    """Publish a draft. The previously published version becomes superseded (kept for restore)."""
    if not system and not can_publish(user):
        raise PermissionDenied("Only an admin or a content publisher can publish.")
    version = UnitVersion.objects.select_for_update().get(pk=version.pk)
    if version.status == VersionStatus.PUBLISHED:
        return version
    if version.status != VersionStatus.DRAFT:
        raise ValueError("Only a draft can be published. Restore an older version instead.")
    validate_blocks(version.blocks)
    UnitVersion.objects.filter(unit=version.unit, status=VersionStatus.PUBLISHED).update(
        status=VersionStatus.SUPERSEDED
    )
    version.status = VersionStatus.PUBLISHED
    version.published_by = None if system else user
    version.published_at = timezone.now()
    version.save(update_fields=["status", "published_by", "published_at", "updated_at"])
    audit(
        "content.published",
        actor=None if system else user,
        target=version.unit,
        request=request,
        version=version.version,
    )
    return version


@transaction.atomic
def restore(version: UnitVersion, user, *, request=None) -> UnitVersion:
    """Bring back an earlier version: a new version with its text, published at once."""
    if not can_publish(user):
        raise PermissionDenied("Only an admin or a content publisher can restore.")
    copy = add_version(
        version.unit, version.title, version.blocks, source=VersionSource.RESTORE, author=user
    )
    audit(
        "content.restored",
        actor=user,
        target=version.unit,
        request=request,
        from_version=version.version,
    )
    return publish(copy, user, request=request)


def published_units(module):
    """(unit, published version) for every unit of a module that has one, in order."""
    units = list(module.units.order_by("order", "pk"))
    versions = {
        v.unit_id: v
        for v in UnitVersion.objects.filter(unit__in=units, status=VersionStatus.PUBLISHED)
    }
    return [(u, versions[u.pk]) for u in units if u.pk in versions]


# --- completion (§8.3) -----------------------------------------------------------------------


def completed_unit_ids(user, units) -> set[int]:
    if not user.is_authenticated or user.role != Role.LEARNER:
        return set()
    return set(
        UnitProgress.objects.filter(user=user, unit__in=units).values_list("unit_id", flat=True)
    )


MANUAL_OK = {UnitType.READING, UnitType.VIDEO}


def complete(user, unit: Unit, *, how: str) -> bool:
    """Record that a learner finished a unit. Returns True the first time.

    `how` says what happened, and must fit the unit type (§8.3):
    reading → "end" (scrolled to the end) or "button"; video → "watched" (80%) or "button" when
    the film is not available yet; handout → "opened"; check → "attempted"; practice → "submitted".
    """
    if not user.is_authenticated or user.role != Role.LEARNER:
        return False
    allowed = {
        UnitType.READING: {"end", "button"},
        UnitType.VIDEO: {"watched", "button"},
        UnitType.HANDOUT: {"opened"},
        UnitType.CHECK: {"attempted"},
        UnitType.PRACTICE_QUIZ: {"submitted"},
    }[unit.type]
    if how not in allowed:
        raise ValueError(f"A {unit.type} unit does not complete by {how}.")
    _, created = UnitProgress.objects.get_or_create(
        user=user, unit=unit, defaults={"completed_at": timezone.now()}
    )
    return created


def module_completion(user, module) -> tuple[int, int]:
    units = [u for u, _ in published_units(module)]
    done = len(completed_unit_ids(user, units))
    return done, len(units)


# --- hours: the adult-only heartbeat (§8.3, D16) -------------------------------------------------


def touch(session) -> None:
    """A server-side interaction happened (a page, a check, a completion)."""
    session["learn_active_at"] = timezone.now().timestamp()


def heartbeat(user, unit: Unit, session, now=None) -> int:
    """Count up to 30 seconds of engaged time. Returns the seconds added (0 if not counted).

    Nothing is recorded for under-18s or unknown ages. A beat counts only if the learner did
    something on the server in the last 5 minutes, at most once every 25 seconds per unit, and
    within the caps: twice the unit's nominal minutes per day, and a daily total.
    """
    now = now or timezone.now()
    today = timezone.localdate(now)
    if not user.is_authenticated or user.role != Role.LEARNER or not may_track_time(user, today):
        return 0
    active = session.get("learn_active_at")
    if not active or now.timestamp() - active > ACTIVE_WINDOW.total_seconds():
        return 0
    key = f"learn_beat_{unit.pk}"
    last = session.get(key)
    if last and now.timestamp() - last < BEAT_SECONDS - 5:
        return 0
    session[key] = now.timestamp()
    with transaction.atomic():
        row, _ = TimeLog.objects.select_for_update().get_or_create(
            user=user, unit=unit, date=today, defaults={"seconds": 0}
        )
        unit_cap = 2 * unit.nominal_minutes * 60
        day_total = (
            TimeLog.objects.filter(user=user, date=today).aggregate(s=Sum("seconds"))["s"] or 0
        )
        add = max(0, min(BEAT_SECONDS, unit_cap - row.seconds, DAILY_CAP_SECONDS - day_total))
        if add:
            TimeLog.objects.filter(pk=row.pk).update(seconds=F("seconds") + add)
    return add


def hours_for(user) -> dict:
    """Engaged time (estimated) for adults; nominal minutes of completed units for under-18s."""
    if may_track_time(user, timezone.localdate()):
        seconds = TimeLog.objects.filter(user=user).aggregate(s=Sum("seconds"))["s"] or 0
        return {"kind": "engaged", "minutes": seconds // 60}
    minutes = (
        UnitProgress.objects.filter(user=user).aggregate(m=Sum("unit__nominal_minutes"))["m"] or 0
    )
    return {"kind": "nominal", "minutes": minutes}
