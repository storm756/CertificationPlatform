"""Private import of the final exam sets from the team's workbook. Preview by default.

    python manage.py import_final_sets --source content-data/outputs/<id>/CCFR-Final-Assessment-Selected-Sets-B-D.xlsx
    python manage.py import_final_sets --source <same file> --apply

Reads every "Set X" tab. Prints counts and stable IDs only: never question text, answers or
scoring details. Rows are accepted only if they are fresh, single-choice, one mark, with a valid
answer key and hint, and not a copy of a module or practice question. --apply stores accepted rows
as DRAFT final-pool questions in a DRAFT set: nothing reaches learners until an admin releases the
set in the admin, which runs the release checks (blueprint, pre-test, reuse) again.
"""

import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assessments import examsets
from apps.assessments.models import ExamSet, ExamSetItem
from apps.content.models import Module
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


def _text(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def read_sets(path: Path) -> dict:
    """{set code: [row dict, ...]} from every "Set X" tab."""
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
        sets[match.group(1)] = [
            {key: row[i] if i < len(row) else None for key, i in index.items()}
            for row in rows[header_at + 1 :]
            if row and _text(row[index["id"]])
        ]
    if not sets:
        raise CommandError("The workbook has no 'Set X' tabs.")
    return sets


def _body(row) -> dict:
    options = [_text(row[k]) for k in ("a", "b", "c", "d") if _text(row[k])]
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
        "correct": "ABCD".index(_text(row["correct"]).upper()),
        "keep_order": bool(tones),
    }


def check_row(code, row, copies) -> tuple[str, list[str]]:
    """("accepted" | "reused" | "copy" | "review" | "invalid", reasons). Reasons hold no content."""
    stable_id = _text(row["id"])
    reasons = []
    match = ID.fullmatch(stable_id)
    module = int(float(row["module"])) if _text(row["module"]) else None
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
    text = examsets.normalise(_text(row["scenario"]))
    if text in copies:
        return "copy", [f"same text as module or practice question {copies[text]}"]
    existing = Question.objects.filter(stable_id=stable_id).exclude(pool=Pool.FINAL).first()
    if existing:
        return "copy", [f"the ID already belongs to a {existing.pool} question"]
    return "accepted", []


class Command(BaseCommand):
    help = "Preview (default) or --apply the final exam sets from the private workbook."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, source, apply, **options):
        if not source.is_file():
            raise CommandError(f"Workbook not found: {source}")
        sets = read_sets(source)
        copies = examsets.non_final_texts()
        blueprint = examsets.blueprint()
        plans = {}
        for code, rows in sorted(sets.items()):
            outcome = {}
            ids = Counter(_text(r["id"]) for r in rows)
            for row in rows:
                stable_id = _text(row["id"])
                status, reasons = check_row(code, row, copies)
                if ids[stable_id] > 1:
                    status, reasons = "invalid", ["the ID appears twice in the set"]
                outcome[stable_id] = (status, reasons, row)
            plans[code] = outcome
            self._report(code, outcome, blueprint)
        if apply:
            self._apply(plans)
            self.stdout.write(self.style.SUCCESS("Applied: accepted rows saved as draft final-pool questions in draft sets. Release them in the admin after the checks pass."))  # fmt: skip
        else:
            self.stdout.write(
                "Preview only: nothing was saved. Use --apply to store accepted rows as drafts."
            )

    def _report(self, code, outcome, blueprint):
        w = self.stdout.write
        by = Counter(status for status, _, _ in outcome.values())
        w(f"== Set {code}: {len(outcome)} rows · accepted {by['accepted']} · reused {by['reused']} · copies {by['copy']} · human review {by['review']} · invalid {by['invalid']}")  # fmt: skip
        for status in ("reused", "copy", "review", "invalid"):
            listed = [(i, r) for i, (s, r, _) in outcome.items() if s == status]
            if listed:
                w(f"  {status}: " + "; ".join(f"{i} ({', '.join(r)})" for i, r in listed))
        accepted = [row for s, _, row in outcome.values() if s == "accepted"]
        pretest = Counter(
            int(float(r["module"]))
            for s, _, r in outcome.values()
            if _text(r["pretest"]).casefold() == "yes"
        )
        pretest_ok = Counter(
            int(float(r["module"])) for r in accepted if _text(r["pretest"]).casefold() == "yes"
        )
        have = Counter(int(float(r["module"])) for r in accepted)
        blockers = []
        for n, need in sorted(blueprint.items()):
            line = f"  Module {n}: {have[n]} accepted of {need} needed · pre-test {pretest_ok[n]}/{examsets.PRETEST_PER_MODULE} accepted ({pretest[n]} proposed)"
            if have[n] < need:
                blockers.append(f"Module {n} needs {need - have[n]} more fresh question(s)")
            elif have[n] > need:
                blockers.append(
                    f"Module {n} has {have[n] - need} surplus fresh question(s) (keep in reserve or change the blueprint)"
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

    @transaction.atomic
    def _apply(self, plans):
        modules = {m.number: m for m in Module.objects.all()}
        for code, outcome in plans.items():
            exam_set, _ = ExamSet.objects.get_or_create(
                code=code, defaults={"name": f"Final exam set {code}"}
            )
            if exam_set.is_released:
                raise CommandError(f"Set {code} is already released; it cannot be re-imported.")
            for stable_id, (status, _, row) in outcome.items():
                if status != "accepted":
                    continue
                body = _body(row)
                question = Question.objects.filter(stable_id=stable_id).first()
                if question is None:
                    question = question_services.create_question(
                        stable_id=stable_id, module=modules[int(float(row["module"]))], fmt="mc",
                        body=body, tags={}, pool=Pool.FINAL,
                    )  # fmt: skip
                else:
                    question_services.add_version(question, body)  # a new version if it changed
                ExamSetItem.objects.update_or_create(
                    exam_set=exam_set, question=question,
                    defaults={"in_pretest": _text(row["pretest"]).casefold() == "yes"},
                )  # fmt: skip
