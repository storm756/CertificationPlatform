"""Results are computed, never stored (architecture §10). Decimals only; rounding only here.

`compute_results(user_ids)` is the single source for module %, overall %, the grade, the final's
unlock state, eligibility and the blockers. The dashboard, the mentor pages and the impact
preview all call it, so they cannot disagree.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils.translation import gettext as _

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
    best_at: object = None  # when the best counted attempt was submitted (the earliest on a tie)

    @property
    def best_shown(self) -> Decimal:
        return round1(self.best)


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
    revoked_blocked: bool = False  # a revoked certificate with no re-issue allowed (§10.2)
    final_best_at: object = None
    setup_gaps: list = field(default_factory=list)
    blockers: list = field(default_factory=list)

    @property
    def achieved_at(self):
        """When the result was achieved: the latest of the submissions that give the best scores
        (normally the passing final). Printed as "Completed on" (D36)."""
        times = [p.best_at for m in self.modules for p in m.parts if p.best_at]
        if self.final_best_at:
            times.append(self.final_best_at)
        return max(times, default=None)

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
        return self.parts_all_answered and self.pretest_done and not self.setup_gaps

    @property
    def modules_passed(self) -> bool:
        # a counted module with no published assessment is a set-up gap (reported separately)
        return all(m.passed for m in self.modules if m.parts)

    @property
    def final_passed(self) -> bool:
        return self.final_shown >= FINAL_PASS

    @property
    def meets_requirements(self) -> bool:
        """Everything about the learner's own results, ignoring course set-up (used by the
        mark-split impact preview, which is about marks and not about missing content)."""
        return (
            self.email_verified
            and self.active
            and self.modules_passed
            and self.final_passed
            and not self.already_issued
            and not self.revoked_blocked
        )

    @property
    def eligible(self) -> bool:  # §10.2
        return self.meets_requirements and not self.setup_gaps


def _counted_parts(overrides=None):
    """(counted modules, published counted parts per module, set-up gaps).

    `overrides` is for the impact preview (§10.4): {"parts": {part_id: {"marks": n, "counted": b}},
    "modules": {module_id: counted}} is applied in memory only, so the preview and the real
    results come from the same code.
    """
    from apps.assessments.models import AssessmentPart
    from apps.content.models import Module

    overrides = overrides or {}
    module_flags = overrides.get("modules", {})
    part_flags = overrides.get("parts", {})
    modules = [
        m
        for m in Module.objects.filter(kind="learning").order_by("order", "number")
        if module_flags.get(m.pk, m.counted)
    ]
    published, unpublished = defaultdict(list), defaultdict(list)
    for part in AssessmentPart.objects.filter(module__in=modules).order_by("module__order", "pk"):
        change = part_flags.get(part.pk, {})
        part.marks = change.get("marks", part.marks)
        part.counted = change.get("counted", part.counted)
        if not part.counted:
            continue
        (published if part.is_published else unpublished)[part.module_id].append(part)
    return modules, published, setup_gaps(modules, published, unpublished)


def setup_gaps(modules, published_parts, unpublished_parts) -> list[str]:
    """Course set-up problems that keep the final locked: a counted module with no published
    counted assessment, a counted assessment that is not published yet, or published counted
    marks that do not total exactly 100 (D11). Learners cannot fix these, and the missing marks
    must not be silently treated as zero or as "nothing required"."""
    gaps = []
    for module in modules:
        if not published_parts[module.pk]:
            gaps.append(f"Module {module.number} has no published assessment yet.")
            continue
        if unpublished_parts[module.pk]:
            names = ", ".join(p.name for p in unpublished_parts[module.pk])
            gaps.append(f"Module {module.number}: {names} is not published yet.")
        marks = sum(part.marks for part in published_parts[module.pk])
        if marks != 100:
            gaps.append(
                f"Module {module.number} has {marks} published marks configured; "
                "it needs exactly 100."
            )
    return gaps


def _raw_percent(attempt):
    """An attempt's percentage from its saved question-level marks, never rounded.

    Attempt.score is stored rounded to one decimal for display, so combining stored scores can
    push a result across the pass mark (13/15 and 5/38 average 49.91, not 50.0). Attempts that
    have no saved items (none exist in practice) fall back to the stored score.
    """
    total = getattr(attempt, "total_points", None)
    if total:
        return HUNDRED * (attempt.earned_points or ZERO) / total
    return attempt.score


def _best(attempts):
    """(best counted percentage, when it was submitted). On a tie the earliest submission wins, so
    retaking for the same score never moves the completion date. (0, None) with nothing counted."""
    counted = [
        (_raw_percent(a), a.submitted_at) for a in attempts if a.counted and a.score is not None
    ]
    if not counted:
        return ZERO, None
    top = max(score for score, _ in counted)
    return top, min((at for score, at in counted if score == top and at), default=None)


def _certificate_states(user_ids):
    """(users holding an issued certificate, users blocked by a revoked one with no re-issue)."""
    from apps.certificates.models import Certificate, CertificateStatus

    rows = Certificate.objects.filter(user_id__in=user_ids).values_list(
        "user_id", "status", "reissue_allowed"
    )
    issued = {uid for uid, status, _ in rows if status == CertificateStatus.ISSUED}
    blocked = {
        uid for uid, status, allowed in rows if status == CertificateStatus.REVOKED and not allowed
    }
    return issued, blocked - issued


def compute_results(user_ids, overrides=None) -> dict:
    """{user_id: Result} for these users, from their attempts. Nothing is read from a stored total."""
    from allauth.account.models import EmailAddress

    from apps.accounts.models import User, UserStatus
    from apps.assessments.models import Attempt, AttemptStatus, ProgrammeAssessmentKind

    user_ids = list(user_ids)
    modules, parts_by_module, gaps = _counted_parts(overrides)
    submitted = (AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED)
    attempts = defaultdict(list)
    marks = ExpressionWrapper(
        F("items__score") * F("items__points"),
        output_field=DecimalField(max_digits=40, decimal_places=20),
    )
    for a in (
        Attempt.objects.filter(user_id__in=user_ids, status__in=submitted)
        .select_related("programme_assessment")
        .annotate(earned_points=Sum(marks), total_points=Sum("items__points"))
    ):
        attempts[a.user_id].append(a)
    verified = set(
        EmailAddress.objects.filter(user_id__in=user_ids, verified=True).values_list(
            "user_id", flat=True
        )
    )
    statuses = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "status"))
    issued, blocked = _certificate_states(user_ids)
    out = {}
    for uid in user_ids:
        mine = attempts[uid]
        module_results = []
        for module in modules:
            result = ModuleResult(module.number, module.title or f"Module {module.number}")
            for part in parts_by_module[module.pk]:
                tries = [a for a in mine if a.part_id == part.pk]
                best, best_at = _best(tries)
                result.parts.append(
                    PartResult(
                        part.pk,
                        part.name,
                        part.marks,
                        best=best,
                        answered=any(a.all_answered for a in tries),
                        attempts=len(tries),
                        best_at=best_at,
                    )  # fmt: skip
                )
            module_results.append(result)
        finals = [
            a for a in mine
            if a.programme_assessment_id and a.programme_assessment.kind == ProgrammeAssessmentKind.FINAL
        ]  # fmt: skip
        final_best, final_best_at = _best(finals)
        r = Result(
            user_id=uid,
            modules=module_results,
            final_best=final_best,
            final_best_at=final_best_at,
            already_issued=uid in issued,
            revoked_blocked=uid in blocked,
            final_attempts=len(finals),
            pretest_done=any(
                a.programme_assessment_id and a.programme_assessment.kind == ProgrammeAssessmentKind.PRETEST
                for a in mine
            ),
            setup_gaps=gaps,
            email_verified=uid in verified,
            active=statuses.get(uid) == UserStatus.ACTIVE,
        )  # fmt: skip
        r.blockers = blockers(r)
        out[uid] = r
    return out


def blockers(r: Result) -> list[str]:
    """Plain-language reasons the learner is not eligible yet (§10.2)."""
    out = []
    if r.revoked_blocked:
        out.append(
            _("Your certificate was revoked. Contact the programme team if you have questions.")
        )
    if r.setup_gaps:
        out.append(
            _("Course setup is incomplete, so the final stays locked.")
            + " "
            + " ".join(r.setup_gaps)
        )
    if not r.email_verified:
        out.append(_("Verify your email address."))
    if not r.active:
        out.append(_("Your account is waiting for your guardian's consent."))
    if not r.pretest_done:
        out.append(_("Take the short pre-test. The final stays locked until it is done."))
    for m in r.modules:
        for p in m.parts:
            if not p.answered:
                out.append(
                    _("Module %(number)s, %(part)s: submit it once with every question answered.")
                    % {"number": m.number, "part": p.name}
                )
    for m in r.modules:
        if m.parts and not m.passed and all(p.answered for p in m.parts):
            detail = ", ".join(
                _("your best %(part)s is %(score)s%%") % {"part": p.name, "score": round1(p.best)}
                for p in m.parts
            )
            out.append(
                _("Module %(number)s is at %(score)s%%.") % {"number": m.number, "score": m.shown}
                + f" {detail[0].upper()}{detail[1:]}."
            )
    if r.final_unlocked and not r.final_passed:
        out.append(
            _("Take the final exam.") if not r.final_attempts
            else _("Your best final is %(best)s%%. You need %(need)s%%.") % {"best": r.final_shown, "need": FINAL_PASS}
        )  # fmt: skip
    return out
