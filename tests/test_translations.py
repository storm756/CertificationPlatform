"""Stage 8: the Translation table, t(), staleness, the reviewer workflow and the XLSX round trip."""

from io import BytesIO

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.accounts.models import Role
from apps.content import services as content_services
from apps.content.models import Unit
from apps.translations import keys, rules, xlsx
from apps.translations.models import Translation, TranslationStatus
from apps.translations.service import Lookup, note, t, translate_blocks
from apps.translations.sources import course_sources, sources_by_key

pytestmark = pytest.mark.django_db

BLOCKS = [
    {"type": "heading", "text": "What is it?", "level": 2},
    {"type": "paragraph", "spans": [{"text": "Lock your "}, {"text": "phone", "bold": True}, {"text": "."}]},
    {"type": "list", "items": ["Use a passphrase.", "Turn on two-step login."], "ordered": False},
    {"type": "reveal", "label": "Predict, then reveal", "prompt": "What first?", "answer": "Call 1930."},
    {"type": "remember", "blocks": [{"type": "paragraph", "spans": [{"text": "Never share an OTP."}]}]},
]  # fmt: skip


def row(key, english, text, status=TranslationStatus.DRAFT, lang="hi", **extra):
    return Translation.objects.create(
        key=key, language=lang, text=text, source_text=english,
        source_hash=keys.source_hash(english), status=status, **extra,
    )  # fmt: skip


@pytest.fixture
def unit(module1):
    module1.title = "Cyber hygiene"
    module1.tagline = "Lock your digital doors."
    module1.overview = {"what": "Small habits.", "outcomes": ["Spot a scam."]}
    module1.save()
    u = Unit.objects.create(module=module1, slug="t1", type="reading", order=1)
    version = content_services.add_version(u, "Introduction", BLOCKS, source="editor")
    content_services.publish(version, None, system=True)
    return u


@pytest.fixture
def admin_user(make_user):
    return make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    user = type(user).objects.get(pk=user.pk)  # drop the permission cache
    return user


# --- keys -----------------------------------------------------------------------------------------


def test_block_keys_cover_text_and_join_paragraphs():
    pairs = dict(keys.block_texts("blk:1.t1", BLOCKS))
    assert pairs["blk:1.t1:0:text"] == "What is it?"
    assert pairs["blk:1.t1:1:text"] == "Lock your phone."
    assert pairs["blk:1.t1:2:items.1"] == "Turn on two-step login."
    assert pairs["blk:1.t1:3:answer"] == "Call 1930."
    assert pairs["blk:1.t1:4:0:text"] == "Never share an OTP."
    assert not any(k.endswith(":type") or k.endswith(":level") for k in pairs)


def test_crosswords_have_no_translatable_text():
    assert keys.QUESTION_TEXT["crossword"] == []


def test_hash_ignores_whitespace_only():
    assert keys.source_hash("Lock  your\nphone") == keys.source_hash("Lock your phone")
    assert keys.source_hash("Lock your phone") != keys.source_hash("Lock your phone!")


# --- t() and staleness ----------------------------------------------------------------------------


def test_t_rules(admin_user):
    row("k:1", "Hello", "नमस्ते", TranslationStatus.REVIEWED, reviewed_by=admin_user)
    row("k:2", "Bye", "अलविदा")
    assert t("k:1", "Hello", "hi") == "नमस्ते"
    assert t("k:1", "Hello", "en") == "Hello"
    assert t("k:1", "Hello", "mr") == "Hello"  # missing language
    assert t("k:2", "Bye", "hi") == "Bye"  # a draft, drafts not allowed
    assert t("k:2", "Bye", "hi", allow_draft=True) == "अलविदा"
    assert t("k:1", "Hello there", "hi") == "Hello there"  # stale: the English changed


def test_changed_english_line_shows_as_stale(unit, admin_user):
    english = "What is it?"
    row("blk:1.t1:0:text", english, "यह क्या है?", TranslationStatus.REVIEWED, reviewed_by=admin_user)
    from apps.translations.admin import coverage

    assert {c["module"]: c for c in coverage()}[1]["hi"]["reviewed"] == 1
    edited = [dict(BLOCKS[0], text="What is it, exactly?"), *BLOCKS[1:]]
    version = content_services.add_version(unit, "Introduction", edited, source="editor")
    content_services.publish(version, None, system=True)
    assert sources_by_key(1)["blk:1.t1:0:text"].english == "What is it, exactly?"
    assert {c["module"]: c for c in coverage()}[1]["hi"]["stale"] == 1
    lookup = Lookup.load("hi", ["blk:1.t1:0:text"], allow_draft=True)
    assert lookup.get("blk:1.t1:0:text", "What is it, exactly?") == "What is it, exactly?"
    # the export marks it stale too
    ws = load_workbook(BytesIO(xlsx.export_module(1))).active
    line = next(r for r in ws.iter_rows(values_only=True) if r[0] == "blk:1.t1:0:text")
    assert line[1] == "What is it, exactly?" and line[3] == "stale"


def test_translate_blocks_keeps_structure_and_tags_drafts(admin_user):
    row("blk:1.t1:1:text", "Lock your phone.", "अपना फ़ोन लॉक करें।")
    row("blk:1.t1:3:answer", "Call 1930.", "1930 पर कॉल करें।", TranslationStatus.REVIEWED, reviewed_by=admin_user)  # fmt: skip
    wanted = [k for k, _ in keys.block_texts("blk:1.t1", BLOCKS)]
    lookup = Lookup.load("hi", wanted, allow_draft=True)
    out = translate_blocks("blk:1.t1", BLOCKS, lookup)
    assert out[1]["spans"] == [
        {"text": "अपना फ़ोन लॉक करें।", "bold": False, "italic": False, "href": ""}
    ]
    assert out[3]["answer"] == "1930 पर कॉल करें।"
    assert out[3]["type"] == "reveal" and len(out) == len(BLOCKS)
    assert BLOCKS[1]["spans"][0]["text"] == "Lock your "  # the stored blocks are untouched
    assert lookup.used_draft


# --- pages ----------------------------------------------------------------------------------------


def test_unit_page_in_hindi_with_draft_tag(unit, learner, learner_client):
    row("blk:1.t1:title", "Introduction", "परिचय")
    row("blk:1.t1:0:text", "What is it?", "यह क्या है?")
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    html = learner_client.get(reverse("learn_unit", args=[1, "t1"])).content.decode()
    assert "परिचय" in html
    assert "यह क्या है?" in html
    assert "badge--mustard" in html  # the "draft translation" tag


def test_reveal_answer_is_translated(unit, learner, learner_client):
    row("blk:1.t1:3:answer", "Call 1930.", "1930 पर कॉल करें।")
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    response = learner_client.post(reverse("learn_block", args=[1, "t1", 3]))
    assert response.json()["answer"] == "1930 पर कॉल करें।"


def test_module_page_title_and_overview(unit, learner, learner_client):
    row("mod:1:title", "Cyber hygiene", "साइबर स्वच्छता")
    row("mod:1:overview.outcomes.0", "Spot a scam.", "धोखा पहचानें।")
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    html = learner_client.get(reverse("learn_module", args=[1])).content.decode()
    assert "साइबर स्वच्छता" in html and "धोखा पहचानें।" in html


def test_crossword_note_reviewed_only(admin_user):
    english = keys.NOTES["m8-crosswords-english"]
    r = row("note:m8-crosswords-english", english, "क्रॉसवर्ड अंग्रेज़ी में रहेंगे।")
    assert note("m8-crosswords-english", "hi") == english  # draft: English until reviewed (D7)
    r.status, r.reviewed_by = TranslationStatus.REVIEWED, admin_user
    r.save()
    assert note("m8-crosswords-english", "hi") == "क्रॉसवर्ड अंग्रेज़ी में रहेंगे।"


# --- reviewer workflow ----------------------------------------------------------------------------


def test_reviewer_rules(make_user):
    uploader = grant(make_user(role=Role.ADMIN, is_staff=True), "upload_translations", "review_hi")
    reviewer = grant(make_user(role=Role.ADMIN, is_staff=True), "review_hi")
    other = grant(make_user(role=Role.ADMIN, is_staff=True), "review_mr")
    line, _ = rules.save_line(key="k:1", language="hi", text="नमस्ते", english="Hello", user=uploader, origin="test")  # fmt: skip
    assert rules.review_refusal(uploader, line, "Hello") == "You uploaded this line, so someone else must review it."  # fmt: skip
    assert "not a reviewer" in rules.review_refusal(other, line, "Hello")
    assert "English changed" in rules.review_refusal(reviewer, line, "Hello!")
    rules.mark_reviewed(reviewer, line, "Hello")
    line.refresh_from_db()
    assert line.status == TranslationStatus.REVIEWED and line.reviewed_by == reviewer
    # a changed upload goes back to draft
    line, outcome = rules.save_line(key="k:1", language="hi", text="नमस्कार", english="Hello", user=uploader, origin="test")  # fmt: skip
    assert (
        outcome == "changed" and line.status == TranslationStatus.DRAFT and line.reviewed_by is None
    )
    # the same text again leaves a reviewed line reviewed
    rules.mark_reviewed(reviewer, line, "Hello")
    line, outcome = rules.save_line(key="k:1", language="hi", text="नमस्कार", english="Hello", user=uploader, origin="test")  # fmt: skip
    assert outcome == "same" and line.status == TranslationStatus.REVIEWED


# --- XLSX round trip ------------------------------------------------------------------------------


def sheet(rows, header=("key", "English", "Hindi")):
    book = Workbook()
    ws = book.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    out = BytesIO()
    book.save(out)
    return SimpleUploadedFile("t.xlsx", out.getvalue())


def test_export_lists_every_key_and_status(unit, admin_user):
    row("blk:1.t1:title", "Introduction", "परिचय")
    data = xlsx.export_module(1)
    ws = load_workbook(BytesIO(data)).active
    values = list(ws.iter_rows(values_only=True))
    assert values[0][:4] == ("key", "English", "Hindi", "Hindi status")
    by_key = {v[0]: v for v in values[1:]}
    assert by_key["blk:1.t1:title"][2:4] == ("परिचय", "draft")
    assert by_key["blk:1.t1:0:text"][3] == "missing"
    assert set(by_key) == {s.key for s in course_sources(1)}


def test_import_round_trip(unit, admin_user):
    result = xlsx.import_module(1, sheet([("blk:1.t1:title", "Introduction", "परिचय")]), admin_user)
    assert result.created == 1
    line = Translation.objects.get(key="blk:1.t1:title", language="hi")
    assert line.status == TranslationStatus.DRAFT and line.uploaded_by == admin_user


@pytest.mark.parametrize(
    "rows,needle",
    [
        ([("blk:9.zz:title", "Nope", "नहीं")], "unknown key"),
        ([("blk:1.t1:title", "Introduction", "परिचय <b>")], "contains '<'"),
        ([("blk:1.t1:title", "Introduction", "परिचय {name}")], "placeholders"),
        (
            [("blk:1.t1:title", "Introduction", "परिचय"), ("blk:1.t1:title", "Introduction", "x")],
            "twice",
        ),
    ],
)
def test_import_refusals(unit, admin_user, rows, needle):
    with pytest.raises(xlsx.SheetRejected) as exc:
        xlsx.import_module(1, sheet(rows), admin_user)
    assert any(needle in e for e in exc.value.errors)
    assert not Translation.objects.exists()  # all or nothing


def test_import_refuses_blank_over_existing(unit, admin_user):
    row("blk:1.t1:title", "Introduction", "परिचय")
    with pytest.raises(xlsx.SheetRejected) as exc:
        xlsx.import_module(1, sheet([("blk:1.t1:title", "Introduction", "")]), admin_user)
    assert "blank, but a translation exists" in exc.value.errors[0]


def test_import_markers_must_match():
    assert xlsx.line_errors("Tap [[!the link]] now", "अभी टैप करें") != []
    assert xlsx.line_errors("Tap [[!the link]] now", "[[!the link]] अभी टैप करें") == []


def test_import_from_older_english_is_stale(unit, admin_user):
    result = xlsx.import_module(1, sheet([("blk:1.t1:title", "Intro (old)", "परिचय")]), admin_user)
    assert result.stale == 1
    assert t("blk:1.t1:title", "Introduction", "hi", allow_draft=True) == "Introduction"


def test_export_cells_are_never_formulas(unit, admin_user):
    row("blk:1.t1:title", "Introduction", '=HYPERLINK("x")')
    ws = load_workbook(BytesIO(xlsx.export_module(1))).active
    cells = [c for r in ws.iter_rows() for c in r if c.value and str(c.value).startswith("=")]
    assert cells and all(c.data_type == "s" for c in cells)


# --- admin and Rosetta access ----------------------------------------------------------------------


def test_sheets_page_and_rosetta_need_staff(client, unit, make_user, admin_user):
    learner = make_user()
    client.force_login(learner)
    assert client.get(reverse("admin:translations_sheets")).status_code in (302, 403)
    assert not rules.can_use_rosetta(learner)
    assert rules.can_use_rosetta(admin_user)


# --- draft importer ---------------------------------------------------------------------------------


def test_draft_import_matches_by_english_and_never_overwrites(unit, tmp_path):
    from apps.translations import drafts

    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "module-1.csv").write_text(
        '"id","English","Hindi","Hindi status","Marathi","Marathi status","Gujarati","Gujarati status"\n'
        '"m1.t0.0","What  is it?","यह क्या है?","draft - needs review","हे काय आहे?","draft - needs review","આ શું છે?","draft - needs review"\n'
        '"m1.t9.9","Not in the course","कुछ नहीं","draft - needs review","","","",""\n',
        encoding="utf-8",
    )
    # the team's framework-labels file: English under "id", each language one column left
    (sheets / "_framework-labels-verify.csv").write_text(
        '"id","English","Hindi","Hindi status","Marathi","Marathi status","Gujarati","Gujarati status"\n'
        '"Introduction","परिचय","ओळख","draft - needs review","પરિચય","draft - needs review","","to translate"\n',
        encoding="utf-8",
    )
    entries = drafts.read_sheets(sheets)
    framework = next(e for e in entries if e.where.startswith("_framework"))
    assert framework.english == "Introduction"
    assert framework.texts == {"hi": "परिचय", "mr": "ओळख", "gu": "પરિચય"}
    row("blk:1.t1:title", "Introduction", "पहले से", lang="hi")  # existing: left alone
    result = drafts.plan(entries)
    planned = {(k, c): t for k, c, t, _e, _o in result.rows}
    assert planned[("blk:1.t1:0:text", "hi")] == "यह क्या है?"  # matched despite spacing
    assert planned[("blk:1.t1:title", "mr")] == "ओळख"
    assert ("blk:1.t1:title", "hi") not in planned
    assert result.skipped_existing == 1
    assert [e.english for e in result.unmatched] == ["Not in the course"]
    drafts.apply(result)
    line = Translation.objects.get(key="blk:1.t1:0:text", language="hi")
    assert line.status == TranslationStatus.DRAFT and line.source_text == "What is it?"
    assert Translation.objects.get(key="blk:1.t1:title", language="hi").text == "पहले से"


def test_draft_import_refuses_the_wrong_script(unit):
    from apps.translations import drafts

    entry = drafts.Entry("Introduction", {"gu": "परिचय", "hi": "પરિચય"}, "sheet", "x")
    result = drafts.plan([entry])
    assert not result.rows
    assert len(result.refused) == 2
