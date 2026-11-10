"""Results are computed, never stored (architecture §10). Decimals only; rounding only here.

`compute_results(user_ids)` is the single source for module %, overall %, the grade, the final's
unlock state, eligibility and the blockers. The dashboard, the mentor pages and the impact
preview all call it, so they cannot disagree.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

PASS_MARK = Decimal("50")  # module and final pass mark, D2
MODULE_PASS = PASS_MARK
FINAL_PASS = PASS_MARK
HUNDRED = Decimal("100")
ONE_DECIMAL = Decimal("0.1")
WEIGHT_MODULES = Decimal("0.5")  # D1
WEIGHT_FINAL = Decimal("0.5")
ZERO = Decimal("0")
GRADES = [(Decimal("90"), "A+"), (Decimal("80"), "A"), (Decimal("60"), "B"), (Decimal("50"), "C")]
BAND_STRONG = Decimal("75")


def round1(value: Decimal) -> Decimal:
    """Round to one decimal place, halves up. The only rounding function for scores."""
    return Decimal(value).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def percent(earned: Decimal, total: Decimal) -> Decimal:
    """100 × earned / total, rounded once with round1. Zero when there is nothing to score."""
    if not total:
        return Decimal("0.0")
    return round1(HUNDRED * Decimal(earned) / Decimal(total))


def grade(overall: Decimal) -> str:
    """The grade for an overall %, compared after rounding (79.95 shows 80.0 and is an A)."""
    shown = round1(overall)
    for floor, letter in GRADES:
        if shown >= floor:
            return letter
    return "Not yet"


def band(pct: Decimal) -> str:
    """The final's per-module band (§9.5): strong ≥ 75, OK 50–74.9, needs work < 50."""
    shown = round1(pct)
    if shown >= BAND_STRONG:
        return "strong"
    return "ok" if shown >= PASS_MARK else "needs_work"


# --- what compute_results returns ---------------------------------------------------------------


@dataclass
class PartResult:
    part_id: int
    name: str
    marks: int
    best: Decimal = ZERO  # best counted attempt, 0 if none
    answered: bool = False  # a submitted attempt with every question answered (gated ones count)
    attempts: int = 0


@dataclass
class ModuleResult:
    number: int
    title: str
    parts: list = field(default_factory=list)

    @property
    def raw(self) -> Decimal:  # full precision: this is what enters the mean
        return sum((p.marks * p.best for p in self.parts), ZERO) / HUNDRED

    @property
    def shown(self) -> Decimal:
        return round1(self.raw)

    @property
    def passed(self) -> bool:
        return self.shown >= MODULE_PASS


@dataclass
class Result:
    user_id: int
    modules: list
    final_best: Decimal = ZERO
    final_attempts: int = 0
    pretest_done: bool = False
    email_verified: bool = True
    active: bool = True
    already_issued: bool = False
    blockers: list = field(default_factory=list)

    @property
    def modules_raw(self) -> Decimal:
        return (
            sum((m.raw for m in self.modules), ZERO) / len(self.modules) if self.modules else ZERO
        )

    @property
    def modules_shown(self) -> Decimal:
        return round1(self.modules_raw)

    @property
    def final_shown(self) -> Decimal:
        return round1(self.final_best)

    @property
    def overall_raw(self) -> Decimal:
        return WEIGHT_MODULES * self.modules_raw + WEIGHT_FINAL * self.final_best

    @property
    def overall_shown(self) -> Decimal:
        return round1(self.overall_raw)

    @property
    def grade(self) -> str:
        return grade(self.overall_raw)

    @property
    def parts_all_answered(self) -> bool:
        return all(p.answered for m in self.modules for p in m.parts)

    @property
    def final_unlocked(self) -> bool:  # §10.2
        return self.parts_all_answered and self.pretest_done

    @property
    def modules_passed(self) -> bool:
        return all(m.passed for m in self.modules)

    @property
    def final_passed(self) -> bool:
        return self.final_shown >= FINAL_PASS

    @property
    def eligible(self) -> bool:  # §10.2
        return (
            self.email_verified
            and self.active
            and self.modules_passed
            and self.final_passed
            and not self.already_issued
        )


def _counted_parts():
    from apps.assessments.models import AssessmentPart
    from apps.content.models import Module

    modules = list(Module.objects.filter(counted=True, kind="learning").order_by("order", "number"))
    parts = defaultdict(list)
    for part in AssessmentPart.objects.filter(
        module__in=modules, counted=True, is_published=True
    ).order_by("module__order", "pk"):
        parts[part.module_id].append(part)
    # A module with no published counted part is not counted yet (§10.4): it cannot be taken, so it
    # neither enters the mean nor blocks eligibility.
    return [m for m in modules if parts[m.pk]], parts


def compute_results(user_ids) -> dict:
    """{user_id: Result} for these users, from their attempts. Nothing is read from a stored total."""
    from allauth.account.models import EmailAddress

    from apps.accounts.models import User, UserStatus
    from apps.assessments.models import Attempt, AttemptStatus, ProgrammeAssessmentKind

    user_ids = list(user_ids)
    modules, parts_by_module = _counted_parts()
    submitted = (AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED)
    attempts = defaultdict(list)
    for a in Attempt.objects.filter(user_id__in=user_ids, status__in=submitted).select_related(
        "programme_assessment"
    ):
        attempts[a.user_id].append(a)
    verified = set(
        EmailAddress.objects.filter(user_id__in=user_ids, verified=True).values_list(
            "user_id", flat=True
        )
    )
    statuses = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "status"))
    out = {}
    for uid in user_ids:
        mine = attempts[uid]
        module_results = []
        for module in modules:
            result = ModuleResult(module.number, module.title or f"Module {module.number}")
            for part in parts_by_module[module.pk]:
                tries = [a for a in mine if a.part_id == part.pk]
                counted = [a.score for a in tries if a.counted and a.score is not None]
                result.parts.append(
                    PartResult(
                        part.pk,
                        part.name,
                        part.marks,
                        best=max(counted, default=ZERO),
                        answered=any(a.all_answered for a in tries),
                        attempts=len(tries),
                    )  # fmt: skip
                )
            module_results.append(result)
        finals = [
            a for a in mine
            if a.programme_assessment_id and a.programme_assessment.kind == ProgrammeAssessmentKind.FINAL
        ]  # fmt: skip
        r = Result(
            user_id=uid,
            modules=module_results,
            final_best=max((a.score for a in finals if a.counted and a.score is not None), default=ZERO),
            final_attempts=len(finals),
            pretest_done=any(
                a.programme_assessment_id and a.programme_assessment.kind == ProgrammeAssessmentKind.PRETEST
                for a in mine
            ),
            email_verified=uid in verified,
            active=statuses.get(uid) == UserStatus.ACTIVE,
        )  # fmt: skip
        r.blockers = blockers(r)
        out[uid] = r
    return out


def blockers(r: Result) -> list[str]:
    """Plain-language reasons the learner is not eligible yet (§10.2)."""
    out = []
    if not r.email_verified:
        out.append("Verify your email address.")
    if not r.active:
        out.append("Your account is waiting for your guardian's consent.")
    if not r.pretest_done:
        out.append("Take the short pre-test. The final stays locked until it is done.")
    for m in r.modules:
        for p in m.parts:
            if not p.answered:
                out.append(
                    f"Module {m.number}, {p.name}: submit it once with every question answered."
                )
    for m in r.modules:
        if m.parts and not m.passed and all(p.answered for p in m.parts):
            detail = ", ".join(f"your best {p.name} is {round1(p.best)}%" for p in m.parts)
            out.append(f"Module {m.number} is at {m.shown}%. {detail[0].upper()}{detail[1:]}.")
    if r.final_unlocked and not r.final_passed:
        out.append(
            "Take the final exam." if not r.final_attempts
            else f"Your best final is {r.final_shown}%. You need {FINAL_PASS}%."
        )  # fmt: skip
    return out
