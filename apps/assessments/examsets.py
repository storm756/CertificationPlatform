"""Final exam sets (Stage 5): release checks, batch assignment and the per-learner freeze.

A batch is assigned one released set (B or D). That set supplies both programme exams: the
pre-test is its shared baseline questions (two per module) and the final is all of its questions,
including those same shared ones. A learner's set and question versions are frozen when their
first programme exam starts, so a later batch move or reassignment cannot pair a Set B pre-test
with a Set D final. Answer keys never leave the server: these functions only choose questions.
"""

import re

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import Role
from apps.audit.services import audit
from apps.questions import formats
from apps.questions import services as question_services
from apps.questions.models import Pool, Question, QuestionStatus

from .models import ExamSet, ExamSetItem, ExamSetStatus, LearnerExamSet

PRETEST_PER_MODULE = 2
SUPPORTED_FORMATS = {"mcq", "mc"}  # single-choice items with one answer key


def blueprint():
    """Questions per module in the final: the handoff blueprint unless the owner changes it."""
    from .programme import final_blueprint

    return final_blueprint()


def blueprint_problems(counted_modules=None) -> list[str]:
    """Why the blueprint cannot be trusted to define a whole paper. The same checks run for
    "Check sets" and for release. It must name exactly the counted learning modules, each with
    enough questions for its pre-test share, so a one-module paper can never pass."""
    from apps.content.models import Module, ModuleKind

    from .programme import raw_blueprint

    raw = raw_blueprint()
    if not isinstance(raw, dict) or not raw:
        return ["The final's blueprint is missing or empty."]
    problems, parsed = [], {}
    for key, value in raw.items():
        try:
            n = int(str(key))
        except ValueError:
            problems.append(f"The blueprint has a module '{key}' that is not a number.")
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < PRETEST_PER_MODULE:
            problems.append(
                f"Module {n}'s blueprint count must be a whole number of at least {PRETEST_PER_MODULE}."
            )
        parsed[n] = value
    counted = (
        set(counted_modules)
        if counted_modules is not None
        else set(
            Module.objects.filter(counted=True, kind=ModuleKind.LEARNING).values_list(
                "number", flat=True
            )
        )
    )
    for n in sorted(counted - set(parsed)):
        problems.append(f"Module {n} is counted but missing from the blueprint.")
    for n in sorted(set(parsed) - counted):
        problems.append(f"Module {n} is in the blueprint but is not a counted learning module.")
    return problems


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def question_text(body: dict) -> str:
    """The text that identifies a question for duplicate checks (stem or scenario)."""
    return normalise(
        body.get("stem") or body.get("scene") or body.get("title") or formats.label(body)
    )


def non_final_texts() -> dict:
    """{normalised text: stable_id} for every module-quiz and practice question, in EVERY version
    (older wording of an edited question still counts as seen)."""
    out = {}
    for q in Question.objects.exclude(pool=Pool.FINAL).prefetch_related("versions"):
        for version in q.versions.all():
            for text in {question_text(version.body), normalise(version.body.get("title", ""))}:
                if len(text) > 12:
                    out.setdefault(text, q.stable_id)
    return out


def release_errors(exam_set: ExamSet) -> list[str]:
    """Everything that stops this set from being given to learners. Empty means it can be.
    "Check sets" and release both call this, so they always agree."""
    errors = blueprint_problems()
    items = list(exam_set.members().select_related("question__module"))
    wanted = blueprint()
    total = sum(wanted.values())
    if len(items) != total:
        errors.append(f"The set has {len(items)} questions; the blueprint needs {total}.")
    per_module, pretest = {}, {}
    copies = non_final_texts()
    elsewhere = dict(
        ExamSetItem.objects.filter(question__in=[i.question_id for i in items], state="member")
        .exclude(exam_set=exam_set)
        .values_list("question__stable_id", "exam_set__code")
    )
    seen_here = {}
    for item in items:
        q = item.question
        n = q.module.number
        per_module[n] = per_module.get(n, 0) + 1
        if item.in_pretest:
            pretest[n] = pretest.get(n, 0) + 1
        version = q.current_version
        if q.stable_id in elsewhere:
            errors.append(
                f"{q.stable_id} is also in Set {elsewhere[q.stable_id]}; sets never share."
            )
        if q.pool != Pool.FINAL:
            errors.append(f"{q.stable_id} is not in the final pool.")
        if q.status == QuestionStatus.RETIRED or version is None:
            errors.append(f"{q.stable_id} is retired or has no content.")
            continue
        if q.format not in SUPPORTED_FORMATS:
            errors.append(f"{q.stable_id}: {q.format} needs human review of its scoring.")
        if q.points != 1:
            errors.append(
                f"{q.stable_id} is worth {q.points.normalize()} marks; final questions are worth 1."
            )
        for problem in question_services.publish_problems(q):  # the exact checks publish() makes
            errors.append(f"{q.stable_id}: {problem}")
        for reason in q.reuse_reasons():
            errors.append(f"{q.stable_id} {reason} (§11).")
        text = question_text(version.body)
        if text in seen_here:
            errors.append(f"{q.stable_id} repeats {seen_here[text]} in this set.")
        seen_here.setdefault(text, q.stable_id)
        if (match := copies.get(text)) is not None:
            errors.append(f"{q.stable_id} repeats module or practice question {match}.")
    for n, need in sorted(wanted.items()):
        if per_module.get(n, 0) != need:
            errors.append(
                f"Module {n}: {per_module.get(n, 0)} questions, the blueprint needs {need}."
            )
        if pretest.get(n, 0) != PRETEST_PER_MODULE:
            errors.append(
                f"Module {n}: {pretest.get(n, 0)} pre-test questions, needs {PRETEST_PER_MODULE}."
            )
    for n in sorted(set(per_module) - set(wanted)):
        errors.append(f"Module {n} is not in the blueprint.")
    return errors


def lock_set(code: str, name: str | None = None, create=False) -> ExamSet | None:
    """The set's row, locked for this transaction. Import and release both take this lock, so they
    can never edit the same set at once. With create, a missing set is made as a draft."""
    exam_set = ExamSet.objects.select_for_update().filter(code=code).first()
    if exam_set is None and create:
        exam_set = ExamSet.objects.create(code=code, name=name or f"Final exam set {code}")
    return exam_set


def _require_admin(user):
    if not (user and user.is_authenticated and (user.role == Role.ADMIN or user.is_superuser)):
        raise PermissionDenied("Only an admin can change final exam sets.")


@transaction.atomic
def release(exam_set: ExamSet, user, request=None) -> list[str]:
    """Release a set if every check passes. Release records exactly what was approved (the question
    versions, marks, formats and modules) and from then on the paper is fixed."""
    _require_admin(user)
    given, exam_set = exam_set, lock_set(exam_set.code)
    if exam_set.is_released:
        return []
    errors = release_errors(exam_set)
    if errors:
        return errors
    for item in exam_set.members().select_related("question__module"):
        q = item.question
        item.version = q.current_version
        item.approved_points = q.points
        item.approved_format = q.format
        item.approved_module = q.module
        item.save()
        if q.status != QuestionStatus.LIVE:
            question_services.publish(q)
    exam_set.status = ExamSetStatus.RELEASED
    exam_set.released_at = timezone.now()
    exam_set.save(update_fields=["status", "released_at", "updated_at"])
    given.status, given.released_at = exam_set.status, exam_set.released_at
    audit("exam_set.released", actor=user, target=exam_set, request=request, questions=exam_set.members().count())  # fmt: skip
    return []


@transaction.atomic
def assign(batch, exam_set: ExamSet | None, user, request=None):
    """Give a batch a released set (or none). Admins only; audited. Learners who already started
    a programme exam keep the set they were frozen on."""
    from apps.batches.models import Batch

    _require_admin(user)
    given, batch = batch, Batch.objects.select_for_update().get(pk=batch.pk)
    if exam_set is not None and not exam_set.is_released:
        raise ValueError("Only a released set can be assigned to a batch.")
    before = batch.exam_set_id
    if before == (exam_set.pk if exam_set else None):
        return batch
    batch.exam_set = exam_set
    batch.save(update_fields=["exam_set", "updated_at"])
    given.exam_set = exam_set
    audit("batch.exam_set_changed", actor=user, target=batch, request=request, was=before, now=batch.exam_set_id)  # fmt: skip
    return batch


def assigned_set(user):
    """The released set this learner would sit now: their frozen set, else their batch's set."""
    frozen = LearnerExamSet.objects.filter(user=user).select_related("exam_set").first()
    if frozen:
        return frozen.exam_set
    exam_set = _batch_set(user)
    return exam_set if exam_set and exam_set.is_released else None


def _batch_set(user):
    """The set on the learner's batch right now, read fresh (never a cached enrolment)."""
    from apps.batches.models import Enrolment

    enrolment = Enrolment.objects.filter(user=user).select_related("batch__exam_set").first()
    return enrolment.batch.exam_set if enrolment else None


def unavailable_reason(user) -> str | None:
    if LearnerExamSet.objects.filter(user=user).exists():
        return None
    exam_set = _batch_set(user)
    if exam_set is None:
        return _("Your batch has not been given a final exam set yet.")
    if not exam_set.is_released:
        return _("Your batch's final exam set is not ready yet.")
    return None


def freeze(user) -> LearnerExamSet:
    """Fix the learner's set and question versions at their first programme exam. Call with the
    learner's row locked (programme.start_programme does)."""
    existing = LearnerExamSet.objects.filter(user=user).first()
    if existing:
        return existing
    exam_set = assigned_set(user)
    if exam_set is None:
        raise LookupError(unavailable_reason(user) or "No final exam set is available.")
    items = list(exam_set.members().select_related("question"))
    if any(i.version_id is None for i in items):
        raise LookupError(_("Your batch's final exam set is not ready yet."))
    record = LearnerExamSet.objects.create(
        user=user, exam_set=exam_set,
        versions={str(i.question_id): i.version_id for i in items},  # the approved versions
        pretest_question_ids=sorted(i.question_id for i in items if i.in_pretest),
    )  # fmt: skip
    audit("exam_set.frozen", actor=user, target=exam_set, set=exam_set.code)
    return record


def set_items(exam_set: ExamSet):
    return ExamSetItem.objects.filter(exam_set=exam_set)
