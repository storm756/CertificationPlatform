"""Private import of the final exam sets from the team's workbook. Preview by default.

    python manage.py import_final_sets --source content-data/outputs/<id>/CCFR-Final-Assessment-Selected-Sets-B-D.xlsx
    python manage.py import_final_sets --source <same file> --apply

Reads every "Set X" tab. Prints counts and stable IDs only: never question text, answers or
scoring details. Rows are accepted only if they are fresh, single-choice, one mark, with a valid
answer key and hint, and not a copy of anything learners have already met (module quizzes, practice,
lesson checks, in any version). The preview is read-only and shows exactly what --apply would
change. --apply reconciles each DRAFT set with the workbook in one transaction: new rows are added,
changed rows get a new question version, rows the workbook holds back are kept in reserve, and rows
that were removed or rejected are marked rejected (never deleted, so question history stays).
Nothing reaches learners until an admin releases the set, which runs the release checks again.
A released set is never touched.
"""

import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assessments import examsets
from apps.assessments.models import ExamSet, ExamSetItem, ItemState
from apps.content.models import Module, ModuleKind
from apps.questions import schemas
from apps.questions import services as question_services
from apps.questions.models import Pool, Question

ID = re.compile(r"^M([1-9])-F([A-Z])(\d{2})$")
SINGLE_CHOICE = {"Choose one", "Quick verdict", "Who do I call?", "Colour triage"}
TONES = {"red": "red", "amber": "amber", "yellow": "yellow", "green": "green"}
COLUMNS = {
    "id": "Proposed ID", "pretest": "Pre-test candidate?", "review": "Final-pool review",
    "module": "Module No", "format": "Question Format", "title": "Question Title",
    "scenario": "Scenario / Question", "instruction": "Instruction to Candidate", "hint": "Hint",
    "a": "Option A", "b": "Option B", "c": "Option C", "d": "Option D",
    "correct": "Correct Option", "answer": "Correct Answer", "detail": "Full Answer Key / Scoring Detail",
    "why": "Explanation / Rationale", "marks": "Marks", "gate": "Safety Gate Item?", "source": "Source",
}  # fmt: skip
CATEGORIES = ("reused", "copy", "review", "invalid")


def _text(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _module_number(value):
    """A whole module number, or None ("one", "1.9", blank and booleans are not)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value) if isinstance(value, (int, float)) else float(str(value).strip())
    except ValueError:
        return None
    return int(number) if number.is_integer() else None


def read_sets(path: Path) -> dict:
    """{set code: [row dict, ...]} from every "Set X" tab. Every populated row is returned, with
    its sheet row number, so rows with no ID are reported instead of silently skipped."""
    import openpyxl

    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sets = {}
    for sheet in book.worksheets:
        match = re.fullmatch(r"Set ([A-Z])", sheet.title.strip())
        if not match:
            continue
        rows = list(sheet.iter_rows(values_only=True))
        try:
            header_at = next(i for i, r in enumerate(rows) if r and _text(r[0]) == COLUMNS["id"])
        except StopIteration:
            raise CommandError(
                f"{sheet.title}: no header row starting with '{COLUMNS['id']}'."
            ) from None
        header = [_text(c) for c in rows[header_at]]
        missing = [name for name in COLUMNS.values() if name not in header]
        if missing:
            raise CommandError(f"{sheet.title}: missing columns {missing}.")
        index = {key: header.index(name) for key, name in COLUMNS.items()}
        out = []
        for number, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
            if row and any(_text(c) for c in row):
                data = {key: row[i] if i < len(row) else None for key, i in index.items()}
                data["_row"] = number
                out.append(data)
        sets[match.group(1)] = out
    if not sets:
        raise CommandError("The workbook has no 'Set X' tabs.")
    return sets


def _body(row) -> dict:
    letters = [k for k in ("a", "b", "c", "d") if _text(row[k])]
    options = [_text(row[k]) for k in letters]
    scenario, instruction = _text(row["scenario"]), _text(row["instruction"])
    tones = (
        [TONES.get(o.casefold()) for o in options]
        if _text(row["format"]) == "Colour triage"
        else []
    )
    return {
        "title": scenario if len(scenario) <= 200 else "",
        "ask": instruction,
        "scene": "" if len(scenario) <= 200 else scenario,
        "hint": _text(row["hint"]),
        "why": _text(row["why"]),  # practice explanation: never shown in an exam
        "options": [
            {"text": text, "tone": (tones[i] if tones else None), "gate": False}
            for i, text in enumerate(options)
        ],
        # the position among the options kept, not the letter (a blank B would shift C and D)
        "correct": letters.index(_text(row["correct"]).lower()),
        "keep_order": bool(tones),
    }


def check_row(code, row, copies, modules, taken) -> tuple[str, list[str]]:
    """("accepted" | "reserve" | "reused" | "copy" | "review" | "invalid", reasons).
    Reasons describe the problem, never the content. `modules` are the counted module numbers and
    `taken` the IDs of other sets' questions."""
    stable_id = _text(row["id"])
    if not stable_id:
        return "invalid", ["the row has content but no ID"]
    reasons = []
    match = ID.fullmatch(stable_id)
    module = _module_number(row["module"])
    if module is None:
        reasons.append(f"the module '{_text(row['module'])}' is not a whole module number")
    elif module not in modules:
        reasons.append(f"module {module} is not a counted learning module")
    if not match:
        reasons.append("the ID must look like M<module>-F<set><nn>")
    elif match.group(2) != code or int(match.group(1)) != module:
        reasons.append("the ID's module or set letter does not match the row")
    review, source = _text(row["review"]).casefold(), _text(row["source"]).casefold()
    if "reused" in review or source.startswith("reused"):
        return "reused", ["marked reused from a module assessment"]
    fmt = _text(row["format"])
    if fmt not in SINGLE_CHOICE:
        return "review", [f"{fmt or 'blank'} scoring cannot be converted automatically"]
    if _text(row["gate"]).casefold() not in ("", "no"):
        return "review", ["safety-gate items need a human to write the gate reason"]
    if _text(row["detail"]):
        return "review", ["the row has a separate scoring detail; a human must confirm the key"]
    try:
        marks = float(row["marks"])
    except (TypeError, ValueError):
        marks = None
    if marks != 1:
        reasons.append("final questions are worth exactly 1 mark")
    letter = _text(row["correct"]).upper()
    options = {k.upper(): _text(row[k]) for k in ("a", "b", "c", "d")}
    if letter not in options or not options[letter]:
        reasons.append("the answer letter does not point at an option")
    elif _text(row["answer"]) and _text(row["answer"]) != options[letter]:
        reasons.append("the answer text does not match the answer letter (ambiguous key)")
    if sum(1 for v in options.values() if v) < 2:
        reasons.append("fewer than two options")
    if fmt == "Colour triage" and [v.casefold() for v in options.values() if v] != list(TONES):
        reasons.append("colour triage needs Red, Amber, Yellow, Green in that order")
    if not _text(row["hint"]):
        reasons.append("no hint")
    if _text(row["pretest"]).casefold() not in ("yes", "no"):
        reasons.append("pre-test must be Yes or No")
    if reasons:
        return "invalid", reasons
    body = _body(row)
    problems = schemas.publish_errors("mc", body)
    if problems:
        return "invalid", [p.split(":")[0] + ": invalid" for p in problems]
    text = examsets.question_text(body)
    if text in copies:
        return "copy", [f"same text as module or practice question {copies[text]}"]
    existing = Question.objects.filter(stable_id=stable_id).first()
    if existing:
        if existing.pool != Pool.FINAL:
            return "copy", [f"the ID already belongs to a {existing.pool} question"]
        reuse = existing.reuse_reasons()
        if reuse:
            return "copy", [f"the question with this ID {reuse[0]}"]
        locked = existing.locked_reason()
        if locked:
            return "invalid", [f"the question with this ID {locked}; start a new draft instead"]
    if stable_id in taken:
        return "invalid", [f"the ID is already in Set {taken[stable_id]}; sets never share"]
    if "reserve" in review or "hold" in review:
        return "reserve", []
    return "accepted", []


def classify(code, rows, modules):
    """One outcome per workbook row, in sheet order."""
    copies = examsets.non_final_texts()
    taken = dict(
        ExamSetItem.objects.filter(state=ItemState.MEMBER)
        .exclude(exam_set__code=code)
        .values_list("question__stable_id", "exam_set__code")
    )
    counts = Counter(_text(r["id"]) for r in rows if _text(r["id"]))
    out = []
    for row in rows:
        stable_id = _text(row["id"])
        status, reasons = check_row(code, row, copies, modules, taken)
        if stable_id and counts[stable_id] > 1:
            status, reasons = "invalid", [f"the ID appears {counts[stable_id]} times in the set"]
        out.append({
            "key": stable_id or f"row {row['_row']}", "status": status, "reasons": reasons,
            "row": row, "module": _module_number(row["module"]),
        })  # fmt: skip
    return out


def plan(outcome, exam_set):
    """What applying would change in this set: [(stable_id, action)]. Reads only."""
    existing = (
        {i.question.stable_id: i for i in exam_set.items.select_related("question")}
        if exam_set else {}
    )  # fmt: skip
    actions, wanted = [], set()
    for o in outcome:
        if o["status"] not in ("accepted", "reserve"):
            continue
        sid, row = o["key"], o["row"]
        wanted.add(sid)
        member = o["status"] == "accepted"
        question = Question.objects.filter(stable_id=sid).first()
        if question is None:
            actions.append((sid, "add"))
        else:
            digest = question_services.content_hash(
                schemas.parse_body("mc", _body(row)).model_dump()
            )
            latest = question.current_version
            actions.append(
                (sid, "revise" if not latest or latest.content_hash != digest else "keep")
            )
        item = existing.get(sid)
        pretest = member and _text(row["pretest"]).casefold() == "yes"
        if item is None:
            if question is not None:
                actions.append((sid, "include"))
        elif member and item.state != ItemState.MEMBER:
            actions.append((sid, "reinstate"))
        elif not member and item.state != ItemState.RESERVE:
            actions.append((sid, "hold in reserve"))
        elif item.in_pretest != pretest:
            actions.append((sid, "change pre-test flag"))
    for sid, item in existing.items():
        if sid not in wanted and item.state != ItemState.REJECTED:
            actions.append((sid, "reject"))
    return actions


class Command(BaseCommand):
    help = "Preview (default) or --apply the final exam sets from the private workbook."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, source, apply, **options):
        if not source.is_file():
            raise CommandError(f"Workbook not found: {source}")
        sets = read_sets(source)
        modules = set(
            Module.objects.filter(counted=True, kind=ModuleKind.LEARNING).values_list(
                "number", flat=True
            )
        )
        problems = examsets.blueprint_problems()
        if problems:
            self.stdout.write("Blueprint problems: " + "; ".join(problems))
        blueprint = examsets.blueprint()
        if apply:
            with transaction.atomic():
                for code in sorted(sets):
                    self._apply(code, sets[code], modules, blueprint)
            self.stdout.write(self.style.SUCCESS("Applied: draft sets reconciled with the workbook. Release them in the admin after the checks pass."))  # fmt: skip
            return
        for code in sorted(sets):
            exam_set = ExamSet.objects.filter(code=code).first()
            outcome = classify(code, sets[code], modules)
            self._report(code, outcome, blueprint)
            self._changes(code, outcome, exam_set)
        self.stdout.write(
            "Preview only: nothing was saved. Use --apply to reconcile the draft sets."
        )

    def _changes(self, code, outcome, exam_set):
        w = self.stdout.write
        if exam_set and exam_set.is_released:
            w(
                f"  Set {code} is released: --apply will refuse it (corrections go in a new draft set)."
            )
            return
        actions = plan(outcome, exam_set)
        by = Counter(action for _, action in actions)
        w("  If applied: " + (", ".join(f"{n} {a}" for a, n in sorted(by.items())) or "no change")
          + (" (a new draft set)" if exam_set is None else ""))  # fmt: skip
        for action in ("reject", "hold in reserve", "reinstate", "revise"):
            ids = [sid for sid, a in actions if a == action]
            if ids:
                w(f"    {action}: " + ", ".join(ids))

    def _report(self, code, outcome, blueprint):
        w = self.stdout.write
        by = Counter(o["status"] for o in outcome)
        w(f"== Set {code}: {len(outcome)} rows · accepted {by['accepted']} · reserve {by['reserve']} · reused {by['reused']} · copies {by['copy']} · human review {by['review']} · invalid {by['invalid']}")  # fmt: skip
        for status in CATEGORIES:
            listed = [o for o in outcome if o["status"] == status]
            if listed:
                w(
                    f"  {status}: "
                    + "; ".join(f"{o['key']} ({', '.join(o['reasons'])})" for o in listed)
                )
        reserve = [o["key"] for o in outcome if o["status"] == "reserve"]
        if reserve:
            w("  reserve: " + ", ".join(reserve))
        members = [o for o in outcome if o["status"] == "accepted"]
        have = Counter(o["module"] for o in members)
        pretest_ok = Counter(
            o["module"] for o in members if _text(o["row"]["pretest"]).casefold() == "yes"
        )
        pretest = Counter(
            o["module"] for o in outcome if _text(o["row"]["pretest"]).casefold() == "yes"
        )
        blockers = []
        for n, need in sorted(blueprint.items()):
            line = f"  Module {n}: {have[n]} accepted of {need} needed · pre-test {pretest_ok[n]}/{examsets.PRETEST_PER_MODULE} accepted ({pretest[n]} proposed)"
            if have[n] < need:
                blockers.append(f"Module {n} needs {need - have[n]} more fresh question(s)")
            elif have[n] > need:
                blockers.append(
                    f"Module {n} has {have[n] - need} surplus fresh question(s) (hold one in reserve or change the blueprint)"
                )
                line += " · SURPLUS"
            if pretest_ok[n] != examsets.PRETEST_PER_MODULE:
                blockers.append(
                    f"Module {n} needs exactly {examsets.PRETEST_PER_MODULE} accepted pre-test questions"
                )
            w(line)
        w(
            f"  Release blockers: {len(blockers)}"
            + ("" if not blockers else " — " + "; ".join(blockers))
        )

    def _apply(self, code, rows, modules, blueprint):
        exam_set = examsets.lock_set(code, f"Final exam set {code}", create=True)
        if exam_set.is_released:
            raise CommandError(f"Set {code} is already released; start a new draft set instead.")
        outcome = classify(code, rows, modules)
        self._report(code, outcome, blueprint)
        actions = plan(outcome, exam_set)
        self.stdout.write(f"  Applying to Set {code}: " + (", ".join(f"{n} {a}" for a, n in sorted(Counter(a for _, a in actions).items())) or "no change"))  # fmt: skip
        by_id = {o["key"]: o for o in outcome}
        mods = {m.number: m for m in Module.objects.all()}
        for o in outcome:
            if o["status"] not in ("accepted", "reserve"):
                continue
            sid, row = o["key"], o["row"]
            body = _body(row)
            question = Question.objects.filter(stable_id=sid).first()
            if question is None:
                question = question_services.create_question(
                    stable_id=sid, module=mods[o["module"]], fmt="mc", body=body, tags={}, pool=Pool.FINAL,
                )  # fmt: skip
            else:
                question_services.add_version(question, body)  # a new version only if it changed
            member = o["status"] == "accepted"
            ExamSetItem.objects.update_or_create(
                exam_set=exam_set, question=question,
                defaults={
                    "state": ItemState.MEMBER if member else ItemState.RESERVE,
                    "in_pretest": member and _text(row["pretest"]).casefold() == "yes",
                },
            )  # fmt: skip
        for item in exam_set.items.select_related("question").exclude(state=ItemState.REJECTED):
            if item.question.stable_id not in by_id or by_id[item.question.stable_id]["status"] not in ("accepted", "reserve"):  # fmt: skip
                item.state, item.in_pretest = ItemState.REJECTED, False
                item.save()
