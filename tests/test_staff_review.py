"""Stage 6 review round: the marks preview against Stage 5's real eligibility rules, the
schema-driven question editor, released-paper protection in the staff editor, and moving learners.
Invented data only."""

import re

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.urls import reverse

from apps.assessments import examsets, programme, services
from apps.assessments.models import ExamSetItem, LearnerExamSet
from apps.audit.models import AuditEvent
from apps.batches.admin import EnrolmentAdmin
from apps.batches.models import Enrolment
from apps.questions import schemas
from apps.questions.models import Question
from apps.results.policy import compute_results
from apps.staff import forms as staff_forms

from .test_exam_sets import admin_user, learner_in, world  # noqa: F401
from .test_results import answer_all_parts
from .test_staff import admin_client, pools, proposal, split_world  # noqa: F401

pytestmark = pytest.mark.django_db


def preview_digest(client, world, a, b):
    html = client.post(
        reverse("staff_marks_edit", args=[1]), proposal(world, a, b)
    ).content.decode()
    return html, re.search(r'name="digest" value="([0-9a-f]+)"', html).group(1)


# --- the marks preview matches what really happens --------------------------------------------------


def test_the_preview_saves_nothing_and_confirming_without_the_preview_digest_saves_nothing(
    admin_client, split_world
):
    w = split_world
    url = reverse("staff_marks_edit", args=[1])
    admin_client.post(url, proposal(w, 20, 80))  # preview
    for extra in ({}, {"digest": "0" * 64}):  # a direct confirm, or a stale/forged digest
        response = admin_client.post(url, {**proposal(w, 20, 80, confirm=True), **extra})
        assert response.status_code == 200 and "Nothing was saved" in response.content.decode()
    w["a"].refresh_from_db()
    assert w["a"].marks == 50 and not AuditEvent.objects.filter(action="marks.changed").exists()


def test_the_previewed_lists_are_exactly_who_gains_and_loses_after_confirming(
    admin_client, split_world
):
    w = split_world
    ids = [w["lose"].pk, w["gain"].pk, w["steady"].pk]
    before = {u for u, r in compute_results(ids).items() if r.eligible}
    html, digest = preview_digest(admin_client, w, 20, 80)
    assert w["lose"].profile.certificate_name in html and w["gain"].profile.certificate_name in html
    admin_client.post(
        reverse("staff_marks_edit", args=[1]),
        {**proposal(w, 20, 80, confirm=True), "digest": digest},
    )
    after = {u for u, r in compute_results(ids).items() if r.eligible}
    assert before - after == {w["lose"].pk} and after - before == {w["gain"].pk}


def test_marks_that_would_leave_a_counted_module_off_100_are_refused(admin_client, split_world):
    """Stage 5 keeps the final locked for everyone unless published counted marks total exactly 100,
    so the editor will not save a split that does that."""
    w = split_world
    html = admin_client.post(
        reverse("staff_marks_edit", args=[1]), proposal(w, 40, 40, confirm=True)
    ).content.decode()
    assert "would total 80" in html and "exactly 100" in html
    w["a"].refresh_from_db()
    assert w["a"].marks == 50
    # an unpublished counted part does not count towards the 100
    from apps.assessments.models import AssessmentPart

    AssessmentPart.objects.filter(pk=w["b"].pk).update(is_published=False)
    html = admin_client.post(
        reverse("staff_marks_edit", args=[1]), proposal(w, 50, 50)
    ).content.decode()
    assert "published counted marks would total 50" in html


def test_the_preview_warns_when_a_module_change_breaks_the_blueprint(admin_client, split_world):
    w = split_world
    final = programme.get_assessment("final")
    final.blueprint = {"per_module": {"1": 3}, "anchors": []}
    final.save()
    data = proposal(w, 50, 50)
    data.pop("module_counted")  # Module 1 stops counting
    for part in (w["a"], w["b"]):
        data.pop(f"counted_{part.pk}")
    html = admin_client.post(reverse("staff_marks_edit", args=[1]), data).content.decode()
    assert "blueprint would no longer match" in html and "Module 1 is in the blueprint" in html


# --- the schema-driven question editor ------------------------------------------------------------------


@pytest.mark.parametrize("fmt", sorted(schemas.SCHEMAS))
def test_every_format_has_an_editor_schema_without_references(fmt):
    model_fields = set(schemas.SCHEMAS[fmt].model_fields)
    assert model_fields <= set(
        staff_forms.form_schema(fmt)["properties"]
    )  # incl. a field named title
    import json

    schema = staff_forms.form_schema(fmt)
    text = json.dumps(schema)
    assert schema["type"] == "object" and "properties" in schema
    assert "$ref" not in text and "anyOf" not in text and "$defs" not in text

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    for obj in objects(schema):  # the editor refuses an object with neither fields nor keys
        assert "properties" in obj or "keys" in obj, obj


def test_the_editor_is_a_schema_form_not_a_json_text_box(admin_client, pools):
    html = admin_client.get(reverse("staff_question", args=[pools["quiz"].pk])).content.decode()
    assert "data-django-jsonform" in html and "react-json-form.js" in html
    import html as htmllib

    assert '"stem"' in htmllib.unescape(html)  # the schema comes from the format's pydantic model
    assert 'class="textarea json-editor"' not in html


def test_the_editor_drops_empty_optional_values_before_validation():
    body = {
        "title": "t", "ask": "a", "scene": "", "hint": "h", "why": "", "gate_message": "",
        "options": [{"text": "a", "tone": "", "gate": False}, {"text": "b", "tone": None, "gate": False}],
        "correct": 0, "keep_order": False,
    }  # fmt: skip
    cleaned = staff_forms.strip_empty("mc", body)
    assert all("tone" not in o for o in cleaned["options"])
    schemas.parse_body("mc", cleaned)


def test_the_editor_saves_a_schema_form_post_as_a_new_version(admin_client, pools):
    q = pools["quiz"]
    body = dict(q.current_version.body, stem="Invented edited stem?")
    import json

    response = admin_client.post(
        reverse("staff_question", args=[q.pk]),
        {
            "body": json.dumps(body),
            "pc": "PC2",
            "type": "R",
            "pool": "module_quiz",
            "keep_live": "on",
        },
    )
    assert response.status_code == 302
    q.refresh_from_db()
    assert q.current_version.version == 2 and q.tags["pc"] == "PC2"


# --- the staff editor respects released papers -----------------------------------------------------------------


def test_a_question_on_a_released_set_is_read_only_in_the_staff_editor(admin_client, world):
    import json

    _, sets = world
    q = Question.objects.get(pk=sorted(sets["B"].items.values_list("question_id", flat=True))[0])
    page = admin_client.get(reverse("staff_question", args=[q.pk])).content.decode()
    assert "This question is fixed" in page and "data-django-jsonform" not in page
    assert "Publish" not in page and "Save as a new version" not in page
    body = dict(q.current_version.body, stem="Invented sneaky change?")
    response = admin_client.post(
        reverse("staff_question", args=[q.pk]),
        {
            "body": json.dumps(body),
            "pc": "PC1",
            "type": "R",
            "pool": "module_quiz",
            "keep_live": "on",
        },
    )
    assert response.status_code == 302
    q.refresh_from_db()
    assert q.current_version.version == 1 and q.pool == "final" and q.status == "live"


def test_an_admin_can_still_edit_a_draft_final_question_not_yet_released(
    admin_client, make_question
):
    import json

    q = make_question(70, pool="final", live=False)
    body = dict(q.current_version.body, stem="Invented draft edit?")
    response = admin_client.post(
        reverse("staff_question", args=[q.pk]),
        {"body": json.dumps(body), "pc": "PC1", "type": "R", "pool": "final"},
    )
    assert response.status_code == 302 and q.versions.count() == 2


def test_a_mentor_still_cannot_reach_a_released_final_question(mentor_client, world):
    _, sets = world
    qid = sets["B"].items.values_list("question_id", flat=True)[0]
    for name in ("staff_question", "staff_question_preview"):
        assert mentor_client.get(reverse(name, args=[qid])).status_code == 403
    assert (
        mentor_client.post(reverse("staff_question", args=[qid]), {"body": "{}"}).status_code == 403
    )


# --- moving a learner from the admin ---------------------------------------------------------------------------------


def test_the_enrolment_admin_moves_a_learner_through_the_audited_service(
    make_batch, make_user, admin_user, world
):
    parts, sets = world
    old, new = make_batch(), make_batch()
    examsets.assign(old, sets["B"], admin_user)
    examsets.assign(new, sets["D"], admin_user)
    learner = make_user(batch=old)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    enrolment = Enrolment.objects.get(user=learner)
    model_admin = EnrolmentAdmin(Enrolment, AdminSite())
    request = RequestFactory().post("/")
    request.user = admin_user
    form = type("F", (), {"changed_data": ["batch"]})()
    enrolment.batch = new
    model_admin.save_model(request, enrolment, form, change=True)
    assert Enrolment.objects.get(user=learner).batch == new
    event = AuditEvent.objects.get(action="learner.moved")
    assert event.data == {"from_batch": old.pk, "to_batch": new.pk}
    assert LearnerExamSet.objects.get(user=learner).exam_set == sets["B"]  # the paper stays frozen
    answer_all_parts(learner, parts)
    final, _ = programme.start_programme(learner, "final")
    assert {
        i.question_version.question_id for i in final.items.select_related("question_version")
    } == set(ExamSetItem.objects.filter(exam_set=sets["B"]).values_list("question_id", flat=True))


# --- migrating an existing Stage 5 database --------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_stage_6_history_migrations_apply_on_top_of_stage_5():
    stage5 = [("assessments", "0006_released_sets_fixed"), ("batches", "0003_exam_sets"), ("questions", "0003_questionimage")]  # fmt: skip
    executor = MigrationExecutor(connection)
    executor.migrate(stage5)
    tables = set(connection.introspection.table_names())
    assert "batches_historicalbatch" not in tables and "assessments_examset" in tables
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
    tables = set(connection.introspection.table_names())
    assert {"batches_historicalbatch", "questions_historicalquestion", "assessments_historicalassessmentpart"} <= tables  # fmt: skip
    columns = {c.name for c in connection.introspection.get_table_description(connection.cursor(), "batches_historicalbatch")}  # fmt: skip
    assert "exam_set_id" in columns


def test_the_editor_form_accepts_every_invented_interactive_question_unchanged(make_interactive):
    """Round trip: the schema form's own validation and ours accept each existing body, and an
    unset optional list (e.g. chips) is dropped, not saved as []."""
    import json

    from .conftest import invented_ids

    checked = 0
    for case in invented_ids():
        q = make_interactive(case, publish=False)
        v = q.current_version
        form = staff_forms.QuestionForm(
            {"body": json.dumps(v.body), "pc": "", "type": "", "pool": "practice"},
            question=q, version=v, pools=["practice"], is_admin=True,
        )  # fmt: skip
        assert form.is_valid(), (case, dict(form.errors))
        again = form.cleaned_data["body"]
        assert (
            schemas.parse_body(q.format, again).model_dump()
            == schemas.parse_body(q.format, v.body).model_dump()
        )
        checked += 1
    assert checked >= 10


def test_optional_empty_lists_are_dropped_but_real_values_survive():
    body = {"title": "t", "rows": [{"label": "a", "steps": [], "min": None, "max": 10}]}
    assert staff_forms.strip_empty("dial", body)["rows"][0] == {"label": "a", "max": 10}
