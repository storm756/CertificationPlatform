"""validate_part(): what must be true before a part can be published (architecture §13.2)."""

from collections import Counter

from apps.audit.services import audit
from apps.questions.models import Question, QuestionStatus

from .models import AssessmentPart, PartFamily, Selection


class PartInvalid(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def live_questions(part: AssessmentPart):
    """Live questions this part draws from: its module's pool, in the part's format family."""
    fmt = "mcq" if part.family == PartFamily.MCQ else None
    qs = Question.objects.filter(
        module=part.module, pool=part.pool, status=QuestionStatus.LIVE
    ).select_related("module")
    return qs.filter(format=fmt) if fmt else qs.exclude(format="mcq")


def _stem(question) -> str:
    version = question.current_version
    return " ".join(version.body.get("stem", "").casefold().split()) if version else ""


def validate_part(part: AssessmentPart) -> list[str]:
    """Every reason this part can't be published yet. Empty means it can."""
    errors: list[str] = []
    if part.family != PartFamily.MCQ:
        errors.append("Only multiple-choice parts can be published until Stage 3 (interactive).")
        return errors

    # Counted marks in a module never exceed 100. Reaching exactly 100 needs the module's other
    # part (interactive, Stage 3), so that is reported by module_marks_total(), not blocked here.
    if part.counted:
        others = (
            AssessmentPart.objects.filter(module=part.module, counted=True)
            .exclude(pk=part.pk)
            .values_list("marks", flat=True)
        )
        total = sum(others) + part.marks
        if total > 100:
            errors.append(f"The counted marks in this module would total {total}, more than 100.")

    questions = list(live_questions(part))
    if part.selection == Selection.DRAW:
        if not part.draw_n:
            errors.append("A random draw needs draw_n (how many questions to draw).")
        elif len(questions) < 2 * part.draw_n:
            errors.append(
                f"The draw pool has {len(questions)} live questions; it needs at least "
                f"{2 * part.draw_n} (twice draw_n)."
            )
        per_tag = Counter(q.tags.get("pc") for q in questions)
        if None in per_tag:
            errors.append("Some live questions have no PC tag.")
        if part.min_per_tag:
            for tag, count in sorted((t, c) for t, c in per_tag.items() if t):
                if count < part.min_per_tag:
                    errors.append(
                        f"Tag {tag} has {count} questions; at least {part.min_per_tag} needed."
                    )
            if part.draw_n and part.min_per_tag * len([t for t in per_tag if t]) > part.draw_n:
                errors.append("draw_n is too small to include min_per_tag from every tag.")
    elif not questions:
        errors.append("There are no live questions in this part's pool.")

    stems = Counter(_stem(q) for q in questions)
    duplicates = sum(1 for stem, n in stems.items() if stem and n > 1)
    if duplicates:
        errors.append(f"{duplicates} question text(s) appear more than once in the pool.")
    return errors


def module_marks_total(module) -> int:
    """Counted marks across the module's parts. A complete module totals 100 (D11)."""
    return sum(
        AssessmentPart.objects.filter(module=module, counted=True).values_list("marks", flat=True)
    )


def publish_part(part: AssessmentPart, actor=None) -> AssessmentPart:
    errors = validate_part(part)
    if errors:
        raise PartInvalid(errors)
    part.is_published = True
    part.save(update_fields=["is_published", "updated_at"])
    audit("part.published", actor=actor, target=part)
    return part


def unpublish_part(part: AssessmentPart, actor=None) -> AssessmentPart:
    part.is_published = False
    part.save(update_fields=["is_published", "updated_at"])
    audit("part.unpublished", actor=actor, target=part)
    return part
