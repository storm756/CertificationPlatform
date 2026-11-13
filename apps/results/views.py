"""The learner's My progress dashboard (architecture §15, laid out like the prototype's dashboard).

Everything shown is computed by `compute_results`, so it always agrees with eligibility.
"""

from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.assessments import examsets, programme
from apps.assessments.models import Attempt, AttemptStatus, ProgrammeAssessmentKind
from apps.certificates import services as certificates
from apps.content import services as content
from apps.results import insights
from apps.results.policy import FINAL_PASS, compute_results, round1
from apps.translations.pages import learning_lookup


def _final_bands(user):
    last = (
        Attempt.objects.filter(
            user=user, status__in=(AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED),
            programme_assessment__kind=ProgrammeAssessmentKind.FINAL,
        ).order_by("-number").first()
    )  # fmt: skip
    return insights.final_bands(last) if last else []


def journey(result, final_state) -> list[dict]:
    """The strip: pre-test, modules, mock, final, certificate, each done / next / waiting."""
    steps = [
        (_("Pre-test"), result.pretest_done),
        (_("Modules"), result.parts_all_answered),
        (_("Practice mock"), None),
        (_("Final"), result.final_passed),
        (_("Certificate"), result.already_issued),
    ]
    out, marked_next = [], False
    for label, done in steps:
        state = "optional" if done is None else "done" if done else "todo"
        if state == "todo" and not marked_next:
            state, marked_next = "next", True
        out.append({"label": label, "state": state})
    return out


def whats_left(result, user, pretest_ready=True) -> dict:
    """Things still to do first, finished ones after (collapsed in the page)."""
    todo, done = [], []
    pre = {
        "text": _("Take the short pre-test"),
        "href": reverse("programme_intro", args=["pretest"]) if pretest_ready else None,
        "detail": None if pretest_ready else _("not available yet"),
        "done": result.pretest_done,
    }
    (done if pre["done"] else todo).append(pre)
    for module in result.modules:
        for part in module.parts:
            item = {
                "text": _("Module %(number)s: %(part)s")
                % {"number": module.number, "part": part.name},
                "href": reverse("assess_intro", args=[part.part_id]),
                "done": part.answered,
                "detail": _("best %(score)s%%") % {"score": round1(part.best)}
                if part.attempts
                else _("not started"),
            }
            (done if item["done"] else todo).append(item)
    return {"todo": todo, "done": done}


def _localise_titles(result) -> None:
    """Module titles in the page language (drafts allowed: learning text). Display only: the
    result is not stored. Part names are assessment text and stay as they are (D24)."""
    lookup = learning_lookup(extra_keys=[f"mod:{m.number}:title" for m in result.modules])
    for m in result.modules:
        if m.title:
            m.title = lookup.get(f"mod:{m.number}:title", m.title)


def dashboard(request):
    user = request.user
    result = compute_results([user.pk])[user.pk]
    _localise_titles(result)
    pretest_ready = programme.pretest_available(user)
    # the same rules start_programme applies: course setup, pre-test, every part answered
    final_reasons = programme.final_locked_reasons(user)
    final_open = not final_reasons
    cooldown = programme.cooldown_until(user) if final_open else None
    has_final = result.final_attempts > 0
    bands = _final_bands(user) if has_final else []
    cert = certificates.current_certificate(user)
    cert_state = certificates.certificate_state(cert, result)
    state = (
        "certified" if cert_state == "issued"
        else "eligible" if result.eligible
        else "unlocked" if result.final_unlocked
        else "new" if not any(p.attempts for m in result.modules for p in m.parts) and not result.pretest_done
        else "midway"
    )  # fmt: skip
    return render(
        request,
        "progress/dashboard.html",
        {
            "result": result,
            "state": state,
            "cert": cert,
            "cert_state": cert_state,
            "journey": journey(result, state),
            "left": whats_left(result, user, pretest_ready),
            "final_reasons": final_reasons,
            "final_open": final_open,
            "cooldown_until": cooldown,
            "unavailable_reason": examsets.unavailable_reason(user),
            "final_bands": bands,
            "final_pass": FINAL_PASS,
            "weakest": insights.weakest_pcs(user),
            "hours": content.hours_for(user),
            "pretest_available": pretest_ready,
            "modules": [
                {"m": m, "href": reverse("learn_module", args=[m.number])} for m in result.modules
            ],
        },
    )
