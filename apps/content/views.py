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


def _is_learner(user):
    return user.is_authenticated and user.role == Role.LEARNER


def _module(number):
    return get_object_or_404(Module, number=number, kind="learning")


def _rows(user, module):
    units = services.published_units(module)
    done = services.completed_unit_ids(user, [u for u, _ in units])
    return [{"unit": u, "version": v, "done": u.pk in done, "icon": KIND_ICON[u.type]} for u, v in units]  # fmt: skip


def _grouped(rows):
    return [{"key": k, "title": title, "rows": [r for r in rows if r["unit"].type in types]} for k, title, types in GROUPS if any(r["unit"].type in types for r in rows)]  # fmt: skip


def catalogue(request):
    cards = []
    for module in Module.objects.filter(kind="learning"):
        rows = _rows(request.user, module)
        done = sum(1 for r in rows if r["done"])
        cards.append({"module": module, "topics": sum(1 for r in rows if r["unit"].type == "reading"), "units": len(rows), "progress": round(100 * done / len(rows)) if rows else 0})  # fmt: skip
    return render(request, "learn/catalogue.html", {"cards": cards})


def module_page(request, number):
    module = _module(number)
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
            "next_module": Module.objects.filter(number=number + 1, kind="learning").first(),
            "assessments": AssessmentPart.objects.filter(module=module, is_published=True),
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
        if _is_learner(request.user):
            services.complete(request.user, unit, how="attempted") if unit.type == UnitType.CHECK else None  # fmt: skip
        return JsonResponse({"right": right, "is_fact": block["is_fact"], "why": block["why"]})
    raise Http404


@require_POST
@ratelimit(key="ip", rate="120/h", method="POST", block=True)
def check(request):
    """POST /learn/check: practice-pool questions only (§8.4)."""
    unit = get_object_or_404(Unit, module__number=request.POST.get("m") or 0, slug=request.POST.get("u", ""))  # fmt: skip
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
    unit = get_object_or_404(Unit, module__number=request.POST.get("m") or 0, slug=request.POST.get("u", ""))  # fmt: skip
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
