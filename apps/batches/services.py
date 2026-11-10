"""Mentor and admin actions on batches and learners. Each one is audited (IDs only)."""

import uuid
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import MentorResetLink, Profile, Role, User
from apps.accounts.tokens import new_token
from apps.audit.services import audit

from .models import Batch, BatchMentor, BatchStatus, Enrolment
from .scoping import batches_for

RESET_LINK_MINUTES = 60


def _deny(actor, request, target_type: str, target_id) -> None:
    audit(
        "access.denied",
        actor=actor,
        request=request,
        target_type_asked=target_type,
        target_id_asked=str(target_id),
    )
    raise PermissionDenied


def scoped_batch(user, pk: int, request=None) -> Batch:
    """The batch if this user may see it: 404 if missing, 403 (and logged) if not theirs."""
    if not Batch.objects.filter(pk=pk).exists():
        raise Http404
    batch = batches_for(user).filter(pk=pk).first()
    if batch is None:
        _deny(user, request, "Batch", pk)
    return batch


def scoped_enrolment(user, learner_id: int, request=None) -> Enrolment:
    enrolment = (
        Enrolment.objects.select_related("user", "user__profile", "batch")
        .filter(user_id=learner_id, user__role=Role.LEARNER)
        .first()
    )
    if enrolment is None:
        raise Http404
    if not batches_for(user).filter(pk=enrolment.batch_id).exists():
        _deny(user, request, "Learner", learner_id)
    return enrolment


def _next_code() -> str:
    """B02, B03, ... derived from the highest existing number."""
    numbers = [
        int(code[1:])
        for code in Batch.objects.values_list("code", flat=True)
        if code.startswith("B") and code[1:].isdigit()
    ]
    return f"B{max(numbers, default=0) + 1:02d}"


@transaction.atomic
def create_batch(mentor, data: dict, request=None) -> Batch:
    """A new batch starts closed and is assigned to its creator (architecture 5)."""
    batch = Batch.objects.create(
        code=f"tmp-{uuid.uuid4().hex[:12]}",
        name=data["name"],
        centre=data.get("centre", ""),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        seat_limit=data["seat_limit"],
    )
    batch.code = _next_code()
    batch.save(update_fields=["code", "updated_at"])
    BatchMentor.objects.create(batch=batch, mentor=mentor)
    audit("batch.created", actor=mentor, target=batch, request=request)
    return batch


def update_registration(actor, batch: Batch, data: dict, request=None) -> Batch:
    if batch.is_open_pool and actor.role != Role.ADMIN:
        raise PermissionDenied
    before = {"accepting": batch.accepting, "seat_limit": batch.seat_limit}
    batch.accepting = data["accepting"]
    batch.opens_at = data.get("opens_at")
    batch.closes_at = data.get("closes_at")
    batch.seat_limit = data["seat_limit"]
    batch.save(update_fields=["accepting", "opens_at", "closes_at", "seat_limit", "updated_at"])
    audit(
        "batch.registration_updated",
        actor=actor,
        target=batch,
        request=request,
        was_accepting=before["accepting"],
        accepting=batch.accepting,
        old_seat_limit=before["seat_limit"],
        seat_limit=batch.seat_limit,
        windowed=bool(batch.opens_at or batch.closes_at),
    )
    return batch


@transaction.atomic
def move_learner(actor, enrolment: Enrolment, target: Batch, request=None) -> Enrolment:
    """Only between batches the actor mentors (admins: any active batch)."""
    if not batches_for(actor).filter(pk=target.pk).exists():
        _deny(actor, request, "Batch", target.pk)
    if target.status != BatchStatus.ACTIVE:
        raise PermissionDenied
    old = enrolment.batch_id
    enrolment.batch = target
    enrolment.save(update_fields=["batch", "updated_at"])
    audit(
        "learner.moved",
        actor=actor,
        target=enrolment.user,
        request=request,
        from_batch=old,
        to_batch=target.pk,
    )
    return enrolment


def change_certificate_name(actor, user: User, new_name: str, request=None) -> None:
    Profile.objects.filter(user=user).update(certificate_name=new_name, updated_at=timezone.now())
    audit("learner.certificate_name_changed", actor=actor, target=user, request=request)


def issue_reset_link(actor, user: User, request=None) -> str:
    """Return the raw token. It is shown once and never stored (only its hash is)."""
    raw, hashed = new_token()
    MentorResetLink.objects.create(
        user=user,
        created_by=actor,
        token_hash=hashed,
        expires_at=timezone.now() + timedelta(minutes=RESET_LINK_MINUTES),
    )
    audit("password.reset_link_issued", actor=actor, target=user, request=request)
    return raw


@transaction.atomic
def set_auto_issue(actor, batch: Batch, value: bool, request=None) -> Batch:
    """The batch's certificate auto-issue switch (D10). Mentors set it for their own batches."""
    if batch.is_open_pool and actor.role != Role.ADMIN:
        raise PermissionDenied
    was = batch.auto_issue
    batch.auto_issue = bool(value)
    batch.save(update_fields=["auto_issue", "updated_at"])
    audit("batch.auto_issue_changed", actor=actor, target=batch, request=request, was=was, now=batch.auto_issue)  # fmt: skip
    return batch
