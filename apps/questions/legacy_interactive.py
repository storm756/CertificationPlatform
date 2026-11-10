"""One-off import of the legacy interactive challenges (docs/legacy-sources.md). Private content.

Input is the JSON written by `tools/legacy_export.mjs` (kept in content-data/legacy/, gitignored).
Like the MCQ importer, this module and its command never print question text: only counts and ids.

* Format `type` gives the schema. Markup in the legacy text is flattened to plain text (content is
  never stored as HTML), so bold in an explanation is lost: report this to the content team.
* Module quizzes (m01-m07, m09) go to the `module_quiz` pool. **Module 8's crosswords and the
  mixed set (m11) go to `practice`** (D26); the mixed set is also recorded as the practice mock.
* The legacy challenges have an explanation (`why`) but **no hint**, so they import as DRAFTS and
  cannot go live until the team supplies approved hints. Nothing is invented here.
* Hotspot art is raw SVG in the legacy file. It is never stored: the importer draws a PNG from the
  SVG's rectangles and text, and keeps only the tappable regions as shapes. If the art uses
  anything it cannot draw, the question is imported without a picture and listed in the report.
* It is create-only and refuses to run after any of these questions has been edited in the app.
"""

import html
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET  # noqa: S405 (input is rejected if it has a DOCTYPE)

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.assessments.models import (
    AssessmentPart,
    PartFamily,
    ProgrammeAssessment,
    ProgrammeAssessmentKind,
    Selection,
)
from apps.content.models import Module

from . import images, schemas, services
from .models import Question

TONES = {"red": "red", "amb": "amber", "yel": "yellow", "grn": "green"}
MODULE_QUIZ_FILES = {f"m0{n}" for n in (1, 2, 3, 4, 5, 6, 7, 9)}


class LegacyImportRefused(Exception):
    pass


@dataclass
class Report:
    created: int = 0
    unchanged: int = 0
    invalid: list[str] = field(default_factory=list)  # ids and the reason, never text
    by_format: Counter = field(default_factory=Counter)
    by_pool: Counter = field(default_factory=Counter)
    no_picture: list[str] = field(default_factory=list)
    mixed: int = 0
    missing_hints: int = 0


def plain(value) -> str:
    """Flatten legacy markup to plain text: tags removed, entities decoded, spaces collapsed."""
    text = re.sub(r"<\s*(br|/p|/li|/div)\s*/?>", " ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]*>", "", text)
    return " ".join(html.unescape(text).split())


def _tone(code):
    return TONES.get(code)


def _spot_segments(text: str) -> list[dict]:
    """`[[!risky]]` and `[[safe]]` markers become tappable segments; the rest is plain text."""
    segments, last = [], 0
    for match in re.finditer(r"\[\[(!?)([\s\S]+?)\]\]", text):
        if match.start() > last:
            segments.append(
                {"text": plain_keep(text[last : match.start()]), "tappable": False, "risky": False}
            )
        segments.append(
            {"text": plain_keep(match.group(2)), "tappable": True, "risky": bool(match.group(1))}
        )
        last = match.end()
    if last < len(text):
        segments.append({"text": plain_keep(text[last:]), "tappable": False, "risky": False})
    return [s for s in segments if s["text"]]


def plain_keep(value: str) -> str:
    """Like plain(), but keeps the single spaces around a phrase (they matter between segments)."""
    text = re.sub(r"<[^>]*>", "", value)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\n]+", " ", text)
    return text


def _common(q: dict) -> dict:
    return {
        "title": plain(q.get("title")),
        "ask": plain(q.get("ask")),
        "scene": plain(q.get("scene")),
        "why": plain(q.get("why")),
        "hint": "",  # none in the legacy challenges
        "gate_message": plain(q.get("gateMsg") or q.get("gateIfMissed")),
    }


def convert(q: dict, *, image_id=None) -> tuple[str, dict]:  # noqa: C901 - one branch per format
    """(format, body) for one legacy challenge. Raises ValueError on a shape we don't know."""
    kind = q["type"]
    body = _common(q)
    if kind == "mc":
        options = [{"t": o} if isinstance(o, str) else o for o in q["opts"]]
        body["options"] = [
            {"text": plain(o["t"]), "tone": _tone(o.get("c")), "gate": False} for o in options
        ]
        body["correct"] = q["a"]
        body["keep_order"] = bool(q.get("keepOrder")) or any(o.get("c") for o in options)
    elif kind == "cards":
        body["labels"] = [{"text": plain(x["t"]), "tone": _tone(x.get("c"))} for x in q["labels"]]
        body["items"] = [
            {
                "text": plain(i["t"]),
                "answer": i["a"],
                "why": plain(i.get("why")),
                "gate": bool(i.get("gate")),
            }
            for i in q["items"]
        ]
    elif kind == "spot":
        body["segments"] = _spot_segments(q["text"])
        body["style"] = q.get("style", "")
        body["redact"] = q.get("mode") == "redact"
        body["show_count"] = bool(q.get("showCount"))
        body["gate_if_missed"] = plain(q.get("gateIfMissed"))
    elif kind == "hotspot":
        body["image_id"] = image_id
        body["image_alt"] = body["title"] or "Illustration"
        body["legend"] = plain(q.get("legend"))
        body["regions"] = _hotspot_regions(q)
    elif kind == "sort":
        body["bins"] = [{"text": plain(b["t"]), "tone": _tone(b.get("c"))} for b in q["bins"]]
        body["items"] = [
            {
                "text": plain(i["t"]),
                "bin": i["b"],
                "why": plain(i.get("why")),
                "gate": bool(i.get("gate")),
            }
            for i in q["items"]
        ]
    elif kind == "match":
        body["pairs"] = [
            {"left": plain(p["l"]), "right": plain(p["r"]), "why": plain(p.get("why"))}
            for p in q["pairs"]
        ]
        body["extra"] = [plain(x) for x in q.get("extra", [])]
        body["left_label"] = plain(q.get("leftLabel"))
        body["right_label"] = plain(q.get("rightLabel"))
    elif kind == "order":
        body["items"] = [{"text": plain(i["t"]), "why": plain(i.get("why"))} for i in q["items"]]
    elif kind == "pick":
        body["items"] = [
            {
                "text": plain(i["t"]),
                "ok": bool(i.get("ok")),
                "why": plain(i.get("why")),
                "gate": bool(i.get("gate")),
            }
            for i in q["items"]
        ]
        body["need"] = int(q.get("need") or 0)
        body["check_label"] = plain(q.get("checkLabel"))
    elif kind == "build":
        body["chips"] = [{"text": plain(c["t"]), "gate": bool(c.get("gate"))} for c in q["chips"]]
        body["slots"] = [
            {
                "label": plain(s["label"]),
                "answer": s["a"] if isinstance(s["a"], list) else [s["a"]],
                "chips": s.get("chips"),
            }
            for s in q["slots"]
        ]
        body["scene_label"] = plain(q.get("sceneLabel"))
    elif kind == "settings":
        rows = []
        for r in q["rows"]:
            want = r["want"] if isinstance(r["want"], list) else [r["want"]]
            if r.get("kind") == "switch":
                rows.append(
                    {
                        "text": plain(r["t"]),
                        "kind": "switch",
                        "start": int(bool(r["start"])),
                        "want": [int(bool(w)) for w in want],
                        "why": plain(r.get("why")),
                    }
                )
            else:
                rows.append(
                    {
                        "text": plain(r["t"]),
                        "kind": "choice",
                        "options": [plain(o) for o in r["opts"]],
                        "start": r["start"],
                        "want": want,
                        "why": plain(r.get("why")),
                    }
                )
        body["rows"] = rows
        body["device"] = plain(q.get("device"))
        body["screen"] = plain(q.get("screen"))
        body["check_label"] = plain(q.get("checkLabel"))
    elif kind == "dial":
        body["rows"] = [
            {
                "label": plain(r["label"]),
                "kind": r.get("kind") or "number",
                "unit": plain(r.get("unit")),
                "start": r["start"],
                "min": r.get("min"),
                "max": r.get("max"),
                "steps": r.get("steps"),
                "answer": r["answer"],
                "tol": r.get("tol", 0),
                "why": plain(r.get("why")),
            }
            for r in q["rows"]
        ]
    elif kind == "chat":
        body["who"] = plain(q["who"])
        body["steps"] = [
            {
                "say": plain(s["say"]),
                "replies": [
                    {
                        "text": plain(r["t"]),
                        "score": r["s"],
                        "why": plain(r.get("why")),
                        "gate": bool(r.get("gate")),
                    }
                    for r in s["replies"]
                ],
            }
            for s in q["steps"]
        ]
    elif kind == "crossword":
        body["words"] = [
            {
                "answer": w["a"],
                "row": w["r"],
                "col": w["c"],
                "dir": w["dir"],
                "clue": plain(w["clue"]),
                "why": plain(w.get("why")),
            }
            for w in q["words"]
        ]
        body["scene_label"] = plain(q.get("sceneLabel"))
    else:
        raise ValueError(f"unknown format {kind}")
    return kind, body


# --- hotspot art ---------------------------------------------------------------------------


class UnsupportedArt(ValueError):
    pass


def _parse_svg(svg: str) -> ET.Element:
    if re.search(r"<!(DOCTYPE|ENTITY)", svg, re.I):
        raise UnsupportedArt("doctype")
    root = ET.fromstring(re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", svg))  # noqa: S314
    if root.tag != "svg":
        raise UnsupportedArt("not an svg")
    return root


def _number(value, default=0.0):
    try:
        return float(str(value).replace("px", "").replace("%", ""))
    except ValueError:
        return default


def _shapes(node, ox=0.0, oy=0.0):
    """Yield (kind, element, offset_x, offset_y) for rects and text, in document order."""
    for child in node:
        transform = child.get("transform", "")
        dx = dy = 0.0
        if transform:
            match = re.fullmatch(r"\s*translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)\s*", transform)
            if not match:
                raise UnsupportedArt("transform")
            dx, dy = float(match.group(1)), float(match.group(2))
        if child.tag == "g":
            yield from _shapes(child, ox + dx, oy + dy)
        elif child.tag in ("rect", "text"):
            yield child.tag, child, ox + dx, oy + dy
        else:
            raise UnsupportedArt(child.tag)


def _view(root):
    box = [float(x) for x in re.split(r"[ ,]+", root.get("viewBox", "0 0 400 300").strip())]
    return box[2], box[3]


def _hotspot_regions(q: dict) -> list[dict]:
    root = _parse_svg(q["svg"])
    width, height = _view(root)
    regions = []
    for node_id, info in q["spots"].items():
        boxes = []
        for node in root.iter():
            if node.get("data-h") == node_id:
                boxes.append(_bbox(node, root, width, height))
        if not boxes:
            raise UnsupportedArt("region without shape")
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[0] + b[2] for b in boxes)
        bottom = max(b[1] + b[3] for b in boxes)
        regions.append(
            {
                "label": plain(info.get("label") or node_id),
                "shape": "rect",
                "coords": [round(v, 2) for v in (left, top, right - left, bottom - top)],
                "ok": bool(info.get("ok")),
                "why": plain(info.get("why")),
                "gate": bool(info.get("gate")),
            }
        )
    return regions


def _bbox(node, root, width, height):
    """A region's rectangle in percent of the picture. Sums enclosing translate() offsets."""
    offsets = {}

    def walk(parent, ox, oy):
        for child in parent:
            transform = child.get("transform", "")
            match = (
                re.fullmatch(r"\s*translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)\s*", transform)
                if transform
                else None
            )
            dx, dy = (float(match.group(1)), float(match.group(2))) if match else (0.0, 0.0)
            offsets[id(child)] = (ox + dx, oy + dy)
            walk(child, ox + dx, oy + dy)

    walk(root, 0.0, 0.0)
    rects = [n for n in ([node, *node.iter()]) if n.tag == "rect"]
    if not rects:
        raise UnsupportedArt("region shape")
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for rect in rects:
        ox, oy = offsets.get(id(rect), (0.0, 0.0))
        x, y = ox + _number(rect.get("x")), oy + _number(rect.get("y"))
        w, h = _number(rect.get("width")), _number(rect.get("height"))
        x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x + w), max(y1, y + h)
    return (100 * x0 / width, 100 * y0 / height, 100 * (x1 - x0) / width, 100 * (y1 - y0) / height)


def render_png(svg: str) -> bytes:
    """Draw the legacy SVG's rectangles and text as a PNG. Raises UnsupportedArt otherwise."""
    from PIL import Image, ImageColor, ImageDraw, ImageFont

    root = _parse_svg(svg)
    width, height = _view(root)
    scale = 1000 / width
    image = Image.new("RGB", (round(width * scale), round(height * scale)), "white")
    draw = ImageDraw.Draw(image)

    def colour(value, fallback):
        if not value or value == "none":
            return None
        try:
            return ImageColor.getrgb(value)
        except ValueError:
            return fallback

    for kind, node, ox, oy in _shapes(root):
        if kind == "rect":
            x, y = (ox + _number(node.get("x"))) * scale, (oy + _number(node.get("y"))) * scale
            w, h = _number(node.get("width")) * scale, _number(node.get("height")) * scale
            fill = colour(node.get("fill"), (230, 236, 244))
            line = colour(node.get("stroke"), (60, 70, 90))
            r = _number(node.get("rx")) * scale
            box = [x, y, x + w, y + h]
            if r > 0:
                draw.rounded_rectangle(
                    box,
                    radius=r,
                    fill=fill,
                    outline=line,
                    width=max(1, round(_number(node.get("stroke-width"), 1) * scale)),
                )
            else:
                draw.rectangle(
                    box,
                    fill=fill,
                    outline=line,
                    width=max(1, round(_number(node.get("stroke-width"), 1) * scale)),
                )
        else:
            size = max(8, round(_number(node.get("font-size"), 14) * scale))
            font = ImageFont.load_default(size=size)
            text = plain("".join(node.itertext()))
            x, y = (ox + _number(node.get("x"))) * scale, (oy + _number(node.get("y"))) * scale
            anchor = {"middle": "ms", "end": "rs"}.get(node.get("text-anchor", ""), "ls")
            draw.text(
                (x, y),
                text,
                fill=colour(node.get("fill"), (20, 30, 60)) or (20, 30, 60),
                font=font,
                anchor=anchor,
            )
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# --- the run -------------------------------------------------------------------------------


def stable_id(file_key: str, index: int) -> str:
    if file_key == "m11":
        return f"MIX-{index:02d}"
    return f"M{int(file_key[1:])}-C{index:02d}"


def module_number(file_key: str, q: dict) -> int:
    if file_key != "m11":
        return int(file_key[1:])
    found = re.search(r"Module\s+(\d+)", q.get("mod", ""))
    return (
        int(found.group(1)) if found else 10
    )  # no module named: the capstone (decision to confirm)


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["modules"]


def run(path: Path, *, dry_run: bool) -> Report:  # noqa: C901
    modules = load(path)
    report = Report()
    plan = []
    for file_key, entry in modules.items():
        for index, q in enumerate(entry["questions"], start=1):
            plan.append((file_key, index, q))
    ids = [stable_id(k, i) for k, i, _ in plan]
    edited = [
        x.stable_id
        for x in Question.objects.filter(stable_id__in=ids).prefetch_related("versions")
        if x.versions.count() > 1
    ]
    if edited:
        raise LegacyImportRefused(
            f"{len(edited)} of these questions have been edited in the app; the legacy import "
            "runs once and refuses to overwrite edits."
        )
    db_modules = {m.number: m for m in Module.objects.all()}
    mixed_ids = []
    with transaction.atomic():
        for file_key, index, q in plan:
            qid = stable_id(file_key, index)
            if Question.objects.filter(stable_id=qid).exists():
                report.unchanged += 1
                continue
            image_id = None
            try:
                if q["type"] == "hotspot":
                    try:
                        png = render_png(q["svg"])  # raises if the art can't be drawn
                        if not dry_run:  # a dry run never writes a file
                            upload = SimpleUploadedFile("art.png", png, "image/png")
                            image_id = images.store_image(upload).pk
                    except (UnsupportedArt, ET.ParseError, ValueError):
                        report.no_picture.append(qid)
                fmt, body = convert(q, image_id=image_id)
                schemas.parse_body(fmt, body)
            except (
                ValueError,
                KeyError,
                TypeError,
                schemas.ValidationError,
                UnsupportedArt,
            ) as exc:
                report.invalid.append(f"{qid} ({type(exc).__name__})")
                continue
            pool = "practice" if file_key in ("m08", "m11") else "module_quiz"
            tags = {"mock": "1"} if file_key == "m11" else {}
            services.create_question(
                stable_id=qid,
                module=db_modules[module_number(file_key, q)],
                fmt=fmt,
                body=body,
                tags=tags,
                pool=pool,
            )
            report.created += 1
            report.by_format[fmt] += 1
            report.by_pool[pool] += 1
            report.missing_hints += 1
            if file_key == "m11":
                mixed_ids.append(qid)
        report.mixed = len(mixed_ids)
        if not dry_run:
            for number in (1, 2, 3, 4, 5, 6, 7, 9):  # Part B shells; Module 8's is pending (D26)
                AssessmentPart.objects.get_or_create(
                    module=db_modules[number],
                    name="Part B: interactive",
                    defaults={
                        "family": PartFamily.INTERACTIVE,
                        "marks": 50,
                        "selection": Selection.ALL_SHUFFLED,
                    },
                )
            if mixed_ids:
                mock, _ = ProgrammeAssessment.objects.get_or_create(
                    kind=ProgrammeAssessmentKind.MOCK
                )
                mock.blueprint = {"questions": mixed_ids}
                mock.save()
        if dry_run:
            transaction.set_rollback(True)
    return report


# --- parity helpers (used by tests and `check_legacy_parity`) ------------------------------


def logical_response(fmt: str, body: dict, option_map: dict, logical: dict) -> dict:
    """Turn a legacy-position answer (what the legacy UI would have recorded) into the token
    response the browser would send, so the Python scorer can be run on the same answer."""
    from . import formats

    def tok(table, index):
        return formats.by_index(option_map, table)[int(index)]

    if fmt == "mc":
        return {"choice": tok("options", logical["choice"])}
    if fmt == "cards":
        return {
            "answers": {tok("items", i): tok("labels", a) for i, a in logical["answers"].items()}
        }
    if fmt == "spot":
        return {"picked": [tok("segments", i) for i in logical["picked"]], "done": True}
    if fmt == "hotspot":
        return {"picked": [tok("regions", i) for i in logical["picked"]], "done": True}
    if fmt == "sort":
        return {"placed": {tok("items", i): tok("bins", b) for i, b in logical["placed"].items()}}
    if fmt == "match":
        return {
            "links": {tok("lefts", left): tok("rights", r) for left, r in logical["links"].items()}
        }
    if fmt == "order":
        return {"sequence": [tok("items", k) for k in logical["sequence"]]}
    if fmt == "pick":
        return {"picked": [tok("items", k) for k in logical["picked"]], "done": True}
    if fmt == "build":
        return {"filled": {tok("slots", s): tok("chips", c) for s, c in logical["filled"].items()}}
    if fmt == "settings":
        values = {}
        for i, value in logical["values"].items():
            row = body["rows"][int(i)]
            values[tok("rows", i)] = (
                int(value) if row["kind"] == "switch" else tok(f"row{i}", value)
            )
        return {"values": values, "done": True}
    if fmt == "dial":
        return {"values": {tok("rows", i): v for i, v in logical["values"].items()}, "done": True}
    if fmt == "chat":
        return {"replies": [tok(f"step{i}", r) for i, r in enumerate(logical["replies"])]}
    if fmt == "crossword":
        from .formats import Crossword

        token_at = dict(
            zip(Crossword.cells(body), formats.by_index(option_map, "cells"), strict=True)
        )
        return {
            "letters": {
                token_at[tuple(int(x) for x in rc.split(","))]: ch
                for rc, ch in logical["letters"].items()
            }
        }
    raise ValueError(fmt)


def parity(lookup: dict[str, dict], cases: list[dict]) -> tuple[int, list[str]]:
    """Run the Python scorer on each case the legacy engine scored. Returns (matches, mismatches).

    `lookup` maps a case id to its legacy question. A case matches when the Python score equals the
    engine's (within 1e-9) and the safety-gate flag is the same. Mismatches are listed by id only.
    """
    from . import formats

    matched, mismatched = 0, []
    for case in cases:
        if "js" not in case:
            continue
        fmt, body = convert(lookup[case["id"]])
        parsed = schemas.parse_body(fmt, body).model_dump()
        option_map = formats.make_map(fmt, parsed)
        response = logical_response(fmt, parsed, option_map, case["logical"])
        response = formats.clean_response(fmt, parsed, option_map, response)
        score, gate = formats.score(fmt, parsed, option_map, response)
        if abs(float(score) - case["js"]["score"]) < 1e-9 and gate == case["js"]["gate"]:
            matched += 1
        else:
            mismatched.append(f"{case['id']}#{case['case']} ({fmt})")
    return matched, mismatched
