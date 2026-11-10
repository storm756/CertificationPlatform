"""Stage 2: questions, immutable versions, the MCQ schema, the XLSX import and the legacy importer.

Every question in these tests is invented. The real bank is private and never in git or tests.
"""

import json

import pytest
import tablib
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction

from apps.content.models import Module
from apps.questions import importing, legacy, schemas, services
from apps.questions.models import Question, QuestionStatus, QuestionVersion

pytestmark = pytest.mark.django_db


def body(**changes):
    data = {
        "stem": "Invented: which one is it?",
        "options": [{"id": "o1", "text": "First"}, {"id": "o2", "text": "Second"}],
        "correct": "o2",
        "hint": "A hint.",
        "gate": {},
    }
    data.update(changes)
    return data


# --- the schema ---------------------------------------------------------------------------------


def test_a_valid_mcq_body_parses():
    assert schemas.parse_body("mcq", body()).correct == "o2"


@pytest.mark.parametrize(
    "bad",
    [
        {"correct": "o9"},  # not one of the options
        {"options": [{"id": "o1", "text": "Only one"}]},  # fewer than two options
        {"options": [{"id": "o1", "text": "Same"}, {"id": "o2", "text": "same"}]},
        {"options": [{"id": "o1", "text": "A"}, {"id": "o1", "text": "B"}]},  # duplicate ids
        {"gate": {"o2": "the correct option can't be a gate option"}},
        {"gate": {"o1": ""}},  # a gate option needs a reason
        {"gate": {"o7": "not an option"}},
        {"stem": "bad \x00 control character"},
        {"surprise": "extra fields are refused"},
    ],
)
def test_invalid_mcq_bodies_are_refused(bad):
    with pytest.raises(schemas.ValidationError):
        schemas.parse_body("mcq", body(**bad))


def test_a_draft_may_lack_a_hint_but_cannot_go_live(module1):
    question = services.create_question(
        stable_id="M1-T01",
        module=module1,
        body=body(hint=""),
        tags={"pc": "PC1"},
        pool="module_quiz",
    )
    assert schemas.publish_errors("mcq", question.current_version.body) == [
        "hint: a hint is required before a question can go live"
    ]
    with pytest.raises(services.PublishError):
        services.publish(question)
    assert question.status == QuestionStatus.DRAFT


def test_publishing_needs_a_pc_tag(module1):
    question = services.create_question(
        stable_id="M1-T02", module=module1, body=body(), tags={}, pool="module_quiz"
    )
    with pytest.raises(services.PublishError) as exc:
        services.publish(question)
    assert any("PC tag" in e for e in exc.value.errors)


def test_a_valid_question_goes_live(module1):
    question = services.create_question(
        stable_id="M1-T03", module=module1, body=body(), tags={"pc": "PC2"}, pool="practice"
    )
    assert services.publish(question).status == QuestionStatus.LIVE


# --- immutable versions ------------------------------------------------------------------------


def test_a_changed_body_adds_a_version_and_leaves_the_old_one(module1):
    question = services.create_question(
        stable_id="M1-T04", module=module1, body=body(), tags={"pc": "PC1"}, pool="module_quiz"
    )
    v1 = question.current_version
    same, created = services.add_version(question, body())
    assert not created and same.pk == v1.pk
    v2, created = services.add_version(question, body(stem="Invented: a reworded stem?"))
    assert created and v2.version == 2
    v1.refresh_from_db()
    assert v1.body["stem"] == "Invented: which one is it?"
    assert question.versions.count() == 2


def test_the_model_refuses_to_edit_or_delete_a_version(module1):
    question = services.create_question(
        stable_id="M1-T05", module=module1, body=body(), tags={"pc": "PC1"}, pool="module_quiz"
    )
    version = question.current_version
    version.body = {"changed": True}
    with pytest.raises(RuntimeError):
        version.save()
    with pytest.raises(RuntimeError):
        version.delete()


def test_the_database_refuses_to_edit_or_delete_a_version(module1):
    """Even a raw UPDATE or DELETE (a script, the admin, a bug) is refused by the trigger."""
    question = services.create_question(
        stable_id="M1-T06", module=module1, body=body(), tags={"pc": "PC1"}, pool="module_quiz"
    )
    pk = question.current_version.pk
    for action in (
        lambda: QuestionVersion.objects.filter(pk=pk).update(body={"x": 1}),
        lambda: QuestionVersion.objects.filter(pk=pk)._raw_delete(QuestionVersion.objects.db),
    ):
        with pytest.raises(Exception) as exc, transaction.atomic():  # noqa: B017
            action()
        assert "immutable" in str(exc.value)
    assert QuestionVersion.objects.get(pk=pk).body["stem"].startswith("Invented")


def test_version_numbers_are_unique_per_question(module1):
    question = services.create_question(
        stable_id="M1-T07", module=module1, body=body(), tags={"pc": "PC1"}, pool="module_quiz"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionVersion.objects.create(question=question, version=1, body=body(), content_hash="x")


# --- XLSX import ------------------------------------------------------------------------------


def sheet(*rows):
    data = tablib.Dataset(headers=importing.COLUMNS)
    for row in rows:
        full = {c: "" for c in importing.COLUMNS} | row
        data.append([full[c] for c in importing.COLUMNS])
    return data


def good_row(n=1, **changes):
    return {
        "id": f"M1-X{n:02d}",
        "question": f"Invented sheet question {n}?",
        "option_a": "Alpha",
        "option_b": "Bravo",
        "option_c": "Charlie",
        "correct": "B",
        "hint": "Invented hint.",
        "pc": "PC1",
        "type": "R",
        "pool": "module_quiz",
        "points": 1,
    } | changes


def test_dry_run_reports_and_saves_nothing():
    result = importing.import_sheet(sheet(good_row(1), good_row(2)), dry_run=True)
    assert not result.has_validation_errors() and not result.has_errors()
    assert result.totals["new"] == 2
    assert Question.objects.count() == 0


def test_real_import_creates_draft_questions_with_a_version():
    result = importing.import_sheet(sheet(good_row(1), good_row(2)), dry_run=False)
    assert result.totals["new"] == 2
    question = Question.objects.get(stable_id="M1-X01")
    assert question.status == QuestionStatus.DRAFT and question.module.number == 1
    assert question.current_version.body["correct"] == "o2"
    assert question.tags == {"pc": "PC1", "type": "R"}


def test_a_live_status_column_publishes():
    importing.import_sheet(sheet(good_row(1, status="live")), dry_run=False)
    assert Question.objects.get(stable_id="M1-X01").status == QuestionStatus.LIVE


@pytest.mark.parametrize(
    ("changes", "column"),
    [
        ({"hint": ""}, "hint"),
        ({"correct": "A,B"}, "correct"),  # two correct options
        ({"correct": ""}, "correct"),
        ({"correct": "D"}, "correct"),  # an empty option
        ({"id": "Q-1"}, "id"),
        ({"id": "M99-1"}, "id"),  # no such module
        ({"option_b": "", "option_c": "Gap"}, "options"),  # a gap in A-F
        ({"option_b": ""}, "options"),  # fewer than two options
        ({"pool": "somewhere"}, "pool"),
        ({"pc": ""}, "pc"),
        ({"type": "Z"}, "type"),
        ({"points": "0"}, "points"),
        ({"gate": "A"}, "gate_reason"),  # a gate option needs a reason
        ({"gate": "B", "gate_reason": "r"}, "gate"),  # the correct option can't be a gate option
        ({"question": ""}, "question"),
    ],
)
def test_bad_rows_are_reported_by_column_in_a_dry_run(changes, column):
    result = importing.import_sheet(sheet(good_row(1), good_row(2, **changes)), dry_run=True)
    assert result.has_validation_errors()
    assert len(result.invalid_rows) == 1
    invalid = result.invalid_rows[0]
    assert invalid.number == 2  # the second data row; the header is not counted
    assert column in invalid.error_dict
    assert Question.objects.count() == 0


def test_one_bad_row_saves_nothing_in_a_real_import():
    result = importing.import_sheet(sheet(good_row(1), good_row(2, hint="")), dry_run=False)
    assert result.has_validation_errors()
    assert Question.objects.count() == 0


def test_duplicate_ids_in_one_sheet_are_reported():
    result = importing.import_sheet(sheet(good_row(1), good_row(1)), dry_run=True)
    assert result.has_validation_errors() and "id" in result.invalid_rows[0].error_dict


def test_reimporting_the_same_sheet_changes_nothing_and_a_change_adds_a_version():
    importing.import_sheet(sheet(good_row(1)), dry_run=False)
    again = importing.import_sheet(sheet(good_row(1)), dry_run=False)
    assert again.totals["skip"] == 1 and QuestionVersion.objects.count() == 1
    edited = importing.import_sheet(
        sheet(good_row(1, question="Invented, reworded?")), dry_run=False
    )
    assert edited.totals["update"] == 1
    assert Question.objects.get(stable_id="M1-X01").versions.count() == 2


def test_the_template_workbook_is_a_real_xlsx_that_imports_in_a_dry_run():
    data = tablib.Dataset().load(importing.template_workbook(), format="xlsx")
    assert list(data.headers) == importing.COLUMNS
    result = importing.import_sheet(data, dry_run=True)
    assert not result.has_validation_errors()


# --- the private legacy importer -----------------------------------------------------------------


def invented_bank(per_module=45, modules=(1, 2)):
    pcs = ["PC1", "PC2", "PC3", "PC4", "PC5", "PC6"]
    bank = {}
    for m in modules:
        bank[str(m)] = [
            {
                "id": f"M{m}-{i:02d}",
                "pc": pcs[i % 6] if i > 8 else pcs[i % 3],
                "t": "RASI"[i % 4],
                "q": f"INVENTED-STEM-{m}-{i}?",
                "o": [f"INVENTED-O-{m}-{i}-{k}" for k in range(4)],
                "a": i % 4,
            }
            for i in range(1, per_module + 1)
        ]
    return bank


def write_bank(tmp_path, bank):
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(bank), encoding="utf-8")
    return path


def test_pools_split_30_quiz_15_practice_with_at_least_5_per_pc():
    rows = invented_bank(modules=(1,))["1"]
    pools = legacy.assign_pools(rows)
    quiz = [r for r in rows if pools[r["id"]] == "module_quiz"]
    assert len(quiz) == 30 and len(rows) - len(quiz) == 15
    per_pc = {pc: sum(1 for r in quiz if r["pc"] == pc) for pc in {r["pc"] for r in rows}}
    assert min(per_pc.values()) >= 5, per_pc
    assert legacy.assign_pools(rows) == pools  # deterministic
    assert "final" not in pools.values()


def test_legacy_import_creates_drafts_never_final_and_needs_hints(tmp_path, capsys):
    path = write_bank(tmp_path, invented_bank())
    call_command("import_legacy_mcq", "--source", str(path))
    assert Question.objects.count() == 90
    assert not Question.objects.filter(pool="final").exists()
    assert set(Question.objects.values_list("status", flat=True)) == {"draft"}
    question = Question.objects.get(stable_id="M1-03")
    assert question.current_version.body["hint"] == ""
    with pytest.raises(services.PublishError):  # no hint in the legacy bank, none invented
        services.publish(question)
    assert question.current_version.body["correct"] == "o4"  # answer index 3 -> o4


def test_legacy_import_prints_counts_only_never_question_text(tmp_path, capsys):
    path = write_bank(tmp_path, invented_bank())
    call_command("import_legacy_mcq", "--source", str(path), "--dry-run")
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "have no hint" in out and "30 quiz, 15 practice" in out
    assert "INVENTED" not in out
    assert Question.objects.count() == 0


def test_legacy_import_is_create_only_and_refuses_after_edits(tmp_path):
    path = write_bank(tmp_path, invented_bank(modules=(1,)))
    call_command("import_legacy_mcq", "--source", str(path))
    call_command("import_legacy_mcq", "--source", str(path))  # a second run changes nothing
    assert Question.objects.count() == 45 and QuestionVersion.objects.count() == 45
    question = Question.objects.get(stable_id="M1-01")
    services.add_version(
        question, {**question.current_version.body, "hint": "Written by the team."}
    )
    with pytest.raises(CommandError, match="edited in the app"):
        call_command("import_legacy_mcq", "--source", str(path))


def test_legacy_import_reports_bad_rows_by_id_only(tmp_path, capsys):
    bank = invented_bank(modules=(1,))
    bank["1"][4]["a"] = 9  # answer index out of range
    call_command("import_legacy_mcq", "--source", str(write_bank(tmp_path, bank)))
    out = capsys.readouterr().out
    assert "INVALID (1)" in out and "M1-05" in out and "INVENTED" not in out
    assert Question.objects.count() == 44


def test_legacy_import_needs_the_file(tmp_path):
    with pytest.raises(CommandError, match="not found"):
        call_command("import_legacy_mcq", "--source", str(tmp_path / "missing.json"))


def test_modules_one_to_ten_exist_and_the_capstone_is_not_counted():
    assert Module.objects.count() == 10
    capstone = Module.objects.get(number=10)
    assert capstone.kind == "capstone" and capstone.counted is False
    assert Module.objects.filter(counted=True).count() == 9


# --- the admin ------------------------------------------------------------------------------------


@pytest.fixture
def staff(client, make_user):
    from allauth.mfa.models import Authenticator

    from apps.accounts.models import Role

    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    return client


def test_admin_lists_and_the_question_history_is_read_only(staff, module1):
    question = services.create_question(
        stable_id="M1-A01", module=module1, body=body(), tags={"pc": "PC1"}, pool="module_quiz"
    )
    for url in (
        "/admin/questions/question/",
        f"/admin/questions/question/{question.pk}/change/",
        "/admin/assessments/assessmentpart/",
        "/admin/assessments/attempt/",
    ):
        assert staff.get(url).status_code == 200, url
    html = staff.get(f"/admin/questions/question/{question.pk}/change/").content.decode()
    assert question.current_version.content_hash[:10] in html


def test_admin_xlsx_import_dry_run_then_confirm(staff):
    from django.core.files.uploadedfile import SimpleUploadedFile

    page = staff.get("/admin/questions/question/import/")
    assert page.status_code == 200
    workbook = SimpleUploadedFile(
        "questions.xlsx",
        sheet(good_row(1), good_row(2, hint="")).export("xlsx"),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    formats = [
        f.__name__
        for f in __import__("import_export.formats.base_formats", fromlist=["x"]).DEFAULT_FORMATS
    ]
    response = staff.post(
        "/admin/questions/question/import/",
        {"import_file": workbook, "format": formats.index("XLSX")},
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "A hint is required." in html  # the row error is shown
    assert Question.objects.count() == 0  # the preview saved nothing
