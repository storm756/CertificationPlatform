"""One-off import of the legacy MCQ bank (docs/legacy-sources.md). Private content, never in git.

Reads `bank_booklet.json`: {"1": [{id, pc, t, q, o: [4 options], a: index of the correct one}]}.
The questions are real and private, so this module and its command never print question text:
only counts and ids.

* Pools: until the content team's sheet decides, each module gets 30 `module_quiz` and 15
  `practice` questions, with at least 5 per PC tag in the quiz. Never `final`.
* Hints: the legacy bank has none. The questions are therefore imported as DRAFTS and cannot go
  live until the team supplies approved hints (§13.2). Nothing is invented here.
* Safety: it refuses to run if any of these questions has since been edited in the app.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from apps.content.models import Module

from . import schemas, services
from .models import Pool, Question

QUIZ_SIZE = 30
MIN_PER_PC_IN_QUIZ = 5


class LegacyImportRefused(Exception):
    pass


@dataclass
class Report:
    created: int = 0
    unchanged: int = 0
    invalid: list[str] = field(default_factory=list)  # ids only
    per_module: dict[int, Counter] = field(default_factory=dict)
    quiz_min_pc: dict[int, int] = field(default_factory=dict)
    missing_hints: int = 0


def assign_pools(rows: list[dict]) -> dict[str, str]:
    """Deterministically split one module's questions into the quiz and practice pools."""
    by_pc: dict[str, list[dict]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["id"]):
        by_pc[row["pc"]].append(row)
    quiz: list[dict] = []
    for pc in sorted(by_pc):  # the guaranteed minimum from every PC first
        quiz.extend(by_pc[pc][:MIN_PER_PC_IN_QUIZ])
    taken = {r["id"] for r in quiz}
    spare = {pc: [r for r in group if r["id"] not in taken] for pc, group in by_pc.items()}
    while len(quiz) < QUIZ_SIZE and any(spare.values()):  # then rotate through the PCs
        for pc in sorted(spare):
            if spare[pc] and len(quiz) < QUIZ_SIZE:
                quiz.append(spare[pc].pop(0))
    in_quiz = {r["id"] for r in quiz}
    return {r["id"]: (Pool.MODULE_QUIZ if r["id"] in in_quiz else Pool.PRACTICE) for r in rows}


def load(path: Path) -> dict[str, list[dict]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_body(row: dict) -> dict:
    options = row["o"]
    if not isinstance(row["a"], int) or not 0 <= row["a"] < len(options):
        raise ValueError("answer index out of range")
    return {
        "stem": row["q"],
        "options": [{"id": f"o{i + 1}", "text": text} for i, text in enumerate(options)],
        "correct": f"o{row['a'] + 1}",
        "hint": "",  # none in the legacy bank: the team supplies approved hints
        "gate": {},
    }


def run(path: Path, *, dry_run: bool) -> Report:
    bank = load(path)
    report = Report()
    plan = []  # (row, module number, pool)
    for module_key, rows in bank.items():
        number = int(module_key)
        pools = assign_pools(rows)
        report.per_module[number] = Counter(pools.values())
        quiz_pcs = Counter(r["pc"] for r in rows if pools[r["id"]] == Pool.MODULE_QUIZ)
        report.quiz_min_pc[number] = min(quiz_pcs.values()) if quiz_pcs else 0
        plan.extend((row, number, pools[row["id"]]) for row in rows)

    edited = [
        q.stable_id
        for q in Question.objects.filter(
            stable_id__in=[r["id"] for r, _, _ in plan]
        ).prefetch_related("versions")
        if q.versions.count() > 1
    ]
    if edited:
        raise LegacyImportRefused(
            f"{len(edited)} of these questions have been edited in the app; the legacy import "
            "runs once and refuses to overwrite edits."
        )

    modules = {m.number: m for m in Module.objects.all()}
    with transaction.atomic():
        for row, number, pool in plan:
            try:
                body = to_body(row)
                schemas.parse_body("mcq", body)
            except (ValueError, KeyError, TypeError, schemas.ValidationError):
                report.invalid.append(str(row.get("id")))
                continue
            report.missing_hints += 1
            if Question.objects.filter(stable_id=row["id"]).exists():
                report.unchanged += 1  # create-only: an existing question is never touched
                continue
            services.create_question(
                stable_id=row["id"],
                module=modules[number],
                body=body,
                tags={"pc": row["pc"], "type": row.get("t", "")},
                pool=pool,
            )
            report.created += 1
        if dry_run:
            transaction.set_rollback(True)
    return report
