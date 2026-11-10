"""XLSX import of MCQs with a dry run and row errors (architecture §13.2, django-import-export).

Columns: id, question, option_a ... option_f, correct, hint, pc, type, pool, points, and optionally
gate, gate_reason, status. A dry run reports every row's problems and changes nothing; a real
import is all-or-nothing, so one bad row stops the whole sheet (`rollback_on_validation_errors`).

Required: a valid body, exactly one correct option, a hint, a PC tag, a type and a pool.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import tablib
from django.core.exceptions import ValidationError
from import_export import fields, resources
from import_export.instance_loaders import BaseInstanceLoader
from import_export.results import RowResult

from apps.content.models import Module

from . import schemas, services
from .models import Pool, Question, QuestionStatus

LETTERS = "ABCDEF"
OPTION_COLUMNS = [f"option_{c.lower()}" for c in LETTERS]
COLUMNS = [
    "id", "question", *OPTION_COLUMNS, "correct", "hint", "pc", "type", "pool", "points",
    "gate", "gate_reason", "status",
]  # fmt: skip
DIFF_COLUMNS = ["id", "question", "correct", "hint", "pc", "type", "pool", "points", "status"]
ID_PATTERN = re.compile(r"^M(\d{1,2})-([A-Za-z0-9]+)$")
TYPES = {"R", "A", "S", "I"}


class RowProblem(Exception):
    def __init__(self, problems: dict[str, str]):
        super().__init__(str(problems))
        self.problems = problems


@dataclass
class ParsedRow:
    stable_id: str
    module: Module
    body: dict
    tags: dict
    pool: str
    points: Decimal
    status: str | None


def _cell(row, name) -> str:
    value = row.get(name)
    return "" if value is None else " ".join(str(value).split())


def parse_row(row: dict) -> ParsedRow:
    """Turn one sheet row into question data, or raise RowProblem listing every column at fault."""
    problems: dict[str, str] = {}
    stable_id = _cell(row, "id")
    match = ID_PATTERN.match(stable_id)
    module = None
    if not match:
        problems["id"] = "Use an id like M4-12 (module number, dash, a number or code)."
    else:
        module = Module.objects.filter(number=int(match.group(1))).first()
        if module is None:
            problems["id"] = f"There is no module {int(match.group(1))}."

    stem = _cell(row, "question")
    if not stem:
        problems["question"] = "The question text is required."

    options = [(c, _cell(row, f"option_{c.lower()}")) for c in LETTERS]
    filled = [(c, t) for c, t in options if t]
    first_gap = next((i for i, (_, t) in enumerate(options) if not t), len(options))
    if any(t for _, t in options[first_gap:]):
        problems["options"] = "Fill the options from A onwards without gaps."
    elif len(filled) < 2:
        problems["options"] = "A question needs at least two options (A and B)."

    correct_raw = _cell(row, "correct").upper().replace(" ", "")
    correct = ""
    if not correct_raw:
        problems["correct"] = "Say which option is correct (one letter)."
    elif len(correct_raw) != 1 or correct_raw not in LETTERS:
        problems["correct"] = "Exactly one option must be correct: give a single letter, e.g. B."
    elif correct_raw not in [c for c, _ in filled]:
        problems["correct"] = f"Option {correct_raw} is empty, so it can't be the correct one."
    else:
        correct = correct_raw

    hint = _cell(row, "hint")
    if not hint:
        problems["hint"] = "A hint is required."

    pc = _cell(row, "pc").upper()
    if not re.fullmatch(r"PC\d{1,2}", pc):
        problems["pc"] = "Give the PC tag, e.g. PC3."
    item_type = _cell(row, "type").upper()
    if item_type not in TYPES:
        problems["type"] = "Type must be one of R, A, S, I."
    pool = _cell(row, "pool").lower().replace(" ", "_")
    if pool not in Pool.values:
        problems["pool"] = "Pool must be module_quiz, final or practice."
    points_raw = _cell(row, "points") or "1"
    try:
        points = Decimal(points_raw)
        if not Decimal("0") < points <= Decimal("10"):
            raise InvalidOperation
    except InvalidOperation:
        points = Decimal("1")
        problems["points"] = "Points must be a number above 0 and up to 10."
    status = _cell(row, "status").lower() or None
    if status not in (None, "draft", "live"):
        problems["status"] = "Status must be draft or live (or empty)."

    gate: dict[str, str] = {}
    gate_raw = _cell(row, "gate").upper().replace(" ", "")
    if gate_raw:
        reason = _cell(row, "gate_reason")
        letters = [x for x in re.split(r"[,;]", gate_raw) if x]
        if not reason:
            problems["gate_reason"] = "Safety-gate options need a reason."
        elif any(x not in LETTERS or x not in [c for c, _ in filled] for x in letters):
            problems["gate"] = "Gate letters must be options of this question."
        elif correct in letters:
            problems["gate"] = "The correct option can't be a safety-gate option."
        else:
            gate = {f"o{LETTERS.index(x) + 1}": reason for x in letters}

    if not problems:
        body = {
            "stem": stem,
            "options": [{"id": f"o{LETTERS.index(c) + 1}", "text": t} for c, t in filled],
            "correct": f"o{LETTERS.index(correct) + 1}",
            "hint": hint,
            "gate": gate,
        }
        try:
            schemas.parse_body("mcq", body)
        except schemas.ValidationError as exc:
            for err in exc.errors():
                problems.setdefault(str(err["loc"][0]) if err["loc"] else "question", err["msg"])
    if problems:
        raise RowProblem(problems)
    return ParsedRow(
        stable_id=stable_id,
        module=module,
        body=body,
        tags={"pc": pc, "type": item_type},
        pool=pool,
        points=points,
        status=status,
    )


class NoLoader(BaseInstanceLoader):
    """import_row() below does its own lookups (a question plus versions), so no loader is used."""

    def get_instance(self, row):
        return None


class MCQResource(resources.Resource):
    """The MCQ sheet. Each row creates a question, adds a new version to an existing one, or is
    skipped when nothing changed. Questions land as drafts unless the row says `live`."""

    for _name in COLUMNS:
        locals()[_name] = fields.Field(column_name=_name)

    class Meta:
        import_id_fields = ["id"]
        instance_loader_class = NoLoader
        use_transactions = True

    @classmethod
    def get_display_name(cls):
        return "Multiple-choice questions"

    def before_import(self, dataset, **kwargs):
        self._seen: set[str] = set()

    def get_diff_headers(self):
        return DIFF_COLUMNS

    def import_row(self, row, instance_loader, **kwargs):
        result = self.get_row_result_class()()
        result.object_id = _cell(row, "id")
        result.object_repr = result.object_id
        try:
            parsed = parse_row(row)
            if parsed.stable_id in self._seen:
                raise RowProblem({"id": "This id appears twice in the sheet."})
            self._seen.add(parsed.stable_id)
            question = Question.objects.filter(stable_id=parsed.stable_id).first()
            if question and (question.format != "mcq" or question.module_id != parsed.module.pk):
                raise RowProblem({"id": "This id belongs to a different module or format."})
        except RowProblem as exc:
            result.import_type = RowResult.IMPORT_TYPE_INVALID
            result.validation_error = ValidationError(
                {col: [msg] for col, msg in exc.problems.items()}
            )
            return result
        result.diff = [_cell(row, c) for c in DIFF_COLUMNS]
        result.import_type = self._apply(parsed, question)
        return result

    def _apply(self, parsed: ParsedRow, question: Question | None) -> str:
        if question is None:
            question = services.create_question(
                stable_id=parsed.stable_id,
                module=parsed.module,
                body=parsed.body,
                tags=parsed.tags,
                pool=parsed.pool,
                points=parsed.points,
            )
            outcome = RowResult.IMPORT_TYPE_NEW
        else:
            _version, created = services.add_version(question, parsed.body)
            changed = created or (question.tags, question.pool, question.points) != (
                parsed.tags,
                parsed.pool,
                parsed.points,
            )
            question.tags, question.pool, question.points = parsed.tags, parsed.pool, parsed.points
            question.save(update_fields=["tags", "pool", "points", "updated_at"])
            outcome = RowResult.IMPORT_TYPE_UPDATE if changed else RowResult.IMPORT_TYPE_SKIP
        if parsed.status == QuestionStatus.LIVE and question.status != QuestionStatus.LIVE:
            services.publish(question)
            outcome = (
                outcome if outcome != RowResult.IMPORT_TYPE_SKIP else RowResult.IMPORT_TYPE_UPDATE
            )
        return outcome


def import_sheet(dataset: tablib.Dataset, *, dry_run: bool):
    """Run the import. Returns the import-export Result (`has_validation_errors()`, `invalid_rows`,
    `totals`). With dry_run=True nothing is saved; with dry_run=False one bad row saves nothing."""
    return MCQResource().import_data(
        dataset, dry_run=dry_run, raise_errors=False, rollback_on_validation_errors=True
    )


def template_workbook() -> bytes:
    """An empty sheet with the right headers and one invented example row."""
    data = tablib.Dataset(headers=COLUMNS)
    data.append(
        [
            "M1-001", "Which of these is a made-up example question?", "An invented answer",
            "A second invented answer", "", "", "", "", "A", "Hint: explain why in one sentence.",
            "PC1", "R", "module_quiz", 1, "", "", "draft",
        ]
    )  # fmt: skip
    return data.export("xlsx")
