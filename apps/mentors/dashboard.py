"""The mentor dashboard's data for one batch (architecture §15): roster with module %, final %,
overall and status, the module heatmap, stuck learners, and who is awaiting approval.

Everything comes from `compute_results`, so it agrees with the learner's own dashboard.
"""

from datetime import timedelta

from allauth.account.models import EmailAddress
from django.db.models import Max
from django.utils import timezone

from apps.assessments.models import Attempt
from apps.batches.models import Enrolment
from apps.certificates import services as certificates
from apps.content.models import UnitProgress
from apps.results.policy import compute_results, round1

STUCK_INACTIVE_DAYS = 7
STUCK_ATTEMPTS = 3
HEAT_FAIL = 50


def _last_activity(user_ids):
    seen = {}
    for uid, at in (
        Attempt.objects.filter(user_id__in=user_ids)
        .values_list("user_id")
        .annotate(at=Max("last_saved_at"))
    ):
        seen[uid] = at
    for uid, at in (
        UnitProgress.objects.filter(user_id__in=user_ids)
        .values_list("user_id")
        .annotate(at=Max("completed_at"))
    ):
        if uid not in seen or at > seen[uid]:
            seen[uid] = at
    return seen


def status_label(enrolment, result, verified) -> str:
    if result.already_issued:
        return "certificate issued"
    if not verified:
        return "email not verified"
    if enrolment.user.status == "pending_guardian":
        return "waiting for guardian"
    if result.eligible:
        return "eligible"
    return enrolment.user.status


def batch_overview(batch, now=None) -> dict:
    now = now or timezone.now()
    enrolments = list(
        Enrolment.objects.filter(batch=batch)
        .select_related("user", "user__profile")
        .order_by("user__profile__certificate_name")
    )
    ids = [e.user_id for e in enrolments]
    results = compute_results(ids)
    verified = set(
        EmailAddress.objects.filter(user_id__in=ids, verified=True).values_list(
            "user_id", flat=True
        )
    )
    activity = _last_activity(ids)
    modules = []
    if results:
        modules = [(m.number, m.title) for m in next(iter(results.values())).modules]
    rows, stuck, awaiting = [], [], []
    for e in enrolments:
        r = results[e.user_id]
        cells = [
            {
                "number": m.number,
                "value": m.shown,
                "fail": bool(m.parts) and m.shown < HEAT_FAIL,
                "parts": bool(m.parts),
            }
            for m in r.modules
        ]
        last = activity.get(e.user_id)
        reasons = []
        idle_since = last or e.joined_at
        if idle_since < now - timedelta(days=STUCK_INACTIVE_DAYS):
            reasons.append(f"no activity for {STUCK_INACTIVE_DAYS}+ days")
        for m in r.modules:
            for p in m.parts:
                if p.attempts >= STUCK_ATTEMPTS and round1(p.best) < HEAT_FAIL:
                    reasons.append(
                        f"Module {m.number}, {p.name}: below 50% after {p.attempts} attempts"
                    )
        row = {
            "enrolment": e,
            "user": e.user,
            "name": e.user.profile.certificate_name,
            "cells": cells,
            "final": r.final_shown if r.final_attempts else None,
            "overall": r.overall_shown,
            "status": status_label(e, r, e.user_id in verified),
            "eligible": r.eligible,
            "last_activity": last,
        }
        rows.append(row)
        if reasons and e.user.status == "active":
            stuck.append({**row, "reasons": reasons})
        if r.eligible:
            awaiting.append(row)
    return {
        "rows": rows,
        "modules": modules,
        "stuck": stuck,
        "awaiting": awaiting,  # eligible and holding no certificate (§12)
        "issued_this_week": list(certificates.issued_recently(batch, now)),
    }
