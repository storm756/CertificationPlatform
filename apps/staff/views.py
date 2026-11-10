"""Staff pages: question editing with preview (mentor and admin), the mark-split editor and the
report page (admin only). Business rules live in services; final-pool questions are admin-only."""

import json
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from apps.accounts import email_budget
from apps.accounts.models import Role
from apps.accounts.rules import can_access_final_pool
from apps.assessments.models import AssessmentPart, AttemptItem
from apps.audit.services import audit
from apps.batches.models import Batch, Enrolment
from apps.content.models import Module
from apps.questions import formats, schemas
from apps.questions import services as qservices
from apps.questions.models import Pool, PoolLocked, Question, QuestionStatus
from apps.results import impact as impact_mod
from apps.results import insights
from apps.results.policy import compute_results


def _deny(request, **data):
    audit("access.denied", actor=request.user, request=request, path=request.path, **data)
    raise PermissionDenied


def staff_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in (Role.MENTOR, Role.ADMIN):
            _deny(request)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def admin_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != Role.ADMIN:
            _deny(request)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def visible_questions(user):
    """Final-pool questions are admin-only: a mentor's queries never include them (§5, D19)."""
    qs = Question.objects.select_related("module")
    return qs if can_access_final_pool(user) else qs.exclude(pool=Pool.FINAL)


def _question(request, pk) -> Question:
    question = get_object_or_404(Question.objects.select_related("module"), pk=pk)
    if question.pool == Pool.FINAL and not can_access_final_pool(request.user):
        _deny(request, target_type_asked="Question", target_id_asked=str(pk))
    return question


# --- questions -------------------------------------------------------------------------------------


@staff_required
def question_list(request):
    qs = visible_questions(request.user)
    module = request.GET.get("module")
    pool = request.GET.get("pool")
    status = request.GET.get("status")
    if module and module.isdigit():
        qs = qs.filter(module__number=int(module))
    if pool in (Pool.MODULE_QUIZ, Pool.PRACTICE) or (
        pool == Pool.FINAL and can_access_final_pool(request.user)
    ):
        qs = qs.filter(pool=pool)
    if status in QuestionStatus.values:
        qs = qs.filter(status=status)
    return render(
        request,
        "staff/question_list.html",
        {
            "questions": qs.order_by("stable_id")[:300],
            "modules": Module.objects.filter(kind="learning"),
            "pools": Pool.choices
            if can_access_final_pool(request.user)
            else [c for c in Pool.choices if c[0] != Pool.FINAL],  # fmt: skip
            "statuses": QuestionStatus.choices,
            "is_admin": can_access_final_pool(request.user),
        },
    )


def _allowed_pools(user):
    return [p for p in Pool.values if p != Pool.FINAL or can_access_final_pool(user)]


@staff_required
def question_edit(request, pk):
    question = _question(request, pk)
    version = question.current_version
    is_admin = can_access_final_pool(request.user)
    errors = []
    posted = request.POST if request.method == "POST" else None
    text = posted.get("body") if posted else json.dumps(version.body, indent=2, ensure_ascii=False)
    if posted:
        errors = _save_question(request, question, posted, is_admin)
        if not errors:
            return redirect("staff_question", pk=question.pk)
    return render(
        request,
        "staff/question_edit.html",
        {
            "question": question,
            "version": question.current_version,
            "body_text": text,
            "errors": errors,
            "pools": _allowed_pools(request.user),
            "is_admin": is_admin,
            "pool": (posted.get("pool") if posted else question.pool),
            "pc": (posted.get("pc") if posted else question.tags.get("pc", "")),
            "qtype": (posted.get("type") if posted else question.tags.get("type", "")),
            "live_errors": schemas.publish_errors(question.format, version.body)
            if version
            else ["no content"],  # fmt: skip
        },
    )


@transaction.atomic
def _save_question(request, question, posted, is_admin) -> list[str]:
    """Add a version from the edited JSON and update the tags and pool. Returns error messages."""
    try:
        body = json.loads(posted.get("body", ""))
    except ValueError as exc:
        return [f"The text is not valid JSON: {exc}"]
    if not isinstance(body, dict):
        return ["The question must be a JSON object."]
    pool = posted.get("pool", question.pool)
    if pool not in _allowed_pools(request.user):
        _deny(request, target_type_asked="Pool", target_id_asked=pool)
    try:
        version, created = qservices.add_version(question, body)
    except ValidationError as exc:
        return [f"{'.'.join(str(p) for p in e['loc']) or 'body'}: {e['msg']}" for e in exc.errors()]
    except ValueError as exc:
        return [str(exc)]
    question = Question.objects.select_for_update().get(pk=question.pk)
    old_pool, was_live = question.pool, question.status == QuestionStatus.LIVE
    question.tags = {**question.tags, "pc": posted.get("pc", "").strip(), "type": posted.get("type", "").strip()}  # fmt: skip
    question.pool = pool
    keep_live = is_admin and posted.get("keep_live") == "on"
    if was_live and not keep_live:
        question.status = QuestionStatus.DRAFT  # a mentor's (or default) edit goes back to draft
    try:
        question.save()
    except PoolLocked as exc:
        transaction.set_rollback(True)
        return [str(exc)]
    if was_live and keep_live:
        problems = schemas.publish_errors(question.format, version.body)
        if problems:
            transaction.set_rollback(True)
            return ["It cannot stay live yet: " + "; ".join(problems)]
    audit(
        "question.edited", actor=request.user, target=question, request=request,
        version=version.version, new_version=created, pool=pool, old_pool=old_pool,
        went_to_draft=was_live and not keep_live,
    )  # fmt: skip
    messages.success(
        request,
        "Saved as a new version."
        + (
            " The question is back in draft until an admin publishes it."
            if was_live and not keep_live
            else ""
        ),  # fmt: skip
    )
    return []


@staff_required
def question_preview(request, pk):
    """The question as a learner sees it: a fresh option map, the same projection, nothing saved."""
    question = _question(request, pk)
    version = question.current_version
    option_map = formats.make_map(question.format, version.body)
    projection = formats.project(question.format, version.body, option_map)
    return render(
        request,
        "staff/question_preview.html",
        {
            "question": question,
            "q": projection,
            "q_json": json.dumps(projection),
            "interactive": question.format != "mcq",
            "staff_hint": version.body.get("hint", ""),
            "staff_why": version.body.get("why", ""),
        },
    )


@admin_required
@require_POST
def question_publish(request, pk):
    question = _question(request, pk)
    try:
        qservices.publish(question)
    except qservices.PublishError as exc:
        messages.error(request, f"Cannot publish: {exc}")
    else:
        audit("question.published", actor=request.user, target=question, request=request, pool=question.pool)  # fmt: skip
        messages.success(request, "The question is live.")
    return redirect("staff_question", pk=question.pk)


# --- the mark-split editor (§10.4) ------------------------------------------------------------------


@admin_required
def marks_index(request):
    return render(
        request, "staff/marks_index.html", {"modules": Module.objects.filter(kind="learning")}
    )


def _proposed(module, posted):
    """(overrides, errors, parts) from the posted form. Nothing is saved here."""
    parts = list(AssessmentPart.objects.filter(module=module).order_by("pk"))
    overrides = {"parts": {}, "modules": {}}
    errors = []
    for part in parts:
        raw = posted.get(f"marks_{part.pk}", str(part.marks)).strip()
        if not raw.isdigit() or not 0 <= int(raw) <= 100:
            errors.append(f"{part.name}: marks must be a whole number from 0 to 100.")
            continue
        overrides["parts"][part.pk] = {"marks": int(raw), "counted": f"counted_{part.pk}" in posted}
    overrides["modules"][module.pk] = "module_counted" in posted
    if not errors:
        total = sum(v["marks"] for v in overrides["parts"].values() if v["counted"])
        if total > 100:
            errors.append(f"The counted marks would total {total}; they cannot exceed 100.")
    return overrides, errors, parts


@admin_required
def marks_edit(request, number):
    module = get_object_or_404(Module, number=number, kind="learning")
    posted = request.POST if request.method == "POST" else {}
    result = None
    if request.method == "POST":
        overrides, errors, parts = _proposed(module, posted)
        if not errors:
            result = impact_mod.impact(overrides)
            if posted.get("confirm") == "1":
                return _apply_marks(request, module, overrides, result)
    else:
        parts = list(AssessmentPart.objects.filter(module=module).order_by("pk"))
        errors = []
    rows = [
        {
            "part": p,
            "marks": posted.get(f"marks_{p.pk}", p.marks) if posted else p.marks,
            "counted": (f"counted_{p.pk}" in posted) if posted else p.counted,
        }
        for p in parts
    ]
    return render(
        request,
        "staff/marks_edit.html",
        {
            "module": module,
            "rows": rows,
            "module_counted": ("module_counted" in posted) if posted else module.counted,
            "errors": errors,
            "impact": result,
            "lose_names": _names(result["lose"]) if result else [],
            "gain_names": _names(result["gain"]) if result else [],
        },
    )


def _names(ids):
    from apps.accounts.models import Profile

    return list(
        Profile.objects.filter(user_id__in=ids[: impact_mod.LIST_LIMIT]).values_list(
            "certificate_name", flat=True
        )
    )


@transaction.atomic
def _apply_marks(request, module, overrides, result):
    """Apply a confirmed change. The impact shown is recomputed on this request, and audited."""
    before = {
        "module_counted": module.counted,
        "parts": {p.pk: (p.marks, p.counted) for p in AssessmentPart.objects.filter(module=module)},
    }
    module.counted = overrides["modules"][module.pk]
    module.save(update_fields=["counted", "updated_at"])
    for part in AssessmentPart.objects.select_for_update().filter(module=module):
        change = overrides["parts"].get(part.pk)
        if change:
            part.marks, part.counted = change["marks"], change["counted"]
            part.save(update_fields=["marks", "counted", "updated_at"])
    audit(
        "marks.changed", actor=request.user, target=module, request=request,
        module=module.number, was_module_counted=before["module_counted"], module_counted=module.counted,
        parts={str(k): {"was": list(before["parts"][k]), "now": [v["marks"], v["counted"]]} for k, v in overrides["parts"].items()},
        learners=result["learners"], lose=len(result["lose"]), gain=len(result["gain"]),
    )  # fmt: skip
    messages.success(
        request,
        f"Marks saved. {len(result['lose'])} learner(s) lose eligibility and {len(result['gain'])} gain it. Issued certificates are not affected.",  # fmt: skip
    )
    return redirect("staff_marks_edit", number=module.number)


# --- the admin report page (§15) --------------------------------------------------------------------

GAIN_TARGET = 25


@admin_required
def report(request):
    batches = []
    all_ids = list(Enrolment.objects.values_list("user_id", flat=True))
    results = compute_results(all_ids)
    for batch in Batch.objects.order_by("code"):
        ids = list(Enrolment.objects.filter(batch=batch).values_list("user_id", flat=True))
        gains = [g for g in (insights.knowledge_gain(u) for u in ids) if g is not None]
        batches.append(
            {
                "batch": batch,
                "registered": len(ids),
                "active": sum(1 for u in ids if results[u].active),
                "eligible": sum(1 for u in ids if results[u].eligible),
                "issued": 0,  # certificates arrive in a later stage
                "gain": (sum(gains) / len(gains)) if gains else None,
                "gain_n": len(gains),
            }
        )
    return render(
        request,
        "staff/report.html",
        {
            "batches": batches,
            "target": GAIN_TARGET,
            "items": item_statistics(),
            "email": email_budget.sent_today(),
            "email_limits": settings.EMAIL_DAILY_BUDGET,
        },
    )


def item_statistics(limit=40):
    """% correct per question across counted submitted attempts, overall and per language."""
    base = AttemptItem.objects.filter(
        attempt__status__in=("submitted", "auto_submitted"),
        attempt__counted=True,
        score__isnull=False,
    )
    overall = {
        row["question_version__question__stable_id"]: row
        for row in base.values("question_version__question__stable_id").annotate(
            avg=Avg("score"), n=Count("id")
        )
    }
    per_language = defaultdict(dict)
    for row in base.values("question_version__question__stable_id", "attempt__user__profile__preferred_language").annotate(avg=Avg("score"), n=Count("id")):  # fmt: skip
        per_language[row["question_version__question__stable_id"]][row["attempt__user__profile__preferred_language"]] = row  # fmt: skip
    rows = []
    for stable_id, row in overall.items():
        rows.append(
            {
                "id": stable_id,
                "percent": round(float(row["avg"]) * 100, 1),
                "n": row["n"],
                "languages": {
                    lang: round(float(r["avg"]) * 100, 1)
                    for lang, r in sorted(per_language[stable_id].items())
                },  # fmt: skip
            }
        )
    return sorted(rows, key=lambda r: (r["percent"], r["id"]))[:limit]
