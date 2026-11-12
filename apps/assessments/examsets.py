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
from apps.questions import formats, schemas
from apps.questions import services as question_services
from apps.questions.models import Pool, Question, QuestionStatus

from .models import ExamSet, ExamSetItem, ExamSetStatus, LearnerExamSet

PRETEST_PER_MODULE = 2
SUPPORTED_FORMATS = {"mcq", "mc"}  # single-choice items with one answer key


def blueprint():
    """Questions per module in the final: the handoff blueprint unless the owner changes it."""
    from .programme import final_blueprint

    return final_blueprint()


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def question_text(body: dict) -> str:
    """The text that identifies a question for duplicate checks (stem or scenario)."""
    return normalise(
        body.get("stem") or body.get("scene") or body.get("title") or formats.label(body)
    )


def non_final_texts() -> dict:
    """{normalised text: stable_id} for every module-quiz and practice question."""
    out = {}
    for q in Question.objects.exclude(pool=Pool.FINAL).prefetch_related("versions"):
        version = q.current_version
        if version:
            for text in {question_text(version.body), normalise(version.body.get("title", ""))}:
                if len(text) > 12:
                    out.setdefault(text, q.stable_id)
    return out


def release_errors(exam_set: ExamSet) -> list[str]:
    """Everything that stops this set from being given to learners. Empty means it can be."""
    errors = []
    items = list(exam_set.items.select_related("question__module"))
    wanted = blueprint()
    total = sum(wanted.values())
    if len(items) != total:
        errors.append(f"The set has {len(items)} questions; the blueprint needs {total}.")
    per_module, pretest = {}, {}
    copies = non_final_texts()
    for item in items:
        q = item.question
        n = q.module.number
        per_module[n] = per_module.get(n, 0) + 1
        if item.in_pretest:
            pretest[n] = pretest.get(n, 0) + 1
        version = q.current_version
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
        for problem in schemas.publish_errors(q.format, version.body):
            errors.append(f"{q.stable_id}: {problem}")
        if _shown_outside_programme_exams(q):
            errors.append(f"{q.stable_id} has been shown outside the final (§11).")
        if (match := copies.get(question_text(version.body))) is not None:
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


def _shown_outside_programme_exams(question) -> bool:
    """Shown in a module assessment or practice: it can never be a final question (§11). The
    pre-test is part of the programme exam, so its shared questions may sit in the final too."""
    from .models import AttemptItem, ProgrammeAssessmentKind

    return (
        AttemptItem.objects.filter(question_version__question=question)
        .exclude(
            attempt__programme_assessment__kind__in=[
                ProgrammeAssessmentKind.FINAL,
                ProgrammeAssessmentKind.PRETEST,
            ]
        )
        .exists()
    )


def _require_admin(user):
    if not (user and user.is_authenticated and (user.role == Role.ADMIN or user.is_superuser)):
        raise PermissionDenied("Only an admin can change final exam sets.")


@transaction.atomic
def release(exam_set: ExamSet, user, request=None) -> list[str]:
    """Release a set if every check passes: its questions go live and batches can be given it."""
    _require_admin(user)
    given, exam_set = exam_set, ExamSet.objects.select_for_update().get(pk=exam_set.pk)
    if exam_set.is_released:
        return []
    errors = release_errors(exam_set)
    if errors:
        return errors
    for item in exam_set.items.select_related("question"):
        if item.question.status != QuestionStatus.LIVE:
            question_services.publish(item.question)
    exam_set.status = ExamSetStatus.RELEASED
    exam_set.released_at = timezone.now()
    exam_set.save(update_fields=["status", "released_at", "updated_at"])
    given.status, given.released_at = exam_set.status, exam_set.released_at
    audit("exam_set.released", actor=user, target=exam_set, request=request, questions=exam_set.items.count())  # fmt: skip
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
    items = list(exam_set.items.select_related("question"))
    versions = {}
    for item in items:
        version = item.question.current_version
        versions[str(item.question_id)] = version.pk
    record = LearnerExamSet.objects.create(
        user=user, exam_set=exam_set, versions=versions,
        pretest_question_ids=sorted(i.question_id for i in items if i.in_pretest),
    )  # fmt: skip
    audit("exam_set.frozen", actor=user, target=exam_set, set=exam_set.code)
    return record


def set_items(exam_set: ExamSet):
    return ExamSetItem.objects.filter(exam_set=exam_set)
