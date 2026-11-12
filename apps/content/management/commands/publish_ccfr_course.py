"""Install the reviewed CCFR learner content after the three legacy imports."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from apps.assessments.models import AssessmentPart, PartFamily, Selection
from apps.assessments.rules import PartInvalid, live_questions, publish_part, validate_part
from apps.content import media, services
from apps.content.blocks import validate_blocks
from apps.content.models import MediaKind, Module, Unit, VersionSource
from apps.questions import services as question_services
from apps.questions.models import Pool, Question, QuestionStatus


def _span(blocks, expected):
    return [i for i in range(len(blocks)) if blocks[i : i + len(expected)] == expected]


def _publish_unit(unit, blocks):
    current = unit.published()
    if current is None:
        raise CommandError(f"Import the learner units first. Missing publication for {unit}.")
    blocks = validate_blocks(blocks)
    if current.blocks != blocks:
        draft = services.add_version(unit, current.title, blocks, source=VersionSource.EDITOR)
        services.publish(draft, None, system=True)


def _apply_table(patch):
    unit = Unit.objects.get(module__number=patch["module"], slug=patch["unit"])
    current = unit.published()
    if current is None:
        raise CommandError(f"Missing published reading {unit}.")
    old = validate_blocks(patch["match_legacy_blocks"])
    new = validate_blocks(patch["replace_with"])
    matches = _span(current.blocks, old)
    if not matches and len(_span(current.blocks, new)) == 1:
        return
    if len(matches) != 1:
        raise CommandError(f"Table in {unit} changed since import. Review it before replacing it.")
    at = matches[0]
    _publish_unit(unit, current.blocks[:at] + new + current.blocks[at + len(old) :])


def _publish_questions(hints, question_edits):
    questions = {
        q.stable_id: q
        for q in Question.objects.select_for_update()
        .filter(stable_id__in=hints)
        .select_related("module")
    }
    if missing := hints.keys() - questions.keys():
        raise CommandError(f"{len(missing)} questions are missing. Run the private legacy imports.")
    for stable_id, hint in hints.items():
        question = questions[stable_id]
        version = question.current_version
        if (
            version is None
            or question.status == QuestionStatus.RETIRED
            or question.pool == Pool.FINAL
        ):
            raise CommandError(f"{stable_id} has no editable module or practice question.")
        if stable_id in {f"M8-C{i:02d}" for i in range(1, 7)}:
            if question.format != "crossword" or question.module.number != 8:
                raise CommandError(f"{stable_id} does not match the Module 8 crossword set.")
            if question.pool != Pool.MODULE_QUIZ:
                question.pool = Pool.MODULE_QUIZ
                question.save(update_fields=["pool", "updated_at"])
        body = {**version.body, "hint": " ".join(hint.split())}
        for field, text in question_edits.get(stable_id, {}).items():
            if field == "title" or not body.get(field):
                body[field] = text
        try:
            changed = version.body != body
            if changed:
                question_services.add_version(question, body)
            if changed or question.status != QuestionStatus.LIVE:
                question_services.publish(question)
        except (ValueError, question_services.PublishError) as exc:
            raise CommandError(
                f"Could not publish question {stable_id}. Check its hint and schema."
            ) from exc


def _publish_parts(module):
    for family, name, expected in (
        (PartFamily.MCQ, "Part A: multiple choice", 30),
        (PartFamily.INTERACTIVE, "Part B: interactive", 6 if module.number == 8 else 10),
    ):
        part, _ = AssessmentPart.objects.get_or_create(
            module=module,
            name=name,
            defaults={"family": family, "marks": 50, "selection": Selection.ALL_SHUFFLED},
        )
        if (part.family, part.pool, part.marks, part.counted, part.selection) != (
            family,
            Pool.MODULE_QUIZ,
            50,
            True,
            Selection.ALL_SHUFFLED,
        ):
            raise CommandError(f"{part} already has a different configuration.")
        if live_questions(part).count() != expected:
            raise CommandError(f"{part} needs exactly {expected} live questions in its pool.")
        if errors := validate_part(part):
            raise CommandError(f"{part}: {' / '.join(errors)}")
        if not part.is_published:
            publish_part(part)


def _install_assets(module, handout_path, film_path):
    handout = Unit.objects.get(module=module, slug="handout")
    film = Unit.objects.get(module=module, slug="film")
    with handout_path.open("rb") as stream:
        pdf = media.store(
            File(stream), module, MediaKind.PDF, title=f"Module {module.number} handout"
        )
    with film_path.open("rb") as stream:
        mp4 = media.store(File(stream), module, MediaKind.MP4, title=f"Module {module.number} film")
    blocks = handout.published().blocks
    if not any(b.get("asset") == pdf.pk for b in blocks):
        _publish_unit(
            handout,
            [
                {
                    "type": "attachment",
                    "asset": pdf.pk,
                    "label": f"Module {module.number} handout (PDF)",
                },
                *blocks,
            ],
        )
    blocks = film.published().blocks
    if not any(b["type"] == "video" for b in blocks):
        raise CommandError(f"Missing video block for {film}.")
    video = {
        "mp4": mp4.pk,
        "youtube_id": "",
        "captions_en": f"captions/module-{module.number}.en.vtt",
        "captions_hi": f"captions/module-{module.number}.hi.vtt",
    }
    _publish_unit(
        film,
        [{**b, **video} if b["type"] == "video" else b for b in blocks],
    )


def _add_practice_check(module):
    unit = Unit.objects.get(module=module, slug="check")
    blocks = unit.published().blocks
    if any(b["type"] == "check" for b in blocks):
        return
    question = Question.objects.filter(
        module=module, pool=Pool.PRACTICE, format="mcq", status=QuestionStatus.LIVE
    ).first()
    if question is None:
        raise CommandError(f"Module {module.number} has no live practice MCQ.")
    _publish_unit(unit, [*blocks, {"type": "check", "question": question.stable_id}])


class Command(BaseCommand):
    help = "Validate and publish the prepared CCFR course. Preview by default. Use --apply to save."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hints", type=Path, default=Path("content-data/ccfr-release/approved-hints.json")
        )
        parser.add_argument("--films", type=Path, default=Path("content-data/film-source"))
        parser.add_argument("--apply", action="store_true")

    def handle(self, *, hints, films, apply, **options):
        try:
            data = json.loads(hints.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or len(data) != 509
                or any(not isinstance(hint, str) or not hint.strip() for hint in data.values())
            ):
                raise CommandError(
                    "The approved hint file needs one nonblank hint for each of the 509 questions."
                )
            edits_file = hints.with_name("question-edits.json")
            edits = json.loads(edits_file.read_text(encoding="utf-8"))
            if (
                not isinstance(edits, dict)
                or edits.keys() - data.keys()
                or any(
                    not isinstance(fields, dict)
                    or fields.keys() - {"title", "gate_message"}
                    or any(
                        not isinstance(text, str) or not text.strip() for text in fields.values()
                    )
                    for fields in edits.values()
                )
            ):
                raise CommandError(
                    "Question edits need a known ID and nonblank titles or gate reasons."
                )
            table_file = settings.BASE_DIR / "apps/content/data/ccfr-reading-tables.json"
            tables = json.loads(table_file.read_text(encoding="utf-8"))
            assets = {}
            for number in range(1, 10):
                pdf = settings.BASE_DIR / f"apps/content/data/handouts/m{number}.pdf"
                mp4s = list(films.glob(f"module-{number}-*.mp4"))
                if not pdf.is_file() or len(mp4s) != 1:
                    raise CommandError(f"Module {number} needs one local handout and one film.")
                assets[number] = (pdf, mp4s[0])
            if apply:
                self._install(tables, data, edits, assets, preview=False)
            else:
                with TemporaryDirectory() as temporary, override_settings(MEDIA_ROOT=temporary):
                    self._install(tables, data, edits, assets, preview=True)
        except (
            OSError,
            ValueError,
            Unit.DoesNotExist,
            Module.DoesNotExist,
            PartInvalid,
            media.MediaRejected,
        ) as exc:
            raise CommandError(str(exc)) from exc
        status = "Published" if apply else "Verified without saving"
        self.stdout.write(
            self.style.SUCCESS(
                f"{status}: {len(tables)} corrected tables, {len(data)} questions, "
                "18 graded parts, nine practice checks, nine handouts and nine films."
            )
        )

    @transaction.atomic
    def _install(self, tables, hints, question_edits, assets, *, preview):
        for patch in tables:
            _apply_table(patch)
        _publish_questions(hints, question_edits)
        for module in (
            Module.objects.select_for_update().filter(number__in=assets).order_by("number")
        ):
            _publish_parts(module)
            _add_practice_check(module)
            _install_assets(module, *assets[module.number])
        if preview:
            transaction.set_rollback(True)
