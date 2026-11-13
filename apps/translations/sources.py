"""Every translatable English string in the live course, with its key (architecture §14).

Used by the XLSX export and import (unknown keys are refused), the draft importers (matching by
English text) and the stale report. Sources: modules, their published unit versions, assessment
part names, live questions (latest version) and the fixed notes in keys.NOTES.
"""

from dataclasses import dataclass

from . import keys


@dataclass(frozen=True)
class Source:
    key: str
    english: str
    module: int | None  # module number, None for notes
    kind: str  # "module", "unit", "part", "question", "note"


def course_sources(module_number: int | None = None) -> list[Source]:
    from apps.assessments.models import AssessmentPart
    from apps.content.models import Module, VersionStatus
    from apps.questions.models import Question, QuestionStatus

    modules = Module.objects.all()
    if module_number is not None:
        modules = modules.filter(number=module_number)
    out: list[Source] = []
    for module in modules.prefetch_related("units__versions"):
        out += [Source(k, e, module.number, "module") for k, e in keys.module_texts(module)]
        for unit in module.units.all():
            live = next(
                (v for v in unit.versions.all() if v.status == VersionStatus.PUBLISHED), None
            )
            if live is None:
                continue
            prefix = keys.unit_prefix(module.number, unit.slug)
            out.append(Source(f"{prefix}:title", live.title, module.number, "unit"))
            out += [
                Source(k, e, module.number, "unit") for k, e in keys.block_texts(prefix, live.blocks)
            ]
        for part in AssessmentPart.objects.filter(module=module).order_by("pk"):
            out.append(Source(f"part:{part.pk}:name", part.name, module.number, "part"))
        questions = Question.objects.filter(
            module=module, status=QuestionStatus.LIVE
        ).prefetch_related("versions")
        for question in questions:
            version = max(question.versions.all(), key=lambda v: v.version, default=None)
            if version is None:
                continue
            out += [
                Source(k, e, module.number, "question")
                for k, e in keys.question_texts(question.stable_id, question.format, version.body)
            ]
    if module_number is None or module_number == 8:
        out += [Source(f"note:{name}", text, 8, "note") for name, text in keys.NOTES.items()]
    return out


def sources_by_key(module_number: int | None = None) -> dict[str, Source]:
    return {s.key: s for s in course_sources(module_number)}
