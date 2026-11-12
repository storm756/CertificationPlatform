"""Stage 5 exam sets: batch assignment, the per-learner freeze, release checks and the private
import preview. Invented questions and an invented workbook only; the real sets stay private."""

import io

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import Role
from apps.assessments import examsets, programme, rules, services
from apps.assessments.models import (
    AssessmentPart,
    ExamSet,
    ExamSetItem,
    ExamSetStatus,
    LearnerExamSet,
    ProgrammeAssessmentKind,
)
from apps.audit.models import AuditEvent
from apps.batches.admin import BatchAdmin
from apps.batches.models import Batch, Enrolment
from apps.questions.models import Question, QuestionStatus

from .conftest import right_token
from .test_results import answer_all_parts, final_questions, make_exam_set, make_parts

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user(make_user):
    return make_user(role=Role.ADMIN)


@pytest.fixture
def world(make_question, admin_user):
    """Two modules (blueprint 3 each) and two released sets, B and D, with no shared questions."""
    parts = make_parts([1, 2])
    final = programme.get_assessment(ProgrammeAssessmentKind.FINAL)
    final.blueprint = {"per_module": {"1": 3, "2": 3}, "anchors": []}
    final.save()
    m1, m2 = parts[1][0].module, parts[2][0].module
    sets = {
        "B": make_exam_set(
            "B",
            [final_questions(make_question, m1, 3, 1), final_questions(make_question, m2, 3, 101)],
            admin_user,
        ),
        "D": make_exam_set(
            "D",
            [final_questions(make_question, m1, 3, 11), final_questions(make_question, m2, 3, 111)],
            admin_user,
        ),
    }
    return parts, sets


def ids_of(exam_set, pretest=None):
    items = exam_set.items.all()
    if pretest is not None:
        items = items.filter(in_pretest=pretest)
    return set(items.values_list("question_id", flat=True))


def drawn(a):
    return {i.question_version.question_id for i in a.items.select_related("question_version")}


def learner_in(make_user, make_batch, exam_set, admin):
    batch = make_batch()
    if exam_set is not None:
        examsets.assign(batch, exam_set, admin)
    return make_user(batch=batch)


# --- two batches, two sets --------------------------------------------------------------------------


def test_two_batches_with_different_sets_never_mix(world, make_user, make_batch, admin_user):
    parts, sets = world
    one = learner_in(make_user, make_batch, sets["B"], admin_user)
    two = learner_in(make_user, make_batch, sets["D"], admin_user)
    for learner, mine, other in ((one, sets["B"], sets["D"]), (two, sets["D"], sets["B"])):
        pre, _ = programme.start_programme(learner, "pretest")
        assert drawn(pre) == ids_of(mine, pretest=True)
        services.submit(pre.pk, learner.pk)
        answer_all_parts(learner, parts)
        final, _ = programme.start_programme(learner, "final")
        assert drawn(final) == ids_of(mine) and not drawn(final) & ids_of(other)
        assert drawn(pre) <= drawn(final)  # the same shared questions sit in the final
        assert LearnerExamSet.objects.get(user=learner).exam_set == mine


# --- admin-only, audited assignment ------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.MENTOR, Role.LEARNER])
def test_only_an_admin_can_assign_or_release_a_set(world, make_user, make_batch, role):
    _, sets = world
    someone = make_user(role=role)
    batch = make_batch()
    with pytest.raises(PermissionDenied):
        examsets.assign(batch, sets["B"], someone)
    with pytest.raises(PermissionDenied):
        examsets.release(ExamSet.objects.create(code="Z", name="z"), someone)
    assert Batch.objects.get(pk=batch.pk).exam_set is None


def test_assignment_is_audited_and_only_released_sets_can_be_assigned(
    world, make_batch, admin_user
):
    _, sets = world
    batch = make_batch()
    examsets.assign(batch, sets["B"], admin_user)
    examsets.assign(batch, sets["D"], admin_user)
    events = list(AuditEvent.objects.filter(action="batch.exam_set_changed").order_by("id"))
    assert [(e.data["was"], e.data["now"]) for e in events] == [
        (None, sets["B"].pk),
        (sets["B"].pk, sets["D"].pk),
    ]
    assert all(e.actor_id == admin_user.pk for e in events)
    draft = ExamSet.objects.create(code="Z", name="Draft")
    with pytest.raises(ValueError, match="released"):
        examsets.assign(batch, draft, admin_user)


def test_the_batch_admin_locks_the_set_for_mentors_and_routes_admin_changes_through_the_audit(
    world, make_user, make_batch, admin_user, mentor
):
    _, sets = world
    ExamSet.objects.create(code="Z", name="Draft")  # never offered
    model_admin = BatchAdmin(Batch, AdminSite())
    rf = RequestFactory()
    as_mentor, as_admin = rf.get("/"), rf.get("/")
    as_mentor.user, as_admin.user = mentor, admin_user
    assert "exam_set" in model_admin.get_readonly_fields(as_mentor)
    assert "exam_set" not in model_admin.get_readonly_fields(as_admin)
    field = model_admin.formfield_for_foreignkey(Batch._meta.get_field("exam_set"), as_admin)
    assert set(field.queryset.values_list("code", flat=True)) == {"B", "D"}
    batch = make_batch()
    form = model_admin.get_form(as_admin, batch)(
        instance=batch,
        data={
            **{
                f.name: getattr(batch, f.attname)
                for f in Batch._meta.concrete_fields
                if f.editable and f.name not in ("id", "exam_set")
            },
            "exam_set": sets["D"].pk,
        },
    )
    assert form.is_valid(), form.errors
    model_admin.save_model(as_admin, form.save(commit=False), form, change=True)
    assert Batch.objects.get(pk=batch.pk).exam_set == sets["D"]
    assert AuditEvent.objects.filter(
        action="batch.exam_set_changed", actor_id=admin_user.pk
    ).exists()


# --- unassigned and unreleased ------------------------------------------------------------------------


def test_an_unassigned_batch_shows_a_clear_unavailable_state(client, world, make_user, make_batch):
    learner = make_user(batch=make_batch())
    client.force_login(learner)
    html = client.get(reverse("programme_intro", args=["pretest"])).content.decode()
    assert "Coming soon" in html and "has not been given a final exam set" in html
    final = client.get(reverse("programme_intro", args=["final"])).content.decode()
    assert "has not been given a final exam set" in final
    with pytest.raises(services.PartNotAvailable, match="not been given"):
        programme.start_programme(learner, "pretest")
    assert not LearnerExamSet.objects.filter(user=learner).exists()


def test_an_unreleased_set_on_a_batch_is_never_served(client, world, make_user, make_batch):
    draft = ExamSet.objects.create(code="Z", name="Draft")
    batch = make_batch()
    Batch.objects.filter(pk=batch.pk).update(exam_set=draft)  # e.g. a set was pulled back
    learner = make_user(batch=batch)
    client.force_login(learner)
    html = client.get(reverse("programme_intro", args=["pretest"])).content.decode()
    assert "Coming soon" in html and "not ready yet" in html
    with pytest.raises(services.PartNotAvailable, match="not ready yet"):
        programme.start_programme(learner, "pretest")


# --- the freeze ---------------------------------------------------------------------------------------


def test_reassigning_the_batch_after_the_pretest_started_keeps_the_learner_on_their_set(
    world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")  # started, not submitted
    examsets.assign(learner.enrolment.batch, sets["D"], admin_user)
    again, created = programme.start_programme(learner, "pretest")
    assert again.pk == pre.pk and not created
    services.submit(pre.pk, learner.pk)
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    assert drawn(final) == ids_of(sets["B"])  # never a Set B pre-test with a Set D final
    newcomer = make_user(batch=learner.enrolment.batch)
    pre2, _ = programme.start_programme(newcomer, "pretest")
    assert drawn(pre2) == ids_of(sets["D"], pretest=True)  # new learners get the new set


def test_moving_batch_after_the_pretest_keeps_the_set_too(world, make_user, make_batch, admin_user):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    other = make_batch()
    examsets.assign(other, sets["D"], admin_user)
    Enrolment.objects.filter(user=learner).update(batch=other)
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    assert drawn(final) == ids_of(sets["B"])


def test_the_freeze_keeps_question_versions_even_if_a_question_gets_a_new_version(
    world, make_user, make_batch, admin_user
):
    from apps.questions import services as qservices

    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    frozen = LearnerExamSet.objects.get(user=learner).versions
    q = Question.objects.get(pk=next(iter(ids_of(sets["B"]))))
    body = dict(q.current_version.body, hint="A changed invented hint.")
    qservices.add_version(q, body)
    assert Question.objects.get(pk=q.pk).current_version.pk != frozen[str(q.pk)]
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    used = {i.question_version.question_id: i.question_version_id for i in final.items.all()}
    assert used[q.pk] == frozen[str(q.pk)]
    assert AuditEvent.objects.filter(action="exam_set.frozen", actor_id=learner.pk).count() == 1


def test_grading_pretest_is_score_only_and_final_has_bands(
    client, world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["D"], admin_user)
    client.force_login(learner)
    pre, _ = programme.start_programme(learner, "pretest")
    for item in pre.items.all():
        services.save_answer(pre.pk, learner, item.position, choice=right_token(item))
    services.submit(pre.pk, learner.pk)
    html = client.get(reverse("attempt_result", args=[pre.pk])).content.decode()
    assert "100.0%" in html and "Strong" not in html and "RIGHT-" not in html
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    for item in final.items.all():
        services.save_answer(final.pk, learner, item.position, choice=right_token(item))
    services.submit(final.pk, learner.pk)
    html = client.get(reverse("attempt_result", args=[final.pk])).content.decode()
    assert "100.0%" in html and "Strong" in html and "RIGHT-" not in html and "HINT-" not in html


# --- release checks ------------------------------------------------------------------------------------


def draft_set(make_question, module_questions, code="Z"):
    exam_set = ExamSet.objects.create(code=code, name="Invented draft")
    for questions in module_questions:
        for i, q in enumerate(questions):
            ExamSetItem.objects.create(exam_set=exam_set, question=q, in_pretest=i < 2)
    return exam_set


@pytest.fixture
def blueprint_2x3(world):
    return world[0]


def test_release_checks_counts_and_pretest_counts(make_question, blueprint_2x3, admin_user):
    m1 = blueprint_2x3[1][0].module
    short = draft_set(make_question, [final_questions(make_question, m1, 3, 201)])
    errors = examsets.release_errors(short)
    assert any("Module 2: 0 questions" in e for e in errors)
    assert any("Module 2: 0 pre-test" in e for e in errors)
    assert examsets.release(short, admin_user) == errors
    assert ExamSet.objects.get(pk=short.pk).status == ExamSetStatus.DRAFT


def test_release_rejects_reused_module_questions_and_copies_with_a_new_id(
    make_question, blueprint_2x3, admin_user, learner
):
    from apps.questions import services as qservices

    parts = blueprint_2x3
    m1, m2 = parts[1][0].module, parts[2][0].module
    module_q = make_question(301, module=m1, pool="module_quiz")
    copy = qservices.create_question(
        stable_id="M1-FZ99", module=m1, body=dict(module_q.current_version.body),
        tags={"pc": "PC1", "type": "R"}, pool="final",
    )  # fmt: skip
    qservices.publish(copy)
    fresh1 = final_questions(make_question, m1, 2, 311)
    exam_set = draft_set(
        make_question, [[*fresh1, copy], final_questions(make_question, m2, 3, 321)]
    )
    errors = examsets.release_errors(exam_set)
    assert any("M1-FZ99 repeats module or practice question" in e for e in errors)
    # a final-pool question that a learner already saw in a module assessment
    for i in range(2):
        make_question(330 + i, module=m2, pool="module_quiz")
    part = AssessmentPart.objects.create(
        module=m2, name="Invented extra part", marks=50, selection="all", counted=False
    )
    rules.publish_part(part)
    a, _ = services.start(learner, part)
    seen = Question.objects.get(pk=a.items.first().question_version.question_id)
    Question.objects.filter(pk=seen.pk).update(pool="final")  # bypassing the pool lock on purpose
    ExamSetItem.objects.filter(exam_set=exam_set, question=copy).update(question=seen)
    errors = examsets.release_errors(exam_set)
    assert any(f"{seen.stable_id} has been shown outside the final" in e for e in errors)


def test_release_rejects_wrong_marks(make_question, blueprint_2x3):
    m1, m2 = blueprint_2x3[1][0].module, blueprint_2x3[2][0].module
    heavy = make_question(401, module=m1, pool="final", points=2)
    exam_set = draft_set(
        make_question,
        [
            [heavy, *final_questions(make_question, m1, 2, 402)],
            final_questions(make_question, m2, 3, 411),
        ],
    )
    assert any("worth 2 marks" in e for e in examsets.release_errors(exam_set))


def test_release_publishes_draft_questions_and_is_audited(make_question, blueprint_2x3, admin_user):
    m1, m2 = blueprint_2x3[1][0].module, blueprint_2x3[2][0].module
    qs = [
        [make_question(500 + i, module=m1, pool="final", live=False) for i in range(3)],
        [make_question(510 + i, module=m2, pool="final", live=False) for i in range(3)],
    ]
    exam_set = draft_set(make_question, qs)
    assert examsets.release(exam_set, admin_user) == []
    assert exam_set.is_released
    assert all(
        q.status == QuestionStatus.LIVE
        for q in Question.objects.filter(stable_id__in=[x.stable_id for row in qs for x in row])
    )
    assert AuditEvent.objects.filter(action="exam_set.released", actor_id=admin_user.pk).exists()


# --- the private import preview, run on an invented workbook ---------------------------------------------


HEADER = [
    "Proposed ID", "Pre-test candidate?", "Final-pool review", "Module No", "Question Format",
    "Question Title", "Scenario / Question", "Instruction to Candidate", "Hint", "Option A",
    "Option B", "Option C", "Option D", "Correct Option", "Correct Answer",
    "Full Answer Key / Scoring Detail", "Explanation / Rationale", "Marks", "Safety Gate Item?",
    "Source",
]  # fmt: skip


def row(stable_id, module, *, pretest="No", review="Keep", fmt="Choose one", marks=1, source="New", scenario=None, correct="B"):  # fmt: skip
    return [
        stable_id, pretest, review, module, fmt, "Invented title",
        scenario or f"Invented scenario for {stable_id} that is long enough to check.",
        "Pick one.", f"INVENTED-HINT-{stable_id}", f"INV-A-{stable_id}", f"INV-SECRET-KEY-{stable_id}",
        f"INV-C-{stable_id}", f"INV-D-{stable_id}", correct, f"INV-SECRET-KEY-{stable_id}", "",
        "Invented rationale.", marks, "No", source,
    ]  # fmt: skip


def workbook(tmp_path, rows):
    import openpyxl

    book = openpyxl.Workbook()
    book.active.title = "Review"
    sheet = book.create_sheet("Set Z")
    sheet.append(["Invented final set Z"])
    sheet.append([])
    sheet.append(HEADER)
    for r in rows:
        sheet.append(r)
    path = tmp_path / "invented.xlsx"
    book.save(path)
    return path


def run(path, *args):
    out = io.StringIO()
    call_command("import_final_sets", "--source", str(path), *args, stdout=out)
    return out.getvalue()


def test_the_import_preview_reports_ids_and_counts_only_and_saves_nothing(
    tmp_path, make_question, blueprint_2x3
):
    module_q = make_question(601, module=blueprint_2x3[1][0].module, pool="module_quiz")
    rows = [
        row("M1-FZ01", 1, pretest="Yes"),
        row("M1-FZ02", 1, pretest="Yes"),
        row("M1-FZ03", 1, review="Replace: reused", source="Reused from M1"),
        row("M1-FZ04", 1, scenario=module_q.current_version.body["stem"]),  # a copy, new ID
        row("M2-FZ05", 2, marks=2),
        row("M2-FZ06", 2, fmt="Drag to sort"),
        row("M2-FZ07", 2, correct="E"),
        row("M3-FZ08", 2),  # the ID says module 3
    ]
    path = workbook(tmp_path, rows)
    out = run(path)
    assert "Set Z: 8 rows · accepted 2 · reused 1 · copies 1 · human review 1 · invalid 3" in out
    assert "M1-FZ03" in out and "M1-FZ04" in out and f"question {module_q.stable_id}" in out
    assert "Module 1: 2 accepted of 3 needed" in out and "Module 2: 0 accepted of 3 needed" in out
    assert "Preview only: nothing was saved" in out
    for leak in ("INV-SECRET-KEY", "INVENTED-HINT", "INV-A-", "Invented scenario", "rationale"):
        assert leak not in out, leak
    assert not ExamSet.objects.filter(code="Z").exists()
    assert not Question.objects.filter(stable_id__startswith="M1-FZ").exists()


def test_the_import_apply_stores_drafts_only_and_is_repeatable(tmp_path, blueprint_2x3):
    rows = [row(f"M1-FZ{i:02d}", 1, pretest="Yes" if i < 3 else "No") for i in (1, 2, 3)]
    rows += [row(f"M2-FZ{i:02d}", 2, pretest="Yes" if i < 6 else "No") for i in (4, 5, 6)]
    path = workbook(tmp_path, rows)
    run(path, "--apply")
    run(path, "--apply")  # a second run adds nothing
    exam_set = ExamSet.objects.get(code="Z")
    assert exam_set.status == ExamSetStatus.DRAFT and exam_set.items.count() == 6
    assert exam_set.items.filter(in_pretest=True).count() == 4
    questions = Question.objects.filter(stable_id__contains="-FZ")
    assert questions.count() == 6 and all(q.status == QuestionStatus.DRAFT for q in questions)
    assert all(q.versions.count() == 1 for q in questions)
    assert all(q.pool == "final" and q.format == "mc" for q in questions)
    body = questions.get(stable_id="M1-FZ01").current_version.body
    assert body["options"][body["correct"]]["text"] == "INV-SECRET-KEY-M1-FZ01"
