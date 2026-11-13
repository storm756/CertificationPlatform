"""Stage 6: the mentor dashboard, CSV export, question editing and preview, the mark-split editor
with its impact preview, the report page, and the access rules (journeys 14 and 15)."""

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.assessments.models import AssessmentPart, Attempt, AttemptStatus, ProgrammeAssessmentKind
from apps.audit.models import AuditEvent
from apps.batches.models import Batch
from apps.content.models import Module
from apps.mentors import export
from apps.questions import services as qservices
from apps.questions.models import PoolLocked, Question, QuestionStatus
from apps.results.policy import compute_results

from .conftest import HINT
from .test_results import attempt, make_parts

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def staff_world(make_batch, make_user, mentor):
    """B01 is the mentor's; B02 belongs to another mentor."""
    other = make_user(role=Role.MENTOR)
    b1 = make_batch(mentor=mentor, code="B01", name="Mine")
    b2 = make_batch(mentor=other, code="B02", name="Theirs")
    return {"b1": b1, "b2": b2, "mine": make_user(batch=b1), "theirs": make_user(batch=b2), "other": other}  # fmt: skip


@pytest.fixture
def admin_client(client, make_user):
    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    client.admin_user = admin
    return client


def denied(user_pk, path_part):
    return AuditEvent.objects.filter(action="access.denied", actor_id=user_pk, data__path__contains=path_part).exists()  # fmt: skip


# --- journey 14: mentors see only their own batches --------------------------------------------------------


def test_journey14_a_mentor_gets_403_for_another_batchs_data_and_it_is_logged(
    mentor_client, mentor, staff_world
):
    other = staff_world["b2"]
    for url in (reverse("mentor_batch", args=[other.pk]), reverse("mentor_learner", args=[staff_world["theirs"].pk])):  # fmt: skip
        assert mentor_client.get(url).status_code == 403
    assert mentor_client.post(reverse("mentor_batch_export", args=[other.pk])).status_code == 403
    assert mentor_client.post(reverse("mentor_batch_auto_issue", args=[other.pk]), {"auto_issue": "on"}).status_code == 403  # fmt: skip
    other.refresh_from_db()
    assert not other.auto_issue
    assert AuditEvent.objects.filter(action="access.denied", actor_id=mentor.pk).count() >= 4
    assert not AuditEvent.objects.filter(action="batch.exported").exists()


def test_a_mentor_dashboard_never_lists_other_batches_learners(mentor_client, staff_world):
    html = mentor_client.get(reverse("mentor_batch", args=[staff_world["b1"].pk])).content.decode()
    assert staff_world["mine"].email in html and staff_world["theirs"].email not in html


def test_a_learner_cannot_open_staff_pages(learner_client):
    for name in ("staff_questions", "staff_marks", "staff_report"):
        assert learner_client.get(reverse(name)).status_code == 403


# --- journey 14: final-pool questions are admin-only ---------------------------------------------------------


@pytest.fixture
def pools(make_question):
    quiz = make_question(1, pool="module_quiz")
    practice = make_question(2, pool="practice")
    final = make_question(3, pool="final")
    return {"quiz": quiz, "practice": practice, "final": final}


def test_journey14_a_mentor_cannot_open_a_final_pool_question(mentor_client, mentor, pools):
    final = pools["final"]
    for url in (reverse("staff_question", args=[final.pk]), reverse("staff_question_preview", args=[final.pk])):  # fmt: skip
        assert mentor_client.get(url).status_code == 403
    assert mentor_client.post(reverse("staff_question", args=[final.pk]), {"body": "{}", "pool": "final"}).status_code == 403  # fmt: skip
    assert mentor_client.post(reverse("staff_question_publish", args=[final.pk])).status_code == 403
    assert AuditEvent.objects.filter(action="access.denied", actor_id=mentor.pk).count() >= 4


def test_the_mentor_question_list_hides_the_final_pool_even_when_asked_for_it(mentor_client, pools):
    for query in ("", "?pool=final"):
        html = mentor_client.get(reverse("staff_questions") + query).content.decode()
        assert pools["quiz"].stable_id in html or query
        assert pools["final"].stable_id not in html


def test_a_mentor_cannot_move_a_question_into_the_final_pool(mentor_client, pools):
    quiz = pools["quiz"]
    body = json.dumps(quiz.current_version.body)
    response = mentor_client.post(reverse("staff_question", args=[quiz.pk]), {"body": body, "pool": "final", "pc": "PC1", "type": "R"})  # fmt: skip
    assert response.status_code == 403
    assert Question.objects.get(pk=quiz.pk).pool == "module_quiz"


def test_an_admin_can_open_and_preview_a_final_pool_question(admin_client, pools):
    final = pools["final"]
    assert admin_client.get(reverse("staff_question", args=[final.pk])).status_code == 200
    assert admin_client.get(reverse("staff_question_preview", args=[final.pk])).status_code == 200
    assert pools["final"].stable_id in admin_client.get(reverse("staff_questions")).content.decode()


def test_the_django_admin_question_list_hides_final_questions_from_non_admin_staff(
    pools, make_user, rf
):
    from django.contrib import admin as dj_admin

    from apps.questions.admin import QuestionAdmin

    model_admin = QuestionAdmin(Question, dj_admin.site)
    request = rf.get("/")
    request.user = make_user(role=Role.MENTOR, is_staff=True)
    assert pools["final"] not in model_admin.get_queryset(request)
    request.user = make_user(role=Role.ADMIN, is_staff=True)
    assert pools["final"] in model_admin.get_queryset(request)


# --- editing and previewing questions ------------------------------------------------------------------------


def edited_body(question, stem):
    body = json.loads(json.dumps(question.current_version.body))
    body["stem"] = stem
    return json.dumps(body)


def test_a_mentor_edit_adds_a_version_and_sends_a_live_question_back_to_draft(mentor_client, pools):
    q = pools["quiz"]
    assert q.status == QuestionStatus.LIVE
    response = mentor_client.post(
        reverse("staff_question", args=[q.pk]),
        {
            "body": edited_body(q, "A better invented stem?"),
            "pool": "module_quiz",
            "pc": "PC1",
            "type": "R",
        },
    )
    assert response.status_code == 302
    q.refresh_from_db()
    assert q.status == QuestionStatus.DRAFT and q.versions.count() == 2
    assert (
        q.versions.get(version=1).body["stem"] != "A better invented stem?"
    )  # the old version is untouched
    assert AuditEvent.objects.filter(action="question.edited", target_id=str(q.pk), data__went_to_draft=True).exists()  # fmt: skip


def test_a_bad_edit_shows_readable_errors_and_saves_nothing(mentor_client, pools):
    q = pools["quiz"]
    for body in ("not json", "[]", json.dumps({"stem": "x", "options": [], "correct": "o9"})):
        response = mentor_client.post(reverse("staff_question", args=[q.pk]), {"body": body, "pool": "module_quiz", "pc": "PC1", "type": "R"})  # fmt: skip
        assert response.status_code == 200 and b"could not be saved" in response.content
    assert q.versions.count() == 1 and Question.objects.get(pk=q.pk).status == QuestionStatus.LIVE


def test_an_admin_can_keep_a_valid_edit_live_and_publish_a_draft(admin_client, pools):
    q = pools["quiz"]
    admin_client.post(reverse("staff_question", args=[q.pk]), {"body": edited_body(q, "Kept live?"), "pool": "module_quiz", "pc": "PC1", "type": "R", "keep_live": "on"})  # fmt: skip
    q.refresh_from_db()
    assert q.status == QuestionStatus.LIVE and q.versions.count() == 2
    admin_client.post(reverse("staff_question", args=[q.pk]), {"body": edited_body(q, "Back to draft?"), "pool": "module_quiz", "pc": "PC1", "type": "R"})  # fmt: skip
    q.refresh_from_db()
    assert q.status == QuestionStatus.DRAFT
    assert admin_client.post(reverse("staff_question_publish", args=[q.pk])).status_code == 302
    q.refresh_from_db()
    assert (
        q.status == QuestionStatus.LIVE
        and AuditEvent.objects.filter(action="question.published").exists()
    )


def test_a_mentor_cannot_publish(mentor_client, pools):
    q = pools["quiz"]
    qservices.retire(q)
    assert mentor_client.post(reverse("staff_question_publish", args=[q.pk])).status_code == 403


def test_the_pool_rule_applies_in_the_editor(admin_client, pools, learner, make_part):
    from apps.assessments import services

    part = make_part()
    attempt_, _ = services.start(learner, part)
    shown = Question.objects.get(pk=attempt_.items.first().question_version.question_id)
    body = json.dumps(shown.current_version.body)
    response = admin_client.post(reverse("staff_question", args=[shown.pk]), {"body": body, "pool": "final", "pc": "PC1", "type": "R"})  # fmt: skip
    assert response.status_code == 200 and b"cannot move into the final pool" in response.content
    assert Question.objects.get(pk=shown.pk).pool == "module_quiz"
    with pytest.raises(PoolLocked):
        shown.pool = "final"
        shown.save()


def test_the_preview_shows_what_a_learner_gets_and_no_answers(mentor_client, pools):
    q = pools["quiz"]
    html = mentor_client.get(reverse("staff_question_preview", args=[q.pk])).content.decode()
    assert "Preview as learner" in html and "Invented question number 1" in html
    assert '"correct"' not in html and 'value="o2"' not in html  # tokens, never the internal ids
    assert HINT.format(n=1) in html  # staff-only hint, outside the learner view
    assert Attempt.objects.count() == 0  # nothing is created by a preview


def test_the_preview_of_an_interactive_question_carries_only_the_projection(
    mentor_client, make_interactive
):
    q = make_interactive("inv-cards")
    html = mentor_client.get(reverse("staff_question_preview", args=[q.pk])).content.decode()
    assert "data-engine" in html and "data-q=" in html
    assert "&quot;a&quot;" not in html and "gate_if_missed" not in html


# --- the mentor dashboard ---------------------------------------------------------------------------------------


def test_the_dashboard_shows_module_percentages_a_red_heatmap_stuck_and_awaiting(
    mentor_client, staff_world, make_user, mentor
):
    parts = make_parts([1, 2])
    b1 = staff_world["b1"]
    strong, weak, idle = staff_world["mine"], make_user(batch=b1), make_user(batch=b1)
    for p in (parts[1][0], parts[1][1], parts[2][0], parts[2][1]):
        attempt(strong, part=p, score="80")
    attempt(strong, kind=ProgrammeAssessmentKind.PRETEST)
    attempt(strong, kind=ProgrammeAssessmentKind.FINAL, score="75")
    for n in (1, 2, 3):
        attempt(weak, part=parts[1][0], number=n, score="30")
    attempt(weak, part=parts[1][1], score="30")
    from apps.batches.models import Enrolment

    Enrolment.objects.filter(user=idle).update(joined_at=timezone.now() - timedelta(days=20))
    html = mentor_client.get(reverse("mentor_batch", args=[b1.pk])).content.decode()
    assert "80.0" in html and "heat--fail" in html  # the weak learner's 30.0 is red
    assert "below 50% after 3 attempts" in html
    assert (
        "Approve all 1" in html
        and strong.profile.certificate_name
        in html.split("Awaiting approval")[1].split("Issued this week")[0]
    )
    assert idle.profile.certificate_name in html.split("may be stuck")[1].split("Roster")[0]


def test_the_auto_issue_switch_is_set_by_the_batch_mentor_and_audited(mentor_client, staff_world):
    b1 = staff_world["b1"]
    mentor_client.post(reverse("mentor_batch_auto_issue", args=[b1.pk]), {"auto_issue": "on"})
    b1.refresh_from_db()
    assert b1.auto_issue
    assert AuditEvent.objects.filter(action="batch.auto_issue_changed", data__now=True).exists()
    mentor_client.post(reverse("mentor_batch_auto_issue", args=[b1.pk]), {})
    b1.refresh_from_db()
    assert not b1.auto_issue


# --- CSV export that is safe to open in Excel ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["=1+1", "+1", "-2", "@SUM(A1)", "\t=x", "\r=x", '  =HYPERLINK("x")']
)
def test_dangerous_cells_are_neutralised(value):
    assert export.safe_cell(value).startswith("'")


@pytest.mark.parametrize("value", ["Asha", "आशा", "", None, "12.5", "a=b"])
def test_ordinary_cells_are_unchanged(value):
    assert export.safe_cell(value) == ("" if value is None else str(value))


def test_the_export_is_a_scoped_audited_post_with_inert_formulas(
    mentor_client, mentor, staff_world, make_user
):
    b1 = staff_world["b1"]
    evil = make_user(batch=b1)
    evil.profile.certificate_name = '=HYPERLINK("http://evil.example","click")'
    evil.profile.save()
    assert mentor_client.get(reverse("mentor_batch_export", args=[b1.pk])).status_code == 405
    response = mentor_client.post(reverse("mentor_batch_export", args=[b1.pk]))
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert 'attachment; filename="B01-results.csv"' in response["Content-Disposition"]
    assert (
        response["Cache-Control"] == "no-store" and response["X-Content-Type-Options"] == "nosniff"
    )
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # a BOM so Excel reads Hindi, Marathi and Gujarati names
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][:4] == ["Batch", "Name", "Email", "Status"]
    names = [r[1] for r in rows[1:]]
    assert '\'=HYPERLINK("http://evil.example","click")' in names
    assert not any(cell.startswith(("=", "+", "-", "@", "\t")) for row in rows for cell in row)
    assert staff_world["theirs"].email not in text  # only this batch
    event = AuditEvent.objects.get(action="batch.exported")
    assert event.data["rows"] == 2 and event.target_id == str(b1.pk) and event.actor_id == mentor.pk
    assert "evil" not in json.dumps(event.data)  # the audit holds counts and ids, not names


# --- journey 15: the mark-split editor and its impact preview -------------------------------------------------------


@pytest.fixture
def split_world(make_user, make_batch):
    parts = make_parts([1])
    a, b = parts[1]
    batch = make_batch()
    lose, gain, steady = make_user(batch=batch), make_user(batch=batch), make_user(batch=batch)
    for user, (sa, sb) in ((lose, ("80", "20")), (gain, ("30", "60")), (steady, ("90", "90"))):
        attempt(user, part=a, score=sa)
        attempt(user, part=b, score=sb)
        attempt(user, kind=ProgrammeAssessmentKind.PRETEST)
        attempt(user, kind=ProgrammeAssessmentKind.FINAL, score="70")
    return {"a": a, "b": b, "lose": lose, "gain": gain, "steady": steady}


def proposal(world, a_marks, b_marks, *, counted=True, confirm=False):
    data = {"module_counted": "on", f"marks_{world['a'].pk}": str(a_marks), f"marks_{world['b'].pk}": str(b_marks)}  # fmt: skip
    if counted:
        data[f"counted_{world['a'].pk}"] = "on"
        data[f"counted_{world['b'].pk}"] = "on"
    if confirm:
        data["confirm"] = "1"
    return data


def test_journey15_the_preview_names_who_gains_and_loses_and_saves_nothing(
    admin_client, split_world
):
    w = split_world
    before = compute_results([w["lose"].pk, w["gain"].pk, w["steady"].pk])
    assert (
        before[w["lose"].pk].eligible and not before[w["gain"].pk].eligible
    )  # 50.0 passes, 45.0 fails
    response = admin_client.post(reverse("staff_marks_edit", args=[1]), proposal(w, 20, 80))
    assert response.status_code == 200
    html = response.content.decode()
    assert (
        "Impact preview" in html
        and "<strong>1</strong> lose eligibility, <strong>1</strong> gain it" in html
    )
    assert w["lose"].profile.certificate_name in html and w["gain"].profile.certificate_name in html
    assert "Confirm and save" in html
    w["a"].refresh_from_db()
    w["b"].refresh_from_db()
    assert (w["a"].marks, w["b"].marks) == (50, 50)  # a preview changes nothing
    assert not AuditEvent.objects.filter(action="marks.changed").exists()


def confirmed(client, world, a_marks, b_marks):
    """Preview, then confirm with the digest the preview page carries (what the browser does)."""
    import re

    url = reverse("staff_marks_edit", args=[1])
    html = client.post(url, proposal(world, a_marks, b_marks)).content.decode()
    digest = re.search(r'name="digest" value="([0-9a-f]+)"', html).group(1)
    return client.post(url, {**proposal(world, a_marks, b_marks, confirm=True), "digest": digest})


def test_journey15_confirming_changes_the_results_and_is_audited(admin_client, split_world):
    w = split_world
    response = confirmed(admin_client, w, 20, 80)
    assert response.status_code == 302
    w["a"].refresh_from_db()
    w["b"].refresh_from_db()
    assert (w["a"].marks, w["b"].marks) == (20, 80)
    after = compute_results([w["lose"].pk, w["gain"].pk, w["steady"].pk])
    assert (
        not after[w["lose"].pk].eligible
        and after[w["gain"].pk].eligible
        and after[w["steady"].pk].eligible
    )
    event = AuditEvent.objects.get(action="marks.changed")
    assert event.data["lose"] == 1 and event.data["gain"] == 1 and event.data["module"] == 1
    assert event.actor_id == admin_client.admin_user.pk
    assert w["a"].history.count() >= 2  # simple-history kept the earlier value


def test_a_preview_of_a_new_counted_part_uses_the_same_results_code(admin_client, split_world):
    w = split_world
    from apps.assessments.models import AssessmentPart

    extra = AssessmentPart.objects.create(module=w["a"].module, name="Part C", marks=0, counted=False, is_published=True)  # fmt: skip
    data = proposal(w, 25, 25)
    data[f"marks_{extra.pk}"] = "50"
    data[f"counted_{extra.pk}"] = "on"  # a brand-new part becomes counted: nobody has answered it
    html = admin_client.post(reverse("staff_marks_edit", args=[1]), data).content.decode()
    # nobody has attempted Part C, so 25 + 25 + 0 fails the two who were passing
    assert "<strong>2</strong> lose eligibility" in html
    extra.refresh_from_db()
    assert not extra.counted


def test_marks_over_100_or_not_numbers_are_refused_and_nothing_is_saved(admin_client, split_world):
    w = split_world
    for a_marks, b_marks in ((70, 60), ("x", 50), (101, 0)):
        html = admin_client.post(
            reverse("staff_marks_edit", args=[1]), proposal(w, a_marks, b_marks, confirm=True)
        ).content.decode()
        assert "Please fix this" in html
    w["a"].refresh_from_db()
    assert w["a"].marks == 50 and not AuditEvent.objects.filter(action="marks.changed").exists()


def test_only_admins_can_use_the_mark_split_editor(mentor_client, split_world):
    assert mentor_client.get(reverse("staff_marks")).status_code == 403
    response = mentor_client.post(
        reverse("staff_marks_edit", args=[1]), proposal(split_world, 20, 80, confirm=True)
    )
    assert response.status_code == 403
    split_world["a"].refresh_from_db()
    assert split_world["a"].marks == 50


def test_the_preview_reports_real_eligibility_and_the_marks_only_effect_separately(
    admin_client, split_world
):
    """With the course set-up incomplete nobody is eligible before or after (the real rule), so the
    headline is 0 and 0; the marks alone would move one learner each way, and that is shown too."""
    Module.objects.filter(number=2).update(
        counted=True
    )  # a counted module with no assessment: a gap
    html = admin_client.post(
        reverse("staff_marks_edit", args=[1]), proposal(split_world, 20, 80)
    ).content.decode()
    assert "<strong>0</strong> lose eligibility, <strong>0</strong> gain it" in html
    assert "ignoring course set-up gaps: 1 would lose and 1 would gain" in html
    assert (
        "course set-up would still be incomplete" in html
        and "Module 2 has no published assessment" in html
    )


# --- the report page and the admin actions ----------------------------------------------------------------------------


def test_the_report_shows_batches_gain_items_and_email_to_admins_only(admin_client, split_world):
    html = admin_client.get(reverse("staff_report")).content.decode()
    assert "Knowledge gain" in html and "Item statistics" in html and "Email budget today" in html
    assert "Registered" in html and "target 25%" in html


def test_the_report_is_forbidden_to_mentors(mentor_client):
    assert mentor_client.get(reverse("staff_report")).status_code == 403


def test_knowledge_gain_appears_per_batch(admin_client, split_world):
    from apps.assessments import programme

    assert programme.get_assessment(
        "pretest"
    )  # the fixture already made pre-test attempts without items
    html = admin_client.get(reverse("staff_report")).content.decode()
    assert "—" in html  # no anchor items in these invented attempts, so no gain to report yet


def test_the_batch_admin_can_open_and_close_registration(admin_client, make_batch):
    batch = make_batch(accepting=False)
    url = reverse("admin:batches_batch_changelist")
    admin_client.post(url, {"action": "open_registration", "_selected_action": [batch.pk]})
    batch.refresh_from_db()
    assert batch.accepting
    admin_client.post(url, {"action": "close_registration", "_selected_action": [batch.pk]})
    batch.refresh_from_db()
    assert not batch.accepting
    assert (
        AuditEvent.objects.filter(action="batch.registration_updated", data__via="admin").count()
        == 2
    )


def test_history_is_kept_for_batches_enrolments_questions_and_parts(make_batch, make_user, pools):
    batch = make_batch(accepting=False)
    batch.accepting = True
    batch.save()
    assert batch.history.count() == 2
    q = pools["quiz"]
    q.status = QuestionStatus.RETIRED
    q.save()
    assert q.history.count() >= 2
    user = make_user(batch=batch)
    assert user.enrolment.history.count() == 1
    part = make_parts([1])[1][0]
    part.marks = 40
    part.save()
    assert part.history.count() == 2


_ = (Batch, AssessmentPart, AttemptStatus)


def test_a_module_with_no_assessment_is_not_painted_red(mentor_client, staff_world):
    make_parts([1])
    Module.objects.filter(number=2).update(
        counted=True
    )  # no parts: shown as a dash, not as a failure
    html = mentor_client.get(reverse("mentor_batch", args=[staff_world["b1"].pk])).content.decode()
    assert html.count("heat--fail") == 1 and "—" in html  # only module 1 (0.0) is red
