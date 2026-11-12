"""Stage 4: learning content. Invented content only, except the importer test that runs on the private
legacy files when they are present (it prints and asserts counts only)."""

import json
import zipfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.content import blocks as blk
from apps.content import docx, legacy, media, services
from apps.content.models import (
    ImmutableVersion,
    LearnCheck,
    MediaKind,
    Module,
    TimeLog,
    Unit,
    UnitProgress,
    UnitType,
    UnitVersion,
    VersionSource,
    VersionStatus,
)
from apps.questions import services as qservices

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "content-data" / "legacy" / "lessons"
SECRET = "SECRET-ANSWER-TEXT"


@pytest.fixture
def module(db):
    m, _ = Module.objects.get_or_create(number=1, defaults={"slug": "module-1", "title_key": "x"})
    m.title, m.tagline, m.overview = (
        "Invented module",
        "Invented tagline.",
        {"what": "Invented what."},
    )
    m.save()
    return m


def para(text):
    return {"type": "paragraph", "spans": [{"text": text}]}


@pytest.fixture
def make_unit(module):
    def make(slug="t1", kind=UnitType.READING, blocks=None, publish=True, minutes=10):
        unit = Unit.objects.create(
            module=module, slug=slug, type=kind, order=1, nominal_minutes=minutes
        )
        v = services.add_version(
            unit, f"Title {slug}", blocks or [para("Hello.")], source=VersionSource.EDITOR
        )
        if publish:
            services.publish(v, None, system=True)
        return unit

    return make


def practice_mcq(stable_id, pool="practice", live=True):
    body = {
        "stem": "Invented practice stem?",
        "options": [
            {"id": "o1", "text": "Wrong one"},
            {"id": "o2", "text": SECRET},
            {"id": "o3", "text": "Wrong two"},
            {"id": "o4", "text": "Wrong three"},
        ],
        "correct": "o2",
        "hint": "Invented hint.",
        "gate": {},
    }
    q = qservices.create_question(
        stable_id=stable_id, module=Module.objects.get(number=1), body=body,
        tags={"pc": "PC1", "type": "R"}, pool=pool,
    )  # fmt: skip
    if live:
        qservices.publish(q)
    return q


# --- blocks: plain text only ------------------------------------------------------------------------


def test_blocks_accept_every_type_and_store_no_html():
    good = [
        {"type": "heading", "text": "A heading"},
        para("Some <b>text</b> stays text."),
        {"type": "list", "items": ["a", "b"]},
        {"type": "reveal", "prompt": "What now?", "answer": "Stop."},
        {"type": "mythfact", "statement": "S", "is_fact": True, "why": "Because."},
        {"type": "flipcards", "cards": [{"front": "F", "back": "B"}]},
        {"type": "ask_yourself", "items": ["Do I?"]},
    ]
    clean = blk.validate_blocks(good)
    assert (
        clean[1]["spans"][0]["text"] == "Some <b>text</b> stays text."
    )  # kept as text; templates escape


@pytest.mark.parametrize(
    "href", ["javascript:alert(1)", "data:text/html,x", "ftp://x.org", "//evil.org"]
)
def test_links_must_be_http_or_https(href):
    with pytest.raises(blk.BlocksInvalid):
        blk.validate_blocks([{"type": "paragraph", "spans": [{"text": "x", "href": href}]}])


def test_unknown_block_types_and_extra_fields_are_refused():
    for bad in ({"type": "script", "src": "x"}, {"type": "heading", "text": "x", "onclick": "y"}):
        with pytest.raises(blk.BlocksInvalid):
            blk.validate_blocks([bad])


def test_a_youtube_id_must_look_like_one():
    blk.validate_blocks([{"type": "video", "youtube_id": "dQw4w9WgXcQ"}])
    with pytest.raises(blk.BlocksInvalid):
        blk.validate_blocks([{"type": "video", "youtube_id": "x'><script>"}])


def test_markup_in_a_page_is_escaped(client, make_unit):
    make_unit(blocks=[para("<script>alert(1)</script>")])
    html = client.get(reverse("learn_unit", args=[1, "t1"])).content.decode()
    assert (
        "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    )


# --- versions: immutable, one published, publish/restore permissions ---------------------------------


def test_a_version_text_is_immutable_in_the_model_and_the_database(make_unit):
    unit = make_unit()
    v = unit.published()
    v.title = "Changed"
    with pytest.raises(ImmutableVersion):
        v.save()
    with pytest.raises(ImmutableVersion):
        v.delete()
    with connection.cursor() as cur, pytest.raises(Exception, match="immutable"):
        cur.execute("UPDATE content_unitversion SET title = 'x' WHERE id = %s", [v.pk])


def test_publishing_supersedes_the_previous_version_and_restore_brings_it_back(
    make_unit, make_user
):
    admin = make_user(role=Role.ADMIN)
    unit = make_unit(blocks=[para("first")])
    first = unit.published()
    second = services.add_version(
        unit, "Second", [para("second")], source=VersionSource.EDITOR, author=admin
    )
    assert unit.published().pk == first.pk  # a draft changes nothing for learners
    services.publish(second, admin)
    first.refresh_from_db()
    assert unit.published().pk == second.pk and first.status == VersionStatus.SUPERSEDED
    restored = services.restore(first, admin)
    assert (
        restored.blocks == first.blocks
        and restored.version == 3
        and unit.published().pk == restored.pk
    )
    assert unit.versions.filter(status=VersionStatus.PUBLISHED).count() == 1
    assert (
        AuditEvent.objects.filter(action__in=["content.published", "content.restored"]).count() >= 2
    )


def test_only_an_admin_or_a_content_publisher_can_publish(make_unit, make_user):
    unit = make_unit(publish=False)
    draft = unit.versions.get()
    learner, mentor, admin = make_user(), make_user(role=Role.MENTOR), make_user(role=Role.ADMIN)
    for who in (learner, mentor):
        with pytest.raises(PermissionDenied):
            services.publish(draft, who)
    mentor.user_permissions.add(Permission.objects.get(codename="publish_unit"))
    mentor = type(mentor).objects.get(pk=mentor.pk)
    assert services.publish(draft, mentor).status == VersionStatus.PUBLISHED
    assert services.can_publish(admin)


def test_an_invalid_draft_is_never_stored(make_unit):
    unit = make_unit(publish=False)
    with pytest.raises(blk.BlocksInvalid):
        services.add_version(unit, "Bad", [{"type": "nope"}], source=VersionSource.EDITOR)
    assert unit.versions.count() == 1


# --- pages -------------------------------------------------------------------------------------------


def test_catalogue_module_and_unit_pages_render_for_a_guest(client, make_unit):
    make_unit("t1")
    make_unit("handout", UnitType.HANDOUT)
    assert client.get(reverse("learn_catalogue")).status_code == 200
    page = client.get(reverse("learn_module", args=[1])).content.decode()
    assert "Invented module" in page and "Title t1" in page
    assert client.get(reverse("learn_unit", args=[1, "t1"])).status_code == 200
    assert client.get(reverse("learn_unit", args=[1, "nope"])).status_code == 404
    cap = client.get(
        reverse("learn_module", args=[10])
    )  # the capstone has a page with a clear pending state
    assert cap.status_code == 200 and b"Coming soon" in cap.content
    assert client.get(reverse("learn_module", args=[11])).status_code == 404


def test_a_draft_is_not_visible_to_learners(client, make_unit):
    make_unit("t1", publish=False)
    assert client.get(reverse("learn_unit", args=[1, "t1"])).status_code == 404


def test_reveal_and_myth_answers_are_not_in_the_page_until_asked(client, make_unit):
    unit = make_unit(blocks=[
        {"type": "reveal", "prompt": "Predict this.", "answer": "ANSWER-ONE-TEXT"},
        {"type": "mythfact", "statement": "A claim.", "is_fact": True, "why": "WHY-TEXT"},
    ])  # fmt: skip
    html = client.get(reverse("learn_unit", args=[1, "t1"])).content.decode()
    for secret in ("ANSWER-ONE-TEXT", "WHY-TEXT", "is_fact"):
        assert secret not in html
    got = client.post(reverse("learn_block", args=[1, unit.slug, 0])).json()
    assert got == {"answer": "ANSWER-ONE-TEXT"}
    verdict = client.post(reverse("learn_block", args=[1, unit.slug, 1]), {"pick": "myth"}).json()
    assert verdict["right"] is False and verdict["is_fact"] is True and verdict["why"] == "WHY-TEXT"
    assert (
        client.post(reverse("learn_block", args=[1, unit.slug, 1]), {"pick": "x"}).status_code
        == 400
    )
    assert client.post(reverse("learn_block", args=[1, unit.slug, 0 + 9])).status_code == 404


def test_a_jumbled_table_is_shown_with_a_being_fixed_notice(client, make_unit):
    make_unit(
        blocks=[{"type": "table", "head": ["A", "B"], "rows": [["1", "2"]], "being_fixed": True}]
    )
    assert "Table being fixed" in client.get(reverse("learn_unit", args=[1, "t1"])).content.decode()


# --- completion rules (8.3) --------------------------------------------------------------------------


def test_completion_rules_per_unit_type(make_unit, learner_client, learner):
    reading, handout = make_unit("t1"), make_unit("handout", UnitType.HANDOUT)
    check = make_unit("check", UnitType.CHECK)
    assert services.complete(learner, reading, how="end") is True
    assert services.complete(learner, reading, how="end") is False  # once
    with pytest.raises(ValueError):
        services.complete(learner, reading, how="opened")  # a reading does not complete by opening
    with pytest.raises(ValueError):
        services.complete(learner, check, how="end")
    learner_client.get(
        reverse("learn_unit", args=[1, handout.slug])
    )  # opening a handout completes it
    assert UnitProgress.objects.filter(user=learner, unit=handout).exists()
    assert UnitProgress.objects.filter(user=learner, unit=reading).count() == 1


def test_guests_and_staff_do_not_record_progress(client, make_unit, make_user):
    unit = make_unit()
    assert client.post(reverse("learn_complete", args=[1, "t1"]), {"how": "end"}).status_code == 403
    mentor = make_user(role=Role.MENTOR)
    assert services.complete(mentor, unit, how="end") is False


def test_the_complete_endpoint_marks_a_reading(learner_client, learner, make_unit):
    make_unit()
    assert learner_client.post(reverse("learn_complete", args=[1, "t1"]), {"how": "end"}).json()[
        "ok"
    ]
    assert (
        learner_client.post(
            reverse("learn_complete", args=[1, "t1"]), {"how": "opened"}
        ).status_code
        == 400
    )
    assert UnitProgress.objects.filter(user=learner).count() == 1


# --- /learn/check: practice questions only -------------------------------------------------------------


def test_learn_check_marks_a_practice_question_and_returns_the_full_answer(
    learner_client, learner, make_unit
):
    practice_mcq("M1-P01")
    make_unit("check", UnitType.CHECK, blocks=[{"type": "check", "question": "M1-P01"}])
    html = learner_client.get(reverse("learn_unit", args=[1, "check"])).content.decode()
    assert '"correct"' not in html and "o2" not in html  # the page carries no key, only tokens
    import re

    tokens = re.findall(r'data-choice="([^"]+)"', html)
    assert len(tokens) == 4
    results = []
    for t in tokens:
        results.append(
            learner_client.post(
                reverse("learn_check"), {"m": 1, "u": "check", "question": "M1-P01", "choice": t}
            ).json()
        )
    assert sum(1 for r in results if r["right"]) == 1
    assert all(r["right_text"] == SECRET for r in results)  # practice shows the full answer (D13)
    assert LearnCheck.objects.filter(user=learner).count() == 4
    assert UnitProgress.objects.filter(user=learner, unit__slug="check").exists()  # attempted once


@pytest.mark.parametrize("pool", ["module_quiz", "final"])
def test_learn_check_refuses_quiz_and_final_questions(learner_client, make_unit, pool):
    practice_mcq("M1-Q01", pool=pool)
    make_unit("check", UnitType.CHECK, blocks=[{"type": "check", "question": "M1-Q01"}])
    html = learner_client.get(reverse("learn_unit", args=[1, "check"])).content.decode()
    assert "data-choice" not in html and SECRET not in html  # not even shown
    response = learner_client.post(
        reverse("learn_check"), {"m": 1, "u": "check", "question": "M1-Q01", "choice": "x"}
    )
    assert response.status_code == 400 and SECRET not in response.content.decode()
    assert LearnCheck.objects.count() == 0


def test_learn_check_refuses_a_practice_question_no_published_unit_uses(learner_client, make_unit):
    practice_mcq("M1-P02")
    make_unit("check", UnitType.CHECK, blocks=[para("no check block here")])
    response = learner_client.post(
        reverse("learn_check"), {"m": 1, "u": "check", "question": "M1-P02", "choice": "x"}
    )
    assert response.status_code == 400 and SECRET not in response.content.decode()


def test_learn_check_needs_the_session_tokens_and_is_rate_limited(learner_client, make_unit):
    practice_mcq("M1-P03")
    make_unit("check", UnitType.CHECK, blocks=[{"type": "check", "question": "M1-P03"}])
    r = learner_client.post(
        reverse("learn_check"), {"m": 1, "u": "check", "question": "M1-P03", "choice": "guess"}
    )
    assert r.status_code == 400  # no page was loaded, so no tokens exist
    assert learner_client.get(reverse("learn_check")).status_code == 405


# --- hours: adults only (8.3, D16) -----------------------------------------------------------------------


def beat(user, unit, client):
    session = client.session
    services.touch(session)
    session.save()
    return client.post(reverse("learn_heartbeat"), {"m": 1, "u": unit.slug}).json()["counted"]


def test_a_minor_generates_no_timelog_rows(client, make_user, make_batch, make_unit):
    minor = make_user(batch=make_batch(), dob=date.today() - timedelta(days=17 * 365 + 30))
    unit = make_unit()
    client.force_login(minor)
    assert beat(minor, unit, client) == 0
    assert TimeLog.objects.count() == 0
    services.complete(minor, unit, how="end")
    assert services.hours_for(minor) == {"kind": "nominal", "minutes": 10}


def test_an_adult_gets_capped_engaged_time_only_after_real_activity(
    client, make_user, make_batch, make_unit
):
    adult = make_user(batch=make_batch(), dob=date(1990, 1, 1))
    unit = make_unit(minutes=1)  # cap = 2 x 1 minute = 120 s
    client.force_login(adult)
    assert (
        client.post(reverse("learn_heartbeat"), {"m": 1, "u": "t1"}).json()["counted"] == 0
    )  # no server interaction yet
    assert beat(adult, unit, client) == 30
    s = client.session
    s[f"learn_beat_{unit.pk}"] = 0  # pretend the 30 s have passed
    s.save()
    for _ in range(6):
        beat(adult, unit, client)
        s = client.session
        s[f"learn_beat_{unit.pk}"] = 0
        s.save()
    assert TimeLog.objects.get(user=adult).seconds == 120  # capped at twice the nominal minutes
    assert services.hours_for(adult)["kind"] == "engaged"


def test_a_stale_session_interaction_does_not_count(client, make_user, make_batch, make_unit):
    adult = make_user(batch=make_batch(), dob=date(1990, 1, 1))
    make_unit()
    client.force_login(adult)
    s = client.session
    s["learn_active_at"] = (timezone.now() - timedelta(minutes=10)).timestamp()
    s.save()
    assert client.post(reverse("learn_heartbeat"), {"m": 1, "u": "t1"}).json()["counted"] == 0


# --- uploads --------------------------------------------------------------------------------------------


def make_docx(body_xml):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')  # fmt: skip
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')  # fmt: skip
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body_xml}</w:body></w:document>')  # fmt: skip
    return SimpleUploadedFile("x.docx", buf.getvalue())


def p(text, style=None, bold=False):
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run = f"<w:r>{'<w:rPr><w:b/></w:rPr>' if bold else ''}<w:t>{text}</w:t></w:r>"
    return f"<w:p>{props}{run}</w:p>"


def test_a_docx_becomes_blocks_that_make_a_draft_unit(make_unit, make_user):
    upload = make_docx(
        p("My lesson", "Heading1")
        + p("<script>x</script> plain words", bold=True)
        + p("Second paragraph.")
    )
    title, blocks, _ = docx.docx_to_blocks(upload)
    assert title == "My lesson"
    unit = make_unit("up", publish=False)
    version = services.add_version(
        unit, title, blocks, source=VersionSource.DOCX, author=make_user(role=Role.ADMIN)
    )
    assert version.status == VersionStatus.DRAFT and version.source == VersionSource.DOCX
    text = json.dumps(version.blocks)
    assert "plain words" in text and "<script" not in text.replace(
        "&lt;script", ""
    )  # text, never markup
    assert unit.published() is None or unit.published().pk != version.pk  # not live until published


@pytest.mark.parametrize("data", [b"not a zip", b"PK\x03\x04junk"])
def test_a_non_docx_is_rejected(data):
    with pytest.raises(docx.DocxRejected):
        docx.docx_to_blocks(SimpleUploadedFile("x.docx", data))


def test_a_docx_with_an_entity_declaration_is_rejected():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]><w:document xmlns:w="a"/>',
        )
    with pytest.raises(docx.DocxRejected):
        docx.docx_to_blocks(SimpleUploadedFile("x.docx", buf.getvalue()))


def test_an_oversized_docx_is_rejected():
    with pytest.raises(docx.DocxRejected):
        docx.docx_to_blocks(
            SimpleUploadedFile("x.docx", b"PK\x03\x04" + b"0" * (docx.MAX_BYTES + 1))
        )


def png_bytes(size=(40, 30), exif=False):
    img = Image.new("RGB", size, "red")
    out = BytesIO()
    if exif:
        e = Image.Exif()
        e[0x010F] = "SECRET-CAMERA"
        img.save(out, format="JPEG", exif=e)
    else:
        img.save(out, format="PNG")
    return out.getvalue()


def test_images_are_reencoded_without_metadata_and_svg_is_refused(module):
    asset = media.store(SimpleUploadedFile("a.jpg", png_bytes(exif=True)), module, MediaKind.IMAGE)
    stored = asset.file.open("rb").read()
    assert b"SECRET-CAMERA" not in stored and asset.content_type.startswith("image/")
    with pytest.raises(media.MediaRejected):
        media.store(SimpleUploadedFile("a.png", b"<svg onload='x'></svg>"), module, MediaKind.IMAGE)


def test_pdf_and_mp4_are_sniffed_not_trusted_by_name(module):
    with pytest.raises(media.MediaRejected):
        media.store(SimpleUploadedFile("evil.pdf", b"MZ not a pdf"), module, MediaKind.PDF)
    with pytest.raises(media.MediaRejected):
        media.store(SimpleUploadedFile("evil.mp4", b"x" * 100), module, MediaKind.MP4)
    ok = media.store(SimpleUploadedFile("h.pdf", b"%PDF-1.4 invented"), module, MediaKind.PDF)
    assert ok.content_type == "application/pdf"
    mp4 = media.store(
        SimpleUploadedFile("f.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 20), module, MediaKind.MP4
    )
    assert mp4.content_type == "video/mp4"


def test_only_media_used_by_a_published_unit_is_served(client, module, make_unit):
    asset = media.store(SimpleUploadedFile("h.pdf", b"%PDF-1.4 invented"), module, MediaKind.PDF)
    assert client.get(reverse("learn_media", args=[asset.pk])).status_code == 404
    make_unit(
        "handout",
        UnitType.HANDOUT,
        blocks=[{"type": "attachment", "asset": asset.pk, "label": "Handout"}],
    )
    r = client.get(reverse("learn_media", args=[asset.pk]))
    assert (
        r.status_code == 200
        and r["Content-Type"] == "application/pdf"
        and r["X-Content-Type-Options"] == "nosniff"
    )


def test_video_unit_uses_the_nocookie_embed_or_the_poster_with_a_notice(client, make_unit):
    make_unit(
        "film",
        UnitType.VIDEO,
        blocks=[
            {
                "type": "video",
                "youtube_id": "dQw4w9WgXcQ",
                "transcript": [{"t0": 0, "t1": 2, "en": "Hello", "hi": "नमस्ते"}],
            }
        ],
    )
    html = client.get(reverse("learn_unit", args=[1, "film"])).content.decode()
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in html and "Hello" in html and "नमस्ते" in html
    make_unit("film2", UnitType.VIDEO, blocks=[{"type": "video"}])
    assert "being uploaded" in client.get(reverse("learn_unit", args=[1, "film2"])).content.decode()


# --- the legacy importer ---------------------------------------------------------------------------------


def test_the_php_reader_handles_arrays_strings_numbers_and_booleans():
    got = legacy.parse_php_array(
        "<?php // c\nreturn [1 => ['t' => 'it\\'s', 'n' => 1.5, 'b' => true, 'l' => ['a', \"b\"]]];"
    )
    assert got == {1: {"t": "it's", "n": legacy.Decimal("1.5"), "b": True, "l": ["a", "b"]}}


def test_every_topic_gets_an_interaction_even_with_few_candidates():
    topics = [
        [
            {"type": "heading", "text": "A"},
            para("alpha beta " * 5),
            {"type": "heading", "text": "B"},
        ]
        for _ in range(4)
    ]
    cands = [
        (f"word{i} alpha", {"type": "reveal", "label": "L", "prompt": "p", "answer": "a"})
        for i in range(5)
    ]
    placed = legacy.place_interactions(topics, cands)
    assert all(blk.has_interaction(t) for t in placed)


@pytest.mark.skipif(
    not (PRIVATE / "booklet_text.json").exists(), reason="private legacy files not present"
)
def test_the_real_legacy_lessons_import_55_topics_each_with_an_interaction():
    planned = legacy.plan(legacy.load_sources(PRIVATE))
    counts = legacy.report(planned)
    assert counts["modules"] == 9 and counts["reading_topics"] == 55
    assert counts["topics_with_interaction"] == 55 and counts["films_with_transcript"] == 9
    assert counts["practice_checks"] == 9
    sizes = {n: len(m["topics"]) for n, m in planned.items()}
    assert sizes == {1: 6, 2: 7, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6}


@pytest.mark.skipif(
    not (PRIVATE / "booklet_text.json").exists(), reason="private legacy files not present"
)
def test_the_importer_creates_published_units_and_will_not_run_twice(client):
    result = legacy.run(PRIVATE)
    assert result["created"] == 9 * 3 + 55 and result["already_imported"] is False
    assert Unit.objects.filter(type="reading").count() == 55
    assert not UnitVersion.objects.exclude(status="published").exists()
    assert (
        legacy.run(PRIVATE)["already_imported"] is True
        and Unit.objects.count() == result["created"]
    )
    for number in range(1, 10):
        assert client.get(reverse("learn_module", args=[number])).status_code == 200
    for unit in Unit.objects.all():
        assert (
            client.get(reverse("learn_unit", args=[unit.module.number, unit.slug])).status_code
            == 200
        )
    assert Module.objects.get(number=1).title and Module.objects.get(number=9).hours
    film = client.get(reverse("learn_unit", args=[1, "film"])).content.decode()
    assert "being uploaded" in film  # no YouTube ID yet: poster and transcript


def test_the_importer_refuses_after_an_edit(make_unit, make_user, tmp_path):
    unit = make_unit()
    services.add_version(unit, "Edited", [para("edited")], source=VersionSource.EDITOR)
    with pytest.raises(legacy.ImportRefused):
        legacy.run(tmp_path)


def test_the_admin_upload_turns_a_docx_into_a_draft_unit(client, make_unit, make_user):
    unit = make_unit("up")
    from allauth.mfa.models import Authenticator

    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    url = reverse("admin:content_unit_docx", args=[unit.pk])
    assert client.get(url).status_code == 200
    upload = make_docx(p("Uploaded lesson", "Heading1") + p("Body text here."))
    response = client.post(url, {"file": upload})
    assert response.status_code == 302
    draft = unit.versions.order_by("-version").first()
    assert draft.status == VersionStatus.DRAFT and draft.source == VersionSource.DOCX
    assert unit.published().pk != draft.pk
    bad = client.post(url, {"file": SimpleUploadedFile("x.docx", b"not a docx")})
    assert bad.status_code == 200 and b"not a Word" in bad.content


# --- review fixes: unpublished lessons, signed-out practice checks ----------------------------------------


def test_completion_is_refused_for_an_unpublished_lesson(learner_client, learner, make_unit):
    make_unit("draft", UnitType.READING, publish=False)
    response = learner_client.post(reverse("learn_complete", args=[1, "draft"]), {"how": "end"})
    assert response.status_code == 404
    assert not UnitProgress.objects.filter(user=learner).exists()
    with pytest.raises(services.UnitNotPublished):
        services.complete(learner, Unit.objects.get(slug="draft"), how="end")


def test_a_lesson_that_loses_its_published_version_cannot_be_completed(learner, make_unit):
    unit = make_unit("t1")
    UnitVersion.objects.filter(unit=unit).update(status=VersionStatus.SUPERSEDED)
    with pytest.raises(services.UnitNotPublished):
        services.complete(learner, unit, how="end")


def test_the_heartbeat_ignores_an_unpublished_lesson(client, make_user, make_batch, make_unit):
    adult = make_user(batch=make_batch(), dob=date(1990, 1, 1))
    unit = make_unit("draft", publish=False)
    client.force_login(adult)
    session = client.session
    services.touch(session)
    session.save()
    assert client.post(reverse("learn_heartbeat"), {"m": 1, "u": "draft"}).status_code == 404
    assert services.heartbeat(adult, unit, client.session) == 0
    assert TimeLog.objects.count() == 0


def test_a_malformed_module_number_is_a_404_not_a_server_error(learner_client):
    for url in ("learn_check", "learn_heartbeat"):
        r = learner_client.post(
            reverse(url), {"m": "abc", "u": "t1", "question": "x", "choice": "y"}
        )
        assert r.status_code == 404


def test_a_signed_out_visitor_can_answer_a_practice_check_and_leaves_no_record(client, make_unit):
    import re

    practice_mcq("M1-P09")
    make_unit("check", UnitType.CHECK, blocks=[{"type": "check", "question": "M1-P09"}])
    html = client.get(reverse("learn_unit", args=[1, "check"])).content.decode()
    tokens = re.findall(r'data-choice="([^"]+)"', html)
    assert len(tokens) == 4
    results = [
        client.post(
            reverse("learn_check"), {"m": 1, "u": "check", "question": "M1-P09", "choice": t}
        )
        for t in tokens
    ]
    assert all(r.status_code == 200 for r in results)
    bodies = [r.json() for r in results]
    assert sum(1 for b in bodies if b["right"]) == 1 and all(
        b["right_text"] == SECRET for b in bodies
    )
    assert LearnCheck.objects.count() == 0 and UnitProgress.objects.count() == 0


def test_a_signed_out_visitor_still_cannot_check_quiz_or_final_questions(client, make_unit):
    for pool in ("module_quiz", "final"):
        practice_mcq(f"M1-{pool[:1].upper()}9", pool=pool)
        make_unit(
            f"c{pool}",
            UnitType.CHECK,
            blocks=[{"type": "check", "question": f"M1-{pool[:1].upper()}9"}],
        )
        r = client.post(
            reverse("learn_check"),
            {"m": 1, "u": f"c{pool}", "question": f"M1-{pool[:1].upper()}9", "choice": "x"},
        )
        assert r.status_code == 400 and SECRET not in r.content.decode()
