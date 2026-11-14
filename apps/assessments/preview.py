"""Read-only staff preview of assessments (pilot fixes).

An admin can look at what a module part, the pre-test or the final would contain. Nothing is
saved: no Attempt, no AttemptItem, no result, no eligibility change, no certificate, no audit row.
The page is built from `client_projection()` with a throwaway option map, so it shows the same
words a learner sees and never the correct option. Mentors get no preview (final questions must
not reach learners through mentors), only a friendly page.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.questions import formats
from apps.questions.projections import client_projection

from . import services
from .models import AssessmentPart, ExamSet, ProgrammeAssessmentKind
from .rules import live_questions


def _project(version) -> dict:
    """One question as a learner would see its words. No key, no marks, no hint."""
    body = version.body
    fmt = version.question.format
    projection = client_projection(fmt, body, formats.make_map(fmt, body))
    if fmt == "mcq":
        return {
            "format": "mcq",
            "text": projection["stem"],
            "options": [o["text"] for o in projection["options"]],
        }
    return {
        "format": fmt,
        "text": projection.get("title") or projection.get("ask") or "",
        "ask": projection.get("ask") if projection.get("title") else "",
        "options": [],
    }


def _rows(versions) -> list[dict]:
    rows = []
    for number, version in enumerate(versions, start=1):
        row = _project(version)
        row["number"] = number
        row["module"] = version.question.module.number if version.question.module_id else None
        rows.append(row)
    return rows


def preview_part(request, part_id):
    part = get_object_or_404(
        AssessmentPart.objects.select_related("module"), pk=part_id, is_published=True
    )
    versions = services._latest_versions(live_questions(part))
    shown = part.draw_n if part.selection == "draw" else len(versions)
    return render(
        request,
        "assessments/preview.html",
        {
            "title": part.name,
            "eyebrow": f"Module {part.module.number}",
            "rows": _rows(versions),
            "note_pool": part.selection == "draw",
            "draw_n": shown,
            "pool_size": len(versions),
            "exam_sets": [],
        },
    )


def preview_exam(request, kind):
    if kind not in ("final", "pretest"):
        raise Http404
    exam_sets = list(ExamSet.objects.filter(status="released"))
    chosen = next((s for s in exam_sets if s.code == request.GET.get("set")), None)
    chosen = chosen or (exam_sets[0] if exam_sets else None)
    rows = []
    if chosen:
        items = chosen.members().select_related("version__question__module")
        if kind == ProgrammeAssessmentKind.PRETEST:
            items = items.filter(in_pretest=True)
        versions = [
            i.version
            for i in items.order_by("version__question__module__number", "pk")
            if i.version
        ]
        rows = _rows(versions)
    return render(
        request,
        "assessments/preview.html",
        {
            "title": "Pre-test" if kind == "pretest" else "Final exam",
            "eyebrow": "Programme exam",
            "rows": rows,
            "exam_sets": exam_sets,
            "chosen_set": chosen,
            "kind": kind,
        },
    )


def staff_notice(request):
    """Mentors: assessments are for learners. A friendly page, not a bare 403."""
    return render(request, "assessments/staff_notice.html", status=403)
