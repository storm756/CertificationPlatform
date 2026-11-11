"""Learning pages (architecture §8). Reading is open to everyone; progress is for learners."""

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.accounts.models import Role
from apps.assessments.models import AssessmentPart

from . import learncheck, services
from .models import MediaAsset, Module, Unit, UnitType, UnitVersion, VersionStatus

KIND_ICON = {"video": "video", "reading": "book", "handout": "file", "check": "lightbulb", "practice_quiz": "retry"}  # fmt: skip
GROUPS = [("watch", "Watch", ["video"]), ("read", "Read", ["reading"]), ("handout", "Handout", ["handout"]), ("practise", "Practise", ["check", "practice_quiz"])]  # fmt: skip


def _posted_unit(request):
    """The unit named by a posted module number and slug; anything malformed is a 404."""
    try:
        number = int(request.POST.get("m", ""))
    except ValueError:
        raise Http404 from None
    return get_object_or_404(Unit, module__number=number, slug=request.POST.get("u", ""))


def _is_learner(user):
    return user.is_authenticated and user.role == Role.LEARNER


def _module(number):
    return get_object_or_404(Module, number=number, kind="learning")


def _rows(user, module):
    units = services.published_units(module)
    done = services.completed_unit_ids(user, [u for u, _ in units])
    rows, reading = [], 0
    for u, v in units:
        if u.type == "reading":
            reading += 1
        rows.append({"unit": u, "version": v, "done": u.pk in done, "icon": KIND_ICON[u.type], "index": reading if u.type == "reading" else None})  # fmt: skip
    return rows


def _grouped(rows):
    return [{"key": k, "title": title, "rows": [r for r in rows if r["unit"].type in types]} for k, title, types in GROUPS if any(r["unit"].type in types for r in rows)]  # fmt: skip


POSTERS = {n: f"img/films/m{n}.jpg" for n in range(1, 10)}  # the prototype's film posters
CAPSTONE_TITLE = "Capstone simulation"
CAPSTONE_TAGLINE = "Bring every module together in one realistic case."


def _state(pct):
    return "done" if pct >= 100 else "progress" if pct > 0 else "todo"


def _question_counts(module):
    """Live (published) questions of this module that learners can be assessed on."""
    from apps.questions.models import Pool, Question, QuestionStatus

    live = Question.objects.filter(module=module, status=QuestionStatus.LIVE, pool=Pool.MODULE_QUIZ)
    return {
        "mcq": live.filter(format="mcq").count(),
        "interactive": live.exclude(format="mcq").count(),
    }


def _module_card(user, module):
    rows = _rows(user, module)
    done = sum(1 for r in rows if r["done"])
    pct = round(100 * done / len(rows)) if rows else 0
    capstone = module.kind == "capstone"
    topics = [r["version"].title for r in rows if r["unit"].type == "reading"]
    title = module.title or (CAPSTONE_TITLE if capstone else module.display_title)
    tagline = module.tagline or (CAPSTONE_TAGLINE if capstone else "")
    counts = _question_counts(module) if not capstone else {"mcq": 0, "interactive": 0}
    return {
        "module": module, "title": title, "tagline": tagline, "capstone": capstone,
        "topics": len(topics), "pct": pct, "state": _state(pct), "has_content": bool(rows),
        "poster": POSTERS.get(module.number), "counts": counts,
        "search": " ".join([title, tagline, *topics]).lower(),
    }  # fmt: skip


def catalogue(request):
    cards = [_module_card(request.user, m) for m in Module.objects.all()]
    learning = [c for c in cards if not c["capstone"]]
    return render(
        request,
        "learn/catalogue.html",
        {
            "cards": cards,
            "stats": {
                "modules": len(learning),
                "topics": sum(c["topics"] for c in learning),
                "films": sum(
                    1
                    for c in learning
                    if any(u.type == "video" for u, _ in services.published_units(c["module"]))
                ),  # fmt: skip
                "hours": sum((c["module"].hours or 0) for c in cards),
            },
        },
    )


def _part_cards(user, module):
    """The module's published assessment parts, each with the learner's attempts and best score."""
    from apps.assessments.models import Attempt

    out = []
    for part in AssessmentPart.objects.filter(module=module, is_published=True).order_by("pk"):
        tries = list(Attempt.objects.filter(user=user, part=part).order_by("number")) if _is_learner(user) else []  # fmt: skip
        best = max((a.score for a in tries if a.counted and a.score is not None), default=None)
        out.append({"part": part, "attempts": len(tries), "best": best})
    return out


def module_page(request, number):
    module = get_object_or_404(Module, number=number)
    if module.kind == "capstone":
        return render(request, "learn/capstone.html", {"card": _module_card(request.user, module), "module": module})  # fmt: skip
    rows = _rows(request.user, module)
    done = sum(1 for r in rows if r["done"])
    nxt = next((r for r in rows if not r["done"]), rows[0] if rows else None)
    return render(
        request,
        "learn/module.html",
        {
            "module": module, "overview": module.overview, "rows": rows, "groups": _grouped(rows),
            "topics": [r for r in rows if r["unit"].type == "reading"],
            "done": done, "total": len(rows), "pct": round(100 * done / len(rows)) if rows else 0,
            "next": nxt, "prev_module": Module.objects.filter(number=number - 1, kind="learning").first(),
            "next_module": Module.objects.filter(number=number + 1).first(),
            "parts": _part_cards(request.user, module),
            "poster": POSTERS.get(module.number),
        },
    )  # fmt: skip


def _prepare(request, unit, blocks):
    """The blocks for the template. Answers never go in: reveal and myth/fact blocks keep theirs."""
    out = []
    for i, b in enumerate(blocks):
        item = {"index": i, **{k: v for k, v in b.items() if k not in ("answer", "is_fact", "why")}}
        if b["type"] == "check":
            item["check"] = learncheck.prepare(request.session, b["question"])
        if b["type"] in ("image", "attachment", "video"):
            for key in ("asset", "mp4", "poster"):
                if b.get(key):
                    item[key + "_url"] = f"/learn/media/{b[key]}/"
        out.append(item)
    return out


def unit_page(request, number, slug):
    module = _module(number)
    unit = get_object_or_404(Unit, module=module, slug=slug)
    version = unit.published()
    if version is None:
        raise Http404
    rows = _rows(request.user, module)
    index = next(i for i, r in enumerate(rows) if r["unit"].pk == unit.pk)
    if _is_learner(request.user):
        services.touch(request.session)
        if unit.type == UnitType.HANDOUT:
            services.complete(request.user, unit, how="opened")
            rows[index]["done"] = True
    blocks = _prepare(request, unit, version.blocks)
    video = next((b for b in blocks if b["type"] == "video"), None)
    return render(
        request,
        "learn/unit.html",
        {
            "module": module,
            "unit": unit,
            "version": version,
            "blocks": blocks,
            "video": video,
            "rows": rows,
            "groups": _grouped(rows),
            "this": rows[index],
            "prev": rows[index - 1] if index else None,
            "next": rows[index + 1] if index + 1 < len(rows) else None,
            "pct": round(100 * sum(1 for r in rows if r["done"]) / len(rows)),
            "complete_rule": {
                "video": "Completes at 80% watched",
                "reading": "Completes when you reach the end",
                "handout": "Completes when opened",
                "check": "Completes after one try",
                "practice_quiz": "Completes when submitted once",
            }[unit.type],  # fmt: skip
            "learner": _is_learner(request.user),
            "parts": _part_cards(request.user, module),
        },
    )


@require_POST
def complete(request, number, slug):
    unit = get_object_or_404(Unit, module__number=number, slug=slug)
    if not _is_learner(request.user):
        raise PermissionDenied
    how = request.POST.get("how", "")
    try:
        created = services.complete(request.user, unit, how=how)
    except services.UnitNotPublished:
        raise Http404 from None
    except (ValueError, KeyError):
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True, "first": created})


@require_POST
@ratelimit(key="ip", rate="120/h", method="POST", block=True)
def block_action(request, number, slug, index):
    """Reveal an answer, or give a myth-or-fact verdict. The server holds the answer until asked."""
    unit = get_object_or_404(Unit, module__number=number, slug=slug)
    version = unit.published()
    if version is None or not 0 <= index < len(version.blocks):
        raise Http404
    block = version.blocks[index]
    if block["type"] == "reveal":
        return JsonResponse({"answer": block["answer"]})
    if block["type"] == "mythfact":
        pick = request.POST.get("pick")
        if pick not in ("fact", "myth"):
            return JsonResponse({"error": "pick fact or myth"}, status=400)
        right = (pick == "fact") == block["is_fact"]
        if _is_learner(request.user) and unit.type == UnitType.CHECK:
            services.complete(request.user, unit, how="attempted")
        return JsonResponse({"right": right, "is_fact": block["is_fact"], "why": block["why"]})
    raise Http404


@require_POST
@ratelimit(key="ip", rate="120/h", method="POST", block=True)
def check(request):
    """POST /learn/check: practice-pool questions only (§8.4)."""
    unit = _posted_unit(request)
    try:
        result = learncheck.answer(
            request.user if _is_learner(request.user) else None, unit,
            request.POST.get("question", ""), request.POST.get("choice", ""), request.session,
        )  # fmt: skip
    except learncheck.CheckRefused as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(result)


@require_POST
def heartbeat(request):
    if not _is_learner(request.user):
        return JsonResponse({"counted": 0})
    unit = _posted_unit(request)
    if unit.published() is None:
        raise Http404
    return JsonResponse({"counted": services.heartbeat(request.user, unit, request.session)})


def media_file(request, pk):
    """A published unit's media only (never a draft's), served with its own checked type."""
    asset = get_object_or_404(MediaAsset, pk=pk)
    used = any(
        _uses(v.blocks, pk)
        for v in UnitVersion.objects.filter(
            unit__module=asset.module, status=VersionStatus.PUBLISHED
        )
    )
    if not used:
        raise Http404
    response = FileResponse(asset.file.open("rb"), content_type=asset.content_type)
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    if asset.kind == "pdf":
        response["Content-Disposition"] = f'inline; filename="module-{asset.module.number}-handout.pdf"'  # fmt: skip
    return response


def _uses(blocks, pk) -> bool:
    return any(pk in (b.get("asset"), b.get("mp4"), b.get("poster")) for b in blocks)


def home_redirect(request):
    return redirect("learn_catalogue")
