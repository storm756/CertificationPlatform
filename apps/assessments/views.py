"""Assessment pages for learners. Thin: the rules are in services.py.

What these views send to the browser is built from `client_projection()` (the question) and a few
plain fields (position, answered, flagged). They never pass an AttemptItem, a QuestionVersion body
or an option map to a template, so a key can't leak by a template mistake.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.certificates.services import auto_issue_after_submit
from apps.questions import formats
from apps.questions.models import QuestionImage
from apps.questions.projections import client_projection
from apps.results import insights
from apps.results.policy import PASS_MARK

from . import examsets, programme, services
from .models import AssessmentPart, Attempt, AttemptStatus


def learner_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != Role.LEARNER:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _own_attempt(request, pk) -> Attempt:
    return get_object_or_404(
        Attempt.objects.select_related("part__module", "programme_assessment"),
        pk=pk,
        user=request.user,
    )


def _items(attempt):
    return attempt.items.select_related("question_version")


def _palette(attempt, current):
    return [
        {
            "number": item.position,
            "answered": item.answered,
            "flagged": bool((item.response or {}).get("flag")),
            "current": item.position == current,
        }
        for item in _items(attempt)
    ]


def _first_unanswered(attempt) -> int:
    for item in _items(attempt):
        if not item.answered:
            return item.position
    return 1


def _question_context(attempt, position):
    item = get_object_or_404(_items(attempt), position=position)
    version = item.question_version
    total = attempt.items.count()
    projection = client_projection(item.format, version.body, item.option_map, item.response)
    context = {
        "attempt": attempt,
        "position": position,
        "total": total,
        "q": projection,
        "chosen": (item.response or {}).get("choice"),
        "flagged": bool((item.response or {}).get("flag")),
        "prev_pos": position - 1 if position > 1 else None,
        "next_pos": position + 1 if position < total else None,
        "palette": _palette(attempt, position),
        "interactive": item.format != "mcq",
    }
    if item.format != "mcq":
        context["q_json"] = json.dumps(projection)  # the allow-listed projection, as an attribute
        context["data_url"] = reverse("attempt_question_data", args=[attempt.pk, position])
        if item.format == "hotspot" and projection["image"]["available"]:
            context["image_url"] = reverse("attempt_image", args=[attempt.pk, position])
    return context


# --- intro, start ------------------------------------------------------------------------------


@learner_required
def intro(request, part_id):
    part = get_object_or_404(
        AssessmentPart.objects.select_related("module"), pk=part_id, is_published=True
    )
    attempts = list(Attempt.objects.filter(user=request.user, part=part).order_by("-number"))
    open_attempt = next((a for a in attempts if a.is_open), None)
    best = max((a.score for a in attempts if a.counted and a.score is not None), default=None)
    return render(
        request,
        "assessments/intro.html",
        {
            "part": part,
            "attempts": attempts,
            "open_attempt": open_attempt,
            "best": best,
            "allowance": services.attempt_allowance(part.max_attempts, len(attempts)),
            "pass_mark": PASS_MARK,
            "question_count": part.draw_n if part.selection == "draw" else None,
        },
    )


@learner_required
@require_POST
def start(request, part_id):
    part = get_object_or_404(AssessmentPart, pk=part_id)
    try:
        attempt, _created = services.start(request.user, part)
    except services.PartNotAvailable as exc:
        messages.error(request, str(exc))
        return redirect("assess_intro", part_id=part_id) if part.is_published else redirect("start")
    return redirect("attempt_page", pk=attempt.pk)


# --- the attempt -------------------------------------------------------------------------------


@learner_required
def attempt_page(request, pk, position=None):
    """The attempt. Resumes on the first unanswered question. A full page, or just the question
    panel for an htmx request."""
    attempt = _own_attempt(request, pk)
    if not attempt.is_open:
        return redirect("attempt_result", pk=attempt.pk)
    position = position or _first_unanswered(attempt)
    context = _question_context(attempt, position)
    if request.headers.get("HX-Request"):
        return render(request, "assessments/_question_panel.html", {**context, "oob": True})
    return render(request, "assessments/attempt.html", context)


def _saved_response(request, attempt, position, status=200):
    """The save pill, plus the question map as an out-of-band swap. Never a score."""
    attempt = _own_attempt(request, attempt.pk)
    response = render(
        request,
        "assessments/_save_status.html",
        {"attempt": attempt, "palette": _palette(attempt, position), "state": "saved"},
        status=status,
    )
    response["X-Answer-Saved"] = "1"  # the browser shows "Saved" only when it sees this
    response["Cache-Control"] = "no-store"
    return response


@learner_required
@require_POST
def answer(request, pk):
    attempt = _own_attempt(request, pk)
    if not request.headers.get("HX-Request"):
        # No JavaScript: save, then show the same question again.
        try:
            position = int(request.POST.get("position", ""))
            services.save_answer(
                attempt.pk,
                request.user,
                position,
                choice=request.POST.get("choice") or None,
                flag=("flag" in request.POST) if "flag_present" in request.POST else None,
            )
        except (ValueError, services.AttemptError):
            return redirect("attempt_page", pk=attempt.pk)
        return redirect("attempt_question", pk=attempt.pk, position=position)
    try:
        position = int(request.POST.get("position", ""))
    except ValueError:
        return HttpResponse(status=400)
    flag = ("flag" in request.POST) if "flag_present" in request.POST else None
    response = None
    if request.POST.get("response"):  # an interactive question's whole answer, as JSON of tokens
        raw = request.POST["response"]
        if len(raw) > 20000:
            return HttpResponse(status=400)
        try:
            response = json.loads(raw)
        except ValueError:
            return HttpResponse(status=400)
        if not isinstance(response, dict):
            return HttpResponse(status=400)
    try:
        services.save_answer(
            attempt.pk,
            request.user,
            position,
            choice=request.POST.get("choice") or None,
            response=response,
            flag=flag,
        )
    except services.AttemptClosed:
        response = HttpResponse(status=409)
        response["HX-Redirect"] = reverse("attempt_result", args=[attempt.pk])
        return response
    except services.InvalidAnswer:
        return HttpResponse(status=400)
    return _saved_response(request, attempt, position)


@learner_required
def review(request, pk):
    attempt = _own_attempt(request, pk)
    if not attempt.is_open:
        return redirect("attempt_result", pk=attempt.pk)
    items = []
    for item in _items(attempt):
        items.append(
            {
                "position": item.position,
                "stem": formats.label(item.question_version.body),
                "answered": item.answered,
                "flagged": bool((item.response or {}).get("flag")),
            }
        )
    missing = [i for i in items if not i["answered"]]
    return render(
        request,
        "assessments/review.html",
        {
            "attempt": attempt,
            "items": items,
            "missing": len(missing),
            "flagged": sum(1 for i in items if i["flagged"]),
            "total": len(items),
        },
    )


@learner_required
@require_POST
def submit(request, pk):
    attempt = _own_attempt(request, pk)
    closed = services.submit(attempt.pk, request.user.pk)
    if closed.just_closed:  # a double tap closes the attempt once, so this runs once
        auto_issue_after_submit(request.user, request)  # never raises; §12 auto-issue
    return redirect("attempt_result", pk=attempt.pk)


# --- the result --------------------------------------------------------------------------------


@learner_required
def result(request, pk):
    """Score, right/wrong and the hint for each question (D13).

    No option text is shown, not even the learner's own pick: for a right answer that text is
    the correct option, so repeating it would reveal the key.
    """
    attempt = _own_attempt(request, pk)
    if attempt.status == AttemptStatus.IN_PROGRESS:
        return redirect("attempt_page", pk=attempt.pk)
    if attempt.programme_assessment_id:
        return _programme_result(request, attempt)
    rows = []
    for item in _items(attempt):
        body = item.question_version.body
        score = item.score if item.score is not None else 0
        rows.append(
            {
                "position": item.position,
                "stem": formats.label(body),
                "right": score == 1,
                "partial": 0 < score < 1,
                "answered": item.answered,
                "hint": body.get("hint", ""),
                "gated": item.gate_flag,
            }
        )
    return render(
        request,
        "assessments/result.html",
        {
            "attempt": attempt,
            "part": attempt.part,
            "rows": rows,
            "score_text": f"{attempt.score}%",
            "passed": attempt.counted and attempt.score is not None and attempt.score >= PASS_MARK,
            "pass_mark": PASS_MARK,
            "auto": attempt.status == AttemptStatus.AUTO_SUBMITTED,
            "allowance": services.attempt_allowance(
                attempt.part.max_attempts,
                Attempt.objects.filter(user=request.user, part=attempt.part).count(),
            ),
        },
    )


@learner_required
def question_data(request, pk, position):
    """The question as JSON for the TypeScript renderer: the same allow-listed projection, nothing
    more. Chat uses it to fetch the next step after each answer is saved."""
    attempt = _own_attempt(request, pk)
    if not attempt.is_open:
        return JsonResponse({"closed": True}, status=409)
    context = _question_context(attempt, position)
    response = JsonResponse(context["q"])
    response["Cache-Control"] = "no-store"
    return response


@learner_required
def image(request, pk, position):
    """A hotspot's picture, only for the learner who has this item in an attempt of their own."""
    attempt = _own_attempt(request, pk)
    item = get_object_or_404(_items(attempt), position=position, format="hotspot")
    image_id = item.question_version.body.get("image_id")
    picture = QuestionImage.objects.filter(pk=image_id).first()
    if picture is None:
        raise Http404
    response = FileResponse(picture.file.open("rb"), content_type=f"image/{picture.format}")
    response["Cache-Control"] = "private, max-age=3600"
    return response


# --- the final exam and the pre-test (architecture §11) ------------------------------------------


def _programme_result(request, attempt):
    """Final: overall % and per-module bands only. Pre-test: the score only. Never a hint, a
    right/wrong mark or an answer, so a learner cannot learn individual answers (§9.5, §11)."""
    kind = attempt.programme_assessment.kind
    context = {
        "attempt": attempt,
        "kind": kind,
        "score": attempt.score,
        "score_text": f"{attempt.score}%",
        "passed": attempt.counted and attempt.score is not None and attempt.score >= PASS_MARK,
        "pass_mark": PASS_MARK,
        "auto": attempt.status == AttemptStatus.AUTO_SUBMITTED,
        "bands": insights.final_bands(attempt) if kind == "final" else [],
        "allowance": services.attempt_allowance(
            attempt.programme_assessment.max_attempts,
            Attempt.objects.filter(
                user=request.user, programme_assessment=attempt.programme_assessment
            ).count(),
        ),
    }
    return render(request, "assessments/programme_result.html", context)


@learner_required
def programme_intro(request, kind):
    if kind not in ("final", "pretest"):
        raise Http404
    assessment = programme.get_assessment(kind)
    attempts = list(
        Attempt.objects.filter(user=request.user, programme_assessment=assessment).order_by(
            "-number"
        )
    )
    reasons = programme.final_locked_reasons(request.user) if kind == "final" else []
    done = kind == "pretest" and any(not a.is_open for a in attempts)
    return render(
        request,
        "assessments/programme_intro.html",
        {
            "kind": kind, "assessment": assessment, "attempts": attempts, "reasons": reasons,
            "open_attempt": next((a for a in attempts if a.is_open), None), "done": done,
            "available": programme.pretest_available(request.user),
            "cooldown_until": programme.cooldown_until(request.user) if kind == "final" else None,
            "unavailable_reason": examsets.unavailable_reason(request.user),
            "allowance": services.attempt_allowance(assessment.max_attempts if kind == "final" else None, len(attempts)),
            "pass_mark": PASS_MARK,
        },
    )  # fmt: skip


@learner_required
@require_POST
def programme_start(request, kind):
    if kind not in ("final", "pretest"):
        raise Http404
    try:
        attempt, _ = programme.start_programme(request.user, kind)
    except programme.Locked as exc:
        for reason in exc.reasons:
            messages.error(request, reason)
        return redirect("programme_intro", kind=kind)
    except services.PartNotAvailable as exc:
        messages.error(request, str(exc))
        return redirect("programme_intro", kind=kind)
    return redirect("attempt_page", pk=attempt.pk)
