"""Regression tests for the exam-set review round: fixed released papers, the reuse rule, draft
reconciliation, workbook and release validation, batch assignment and the learner pages.
Invented questions and an invented workbook only."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.assessments import examsets, programme, services
from apps.assessments.admin import ExamSetAdmin, ExamSetItemInline
from apps.assessments.models import (
    Attempt,
    AttemptStatus,
    ExamSet,
    ExamSetItem,
    ExamSetLocked,
    ExamSetStatus,
    ItemState,
    ProgrammeAssessmentKind,
)
from apps.audit.models import AuditEvent
from apps.batches.admin import BatchAdmin
from apps.batches.models import Batch
from apps.content.models import LearnCheck, Unit, UnitVersion
from apps.questions import services as qservices
from apps.questions.models import PoolLocked, Question, QuestionLocked, QuestionStatus

from .test_exam_sets import (  # noqa: F401  (fixtures and helpers shared with the main file)
    admin_user,
    blueprint_2x3,
    draft_set,
    drawn,
    ids_of,
    learner_in,
    row,
    run,
    workbook,
    world,
)
from .test_results import answer_all_parts, final_questions

pytestmark = pytest.mark.django_db


def one_question(set_code, sets):
    return Question.objects.get(pk=sorted(ids_of(sets[set_code]))[0])


# --- 1. a released paper is fixed ---------------------------------------------------------------------


def test_release_records_the_approved_versions_marks_formats_and_modules(world):
    _, sets = world
    for item in sets["B"].items.select_related("question__module"):
        q = item.question
        assert item.version_id == q.current_version.pk and item.approved_points == q.points
        assert item.approved_format == q.format and item.approved_module_id == q.module_id


@pytest.mark.parametrize(
    "change",
    [{"points": Decimal("2")}, {"format": "mc"}, {"pool": "practice"}, {"status": "retired"}],
)
def test_a_released_question_cannot_change_marks_format_pool_or_status(world, change):
    _, sets = world
    q = one_question("B", sets)
    for field, value in change.items():
        setattr(q, field, value)
    with pytest.raises(QuestionLocked):
        q.save()


def test_a_released_question_cannot_move_to_another_module(world):
    parts, sets = world
    q = one_question("B", sets)
    q.module = parts[2][0].module if q.module_id == parts[1][0].module_id else parts[1][0].module
    with pytest.raises(QuestionLocked):
        q.save()


def test_the_database_refuses_scripts_that_bypass_the_models(world, admin_user):
    _, sets = world
    q = one_question("B", sets)
    with pytest.raises(DatabaseError), transaction.atomic():
        Question.objects.filter(pk=q.pk).update(points=5)
    with pytest.raises(DatabaseError), transaction.atomic():
        ExamSetItem.objects.filter(exam_set=sets["B"]).update(in_pretest=False)
    with pytest.raises(DatabaseError), transaction.atomic():
        ExamSetItem.objects.filter(exam_set=sets["B"]).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        ExamSet.objects.filter(pk=sets["B"].pk).update(status="draft")
    with pytest.raises(DatabaseError), transaction.atomic():
        ExamSet.objects.filter(pk=sets["B"].pk).delete()
    sets["B"].refresh_from_db()
    assert sets["B"].is_released and sets["B"].items.filter(in_pretest=True).count() == 4


def test_released_membership_cannot_be_changed_through_the_models(world, make_question):
    parts, sets = world
    item = sets["B"].items.first()
    item.in_pretest = not item.in_pretest
    with pytest.raises(ExamSetLocked):
        item.save()
    with pytest.raises(ExamSetLocked):
        item.delete()
    extra = make_question(901, module=parts[1][0].module, pool="final")
    with pytest.raises(ExamSetLocked):
        ExamSetItem.objects.create(exam_set=sets["B"], question=extra)
    sets["B"].status = ExamSetStatus.DRAFT
    with pytest.raises(ExamSetLocked):
        sets["B"].save()


def test_the_admin_inline_is_read_only_once_released_and_editable_while_draft(
    world, admin_user, make_question, blueprint_2x3
):
    _, sets = world
    inline = ExamSetItemInline(ExamSet, AdminSite())
    request = RequestFactory().get("/")
    request.user = admin_user
    draft = ExamSet.objects.create(code="Y", name="Draft")
    assert not inline.has_change_permission(request, sets["B"])
    assert inline.has_change_permission(request, draft)
    assert "state" not in inline.readonly_fields


def test_a_set_released_while_an_admin_page_was_open_refuses_the_save(world, admin_user):
    _, sets = world
    model_admin = ExamSetAdmin(ExamSet, AdminSite())
    request = RequestFactory().get("/")
    request.user = admin_user
    with pytest.raises(PermissionDenied):
        model_admin.save_model(request, sets["B"], form=None, change=True)


def test_a_final_question_used_in_an_exam_cannot_change_marks_or_module(
    world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    q = Question.objects.get(pk=sorted(drawn(pre))[0])
    q.pool = "module_quiz"
    with pytest.raises(QuestionLocked):
        q.save()  # also blocked by the released set; the exam history is protected either way


def test_existing_frozen_learners_keep_their_paper_after_a_new_draft_correction(
    world, make_user, make_batch, admin_user, make_question
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    # a correction is a NEW draft set; the released Set B and the frozen learner are untouched
    draft = ExamSet.objects.create(code="B2", name="Set B revision")
    ExamSetItem.objects.create(
        exam_set=draft, question=make_question(950, module=parts[1][0].module, pool="final")
    )
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    assert drawn(final) == ids_of(sets["B"])


# --- 2. the reuse rule ------------------------------------------------------------------------------------


def lesson_check_block(module, stable_id, status="draft"):
    unit = Unit.objects.create(module=module, slug=f"u-{stable_id.lower()}", type="reading")
    return UnitVersion.objects.create(
        unit=unit, version=1, title="Invented", source="editor", status=status,
        blocks=[{"type": "check", "question": stable_id}],
    )  # fmt: skip


def test_a_question_answered_in_a_lesson_practice_check_cannot_move_into_the_final(
    learner, make_question
):
    q = make_question(801, pool="practice")
    LearnCheck.objects.create(user=learner, question_version=q.current_version, score=Decimal(1))
    q.pool = "final"
    with pytest.raises(PoolLocked, match="lesson practice check"):
        q.save()


def test_a_question_in_a_lesson_check_block_cannot_move_into_the_final(make_question, module1):
    q = make_question(802, pool="practice")
    lesson_check_block(module1, q.stable_id)  # signed-out visitors can answer it without a record
    q.pool = "final"
    with pytest.raises(PoolLocked, match="lesson practice check"):
        q.save()


def test_release_rejects_final_questions_with_a_practice_check_history(
    blueprint_2x3, make_question, learner
):
    m1, m2 = blueprint_2x3[1][0].module, blueprint_2x3[2][0].module
    sets_q = [
        final_questions(make_question, m1, 3, 810),
        final_questions(make_question, m2, 3, 820),
    ]
    exam_set = draft_set(make_question, sets_q)
    LearnCheck.objects.create(
        user=learner, question_version=sets_q[0][0].current_version, score=Decimal(1)
    )
    lesson_check_block(m2, sets_q[1][0].stable_id, status="published")
    errors = examsets.release_errors(exam_set)
    assert any(sets_q[0][0].stable_id in e and "lesson practice check" in e for e in errors)
    assert any(sets_q[1][0].stable_id in e and "lesson practice check" in e for e in errors)


def test_older_wording_of_an_edited_module_question_still_counts_as_seen(
    blueprint_2x3, make_question, admin_user
):
    m1, m2 = blueprint_2x3[1][0].module, blueprint_2x3[2][0].module
    old = make_question(830, module=m1, pool="module_quiz")
    old_text = old.current_version.body["stem"]
    qservices.add_version(old, dict(old.current_version.body, stem="Invented new wording of 830?"))
    body = dict(old.current_version.body, stem=old_text)
    twin = qservices.create_question(
        stable_id="M1-FZ97", module=m1, body=body, tags={"pc": "PC1", "type": "R"}, pool="final"
    )
    qservices.publish(twin)
    exam_set = draft_set(
        make_question,
        [
            [twin, *final_questions(make_question, m1, 2, 840)],
            final_questions(make_question, m2, 3, 850),
        ],
    )
    assert any(
        "M1-FZ97 repeats module or practice question" in e
        for e in examsets.release_errors(exam_set)
    )


def test_the_import_applies_the_same_reuse_rule(tmp_path, blueprint_2x3, make_question, learner):
    m1 = blueprint_2x3[1][0].module
    old = make_question(860, module=m1, pool="module_quiz")
    old_text = old.current_version.body["stem"]
    qservices.add_version(old, dict(old.current_version.body, stem="Invented rewritten 860?"))
    final_q = make_question(861, module=m1, pool="final")
    Question.objects.filter(pk=final_q.pk).update(stable_id="M1-FZ02")
    LearnCheck.objects.create(user=learner, question_version=final_q.current_version, score=1)
    rows = [row("M1-FZ01", 1, scenario=old_text), row("M1-FZ02", 1), row("M1-FZ03", 1)]
    out = run(workbook(tmp_path, rows))
    assert "copies 2" in out and "accepted 1" in out
    assert "M1-FZ01 (same text as module or practice question" in out
    assert "M1-FZ02 (the question with this ID has been answered in a lesson practice check" in out


# --- 3. reconciling a draft ------------------------------------------------------------------------------------


def sheet(*ids_modules):
    return [row(i, m, pretest="Yes" if n < 2 else "No") for n, (i, m) in enumerate(ids_modules)]


def test_reimport_after_removing_a_row_rejects_the_old_row_and_keeps_its_history(
    tmp_path, blueprint_2x3
):
    rows = [row("M1-FZ01", 1, pretest="Yes"), row("M1-FZ02", 1), row("M1-FZ03", 1)]
    run(workbook(tmp_path, rows), "--apply")
    exam_set = ExamSet.objects.get(code="Z")
    assert exam_set.members().count() == 3
    preview = run(workbook(tmp_path, rows[:2]))  # the owner removed the surplus row
    assert "reject: M1-FZ03" in preview
    assert exam_set.members().count() == 3  # the preview changed nothing
    run(workbook(tmp_path, rows[:2]), "--apply")
    states = {i.question.stable_id: i.state for i in exam_set.items.select_related("question")}
    assert states == {"M1-FZ01": "member", "M1-FZ02": "member", "M1-FZ03": "rejected"}
    gone = Question.objects.get(stable_id="M1-FZ03")
    assert gone.versions.count() == 1 and gone.status == QuestionStatus.DRAFT


def test_a_row_marked_hold_is_kept_in_reserve_and_not_counted(tmp_path, blueprint_2x3):
    rows = [row("M1-FZ01", 1, pretest="Yes"), row("M1-FZ02", 1, review="Hold in reserve")]
    out = run(workbook(tmp_path, rows))
    assert "reserve 1" in out and "accepted 1" in out and "Module 1: 1 accepted" in out
    run(workbook(tmp_path, rows), "--apply")
    exam_set = ExamSet.objects.get(code="Z")
    assert exam_set.members().count() == 1
    assert exam_set.items.get(question__stable_id="M1-FZ02").state == ItemState.RESERVE
    # the owner un-holds it in the workbook: reinstated, with the same question and version
    rows[1] = row("M1-FZ02", 1)
    assert "reinstate: M1-FZ02" in run(workbook(tmp_path, rows))
    run(workbook(tmp_path, rows), "--apply")
    assert exam_set.members().count() == 2


def test_reserve_and_rejected_rows_do_not_count_toward_release(world, make_question, admin_user):
    parts, sets = world
    draft = draft_set(
        make_question,
        [final_questions(make_question, parts[1][0].module, 3, 960),
         final_questions(make_question, parts[2][0].module, 3, 970)],
    )  # fmt: skip
    extra = make_question(980, module=parts[1][0].module, pool="final")
    ExamSetItem.objects.create(exam_set=draft, question=extra, state=ItemState.RESERVE)
    assert examsets.release_errors(draft) == []
    assert examsets.release(draft, admin_user) == []
    assert draft.members().count() == 6 and draft.items.count() == 7


def test_the_preview_is_read_only_and_apply_refuses_a_released_set(tmp_path, world):
    _, sets = world
    before = (ExamSet.objects.count(), Question.objects.count(), ExamSetItem.objects.count())
    out = run(workbook(tmp_path, [row("M1-FB01", 1)]).parent / "invented.xlsx")
    assert "Preview only" in out
    assert (
        ExamSet.objects.count(),
        Question.objects.count(),
        ExamSetItem.objects.count(),
    ) == before
    import openpyxl

    book = openpyxl.load_workbook(tmp_path / "invented.xlsx")
    book["Set Z"].title = "Set B"
    book.save(tmp_path / "b.xlsx")
    assert "Set B is released" in run(tmp_path / "b.xlsx")
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="already released"):
        run(tmp_path / "b.xlsx", "--apply")


def test_import_and_release_take_the_same_row_lock(world):
    with CaptureQueriesContext(connection) as queries, transaction.atomic():
        examsets.lock_set("B")
    assert any("FOR UPDATE" in q["sql"] and "assessments_examset" in q["sql"] for q in queries)


# --- 4. clear workbook and release errors ----------------------------------------------------------------------


def test_bad_module_values_are_reported_per_row_without_crashing(tmp_path, blueprint_2x3):
    rows = [row("M1-FZ01", "1.9"), row("M1-FZ02", "one"), row("M1-FZ03", 1.0), row("M1-FZ04", 7)]
    out = run(workbook(tmp_path, rows))
    assert "M1-FZ01 (the module '1.9' is not a whole module number" in out
    assert "M1-FZ02 (the module 'one' is not a whole module number" in out
    assert "M1-FZ04 (module 7 is not a counted learning module" in out
    assert "accepted 1" in out  # 1.0 is a whole number


def test_rows_with_content_but_no_id_are_flagged_and_duplicates_are_counted(
    tmp_path, blueprint_2x3
):
    rows = [row("", 1), row("M1-FZ01", 1), row("M1-FZ01", 1), row("M1-FZ02", 1)]
    out = run(workbook(tmp_path, rows))
    assert (
        "Set Z: 4 rows · accepted 1 · reserve 0 · reused 0 · copies 0 · human review 0 · invalid 3"
        in out
    )
    assert "row 4 (the row has content but no ID)" in out
    assert out.count("the ID appears 2 times in the set") == 2


def test_a_one_module_blueprint_cannot_release_a_paper(world, make_question, admin_user):
    parts, sets = world
    final = programme.get_assessment(ProgrammeAssessmentKind.FINAL)
    final.blueprint = {"per_module": {"1": 3}, "anchors": []}
    final.save()
    draft = draft_set(make_question, [final_questions(make_question, parts[1][0].module, 3, 990)])
    errors = examsets.release_errors(draft)
    assert any("Module 2 is counted but missing from the blueprint" in e for e in errors)
    assert examsets.release(draft, admin_user) == errors
    final.blueprint = {"per_module": {"1": "many", "2": 1, "x": 3}, "anchors": []}
    final.save()
    errors = examsets.release_errors(draft)
    assert any("'x' that is not a number" in e for e in errors)
    assert any("Module 1's blueprint count" in e for e in errors) and examsets.blueprint() == {2: 1}


def test_check_and_release_agree_on_a_missing_required_tag(
    make_question, blueprint_2x3, admin_user
):
    m1, m2 = blueprint_2x3[1][0].module, blueprint_2x3[2][0].module
    qs = [final_questions(make_question, m1, 3, 1000), final_questions(make_question, m2, 3, 1010)]
    exam_set = draft_set(make_question, qs)
    bad = qs[0][2]
    Question.objects.filter(pk=bad.pk).update(format="mcq", tags={})  # mcq needs a PC tag
    errors = examsets.release_errors(exam_set)
    assert any(bad.stable_id in e and "PC tag" in e for e in errors)
    assert examsets.release(exam_set, admin_user) == errors  # reported, not raised
    assert not ExamSet.objects.get(pk=exam_set.pk).is_released


# --- 5. reliable batch assignment ------------------------------------------------------------------------------


def batch_form(model_admin, request, batch, **changes):
    data = {
        f.name: ("" if getattr(batch, f.attname) is None else getattr(batch, f.attname))
        for f in Batch._meta.concrete_fields
        if f.editable and f.name != "id"
    }
    data.update(changes)
    return model_admin.get_form(request, batch)(instance=batch, data=data)


def test_an_unrelated_edit_on_a_stale_page_keeps_the_latest_assignment(
    world, make_batch, admin_user
):
    _, sets = world
    batch = make_batch()
    examsets.assign(batch, sets["B"], admin_user)
    model_admin = BatchAdmin(Batch, AdminSite())
    request = RequestFactory().post("/")
    request.user = admin_user
    stale = Batch.objects.get(pk=batch.pk)  # admin 1 opened the page showing Set B
    opened = model_admin.get_form(request, stale)(instance=stale)
    assert opened.initial["exam_set_loaded"] == sets["B"].pk
    examsets.assign(Batch.objects.get(pk=batch.pk), sets["D"], admin_user)  # admin 2 moves it to D
    fresh = Batch.objects.get(pk=batch.pk)
    form = batch_form(
        model_admin, request, fresh, name="Renamed batch", exam_set=sets["B"].pk,
        exam_set_loaded=sets["B"].pk,
    )  # fmt: skip
    assert form.is_valid(), form.errors
    model_admin.save_model(request, form.save(commit=False), form, change=True)
    saved = Batch.objects.get(pk=batch.pk)
    assert saved.name == "Renamed batch" and saved.exam_set == sets["D"]
    changes = AuditEvent.objects.filter(action="batch.exam_set_changed", target_id=str(batch.pk))
    assert [(e.data["was"], e.data["now"]) for e in changes.order_by("id")] == [
        (None, sets["B"].pk),
        (sets["B"].pk, sets["D"].pk),
    ]  # the unrelated save added no audit event and no revert


def test_a_real_change_on_a_current_page_is_applied_and_audited(world, make_batch, admin_user):
    _, sets = world
    batch = make_batch()
    examsets.assign(batch, sets["B"], admin_user)
    model_admin = BatchAdmin(Batch, AdminSite())
    request = RequestFactory().post("/")
    request.user = admin_user
    fresh = Batch.objects.get(pk=batch.pk)
    form = batch_form(
        model_admin, request, fresh, exam_set=sets["D"].pk, exam_set_loaded=sets["B"].pk
    )
    assert form.is_valid(), form.errors
    model_admin.save_model(request, form.save(commit=False), form, change=True)
    assert Batch.objects.get(pk=batch.pk).exam_set == sets["D"]
    assert (
        AuditEvent.objects.filter(action="batch.exam_set_changed", actor_id=admin_user.pk).count()
        == 2
    )


def test_choosing_a_set_after_someone_else_changed_it_is_refused_not_overwritten(
    world, make_batch, admin_user
):
    _, sets = world
    batch = make_batch()
    examsets.assign(batch, sets["B"], admin_user)
    examsets.assign(Batch.objects.get(pk=batch.pk), sets["D"], admin_user)
    model_admin = BatchAdmin(Batch, AdminSite())
    request = RequestFactory().post("/")
    request.user = admin_user
    form = batch_form(
        model_admin,
        request,
        Batch.objects.get(pk=batch.pk),
        exam_set="",
        exam_set_loaded=sets["B"].pk,
    )
    assert not form.is_valid() and "Another admin changed" in str(form.errors)


def test_mentors_cannot_change_the_set_even_with_a_forged_form(
    world, make_batch, admin_user, mentor
):
    _, sets = world
    batch = make_batch()
    examsets.assign(batch, sets["B"], admin_user)
    model_admin = BatchAdmin(Batch, AdminSite())
    request = RequestFactory().post("/")
    request.user = mentor
    form = batch_form(
        model_admin,
        request,
        Batch.objects.get(pk=batch.pk),
        name="Mentor edit",
        exam_set=sets["D"].pk,
    )
    assert "exam_set" not in form.fields
    assert form.is_valid(), form.errors
    model_admin.save_model(request, form.save(commit=False), form, change=True)
    assert Batch.objects.get(pk=batch.pk).exam_set == sets["B"]
    with pytest.raises(PermissionDenied):
        examsets.assign(batch, sets["D"], mentor)


# --- 6. the learner pages agree with the real rules ---------------------------------------------------------------


def test_the_catalogue_reflects_whether_the_learner_has_a_released_set(
    client, world, make_user, make_batch, admin_user
):
    without = make_user(batch=make_batch())
    client.force_login(without)
    html = client.get(reverse("learn_catalogue")).content.decode()
    assert "Coming soon. See what you know" in html and "Coming soon. The final counts" in html
    ready = learner_in(make_user, make_batch, world[1]["B"], admin_user)
    client.force_login(ready)
    html = client.get(reverse("learn_catalogue")).content.decode()
    assert (
        "Coming soon. See what you know" not in html and "Coming soon. The final counts" not in html
    )
    assert reverse("programme_intro", args=["pretest"]) in html


def test_a_new_learner_with_no_set_is_not_told_to_start_the_pretest(
    client, world, make_user, make_batch
):
    learner = make_user(batch=make_batch())
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    client.force_login(learner)
    html = client.get(reverse("start")).content.decode()
    assert "Pre-test not available yet" in html and "has not been given a final exam set" in html
    assert "Welcome. Start with the pre-test" not in html and "Take the pre-test" not in html
    assert reverse("programme_intro", args=["pretest"]) not in html
    assert "Nothing left: the final is unlocked" not in html


def test_a_new_learner_with_a_set_is_offered_the_pretest(
    client, world, make_user, make_batch, admin_user
):
    learner = learner_in(make_user, make_batch, world[1]["B"], admin_user)
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    client.force_login(learner)
    html = client.get(reverse("start")).content.decode()
    assert "Welcome. Start with the pre-test" in html and "Take the pre-test" in html


def test_the_dashboard_does_not_say_unlocked_while_course_setup_blocks_the_final(
    client, world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    answer_all_parts(learner, parts, "70")
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    from apps.assessments.models import AssessmentPart

    AssessmentPart.objects.filter(pk=parts[1][1].pk).update(marks=40)  # Module 1 now has 90 marks
    client.force_login(learner)
    html = client.get(reverse("start")).content.decode()
    assert "Course setup is incomplete" in html and "Locked" in html
    assert "The final is unlocked" not in html and "Nothing left: the final is unlocked" not in html
    assert "Start the final" not in html


def test_a_running_cooldown_is_shown_before_asking_to_start_again(
    client, world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    answer_all_parts(learner, parts, "70")
    final = programme.get_assessment("final")
    final.cooldown_hours = 3
    final.save()
    a, _ = programme.start_programme(learner, "final")
    services.submit(a.pk, learner.pk)
    until = Attempt.objects.get(pk=a.pk).submitted_at + timedelta(hours=3)
    assert programme.cooldown_until(learner) == until
    client.force_login(learner)
    dash = client.get(reverse("start")).content.decode()
    assert "You can try again after" in dash and "Start the final" not in dash
    assert "Try the final again" not in dash
    intro = client.get(reverse("programme_intro", args=["final"])).content.decode()
    assert (
        "Please wait before your next try" in intro and "You can try the final again after" in intro
    )
    assert 'action="' + reverse("programme_start", args=["final"]) not in intro
    Attempt.objects.filter(pk=a.pk).update(submitted_at=timezone.now() - timedelta(hours=4))
    assert programme.cooldown_until(learner) is None
    assert "Try the final again" in client.get(reverse("start")).content.decode()


def test_the_exam_timer_and_sixty_minute_guidance_are_unchanged(
    client, world, make_user, make_batch, admin_user
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    answer_all_parts(learner, parts, "70")
    client.force_login(learner)
    intro = client.get(reverse("programme_intro", args=["final"])).content.decode()
    assert "about 60 minutes" in intro and "no time limit" in intro
    a, _ = programme.start_programme(learner, "final")
    page = client.get(reverse("attempt_page", args=[a.pk])).content.decode()
    assert "data-timer" in page or "timer" in page.lower()
    assert Attempt.objects.get(pk=a.pk).status == AttemptStatus.IN_PROGRESS
