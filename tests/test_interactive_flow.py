"""Stage 3: interactive attempts end to end, journeys 8 and 10, images, the importer, the bundle."""

import json
import re
from decimal import Decimal
from html import unescape
from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse
from PIL import Image

from apps.assessments import rules, services
from apps.assessments.models import AssessmentPart, Attempt
from apps.audit.models import AuditEvent
from apps.content.models import Module
from apps.questions import images, legacy_interactive, schemas
from apps.questions import services as qservices
from apps.questions.models import Question, QuestionImage

from .conftest import _INVENTED, invented_body
from .test_interactive_formats import ALLOWED, FORBIDDEN_NAMES, NESTED, keys_of

pytestmark = pytest.mark.django_db
HX = {"HTTP_HX_REQUEST": "true"}
ROOT = Path(__file__).resolve().parent.parent


def post_response(client, attempt, position, response, flag=False):
    data = {"position": position, "flag_present": "1", "response": json.dumps(response)}
    if flag:
        data["flag"] = "on"
    return client.post(reverse("attempt_answer", args=[attempt.pk]), data, **HX)


def tokens(item, table):
    from apps.questions import formats

    return formats.by_index(item.option_map, table)


def logical(item, spec):
    from apps.questions import formats  # noqa: F401

    body = item.question_version.body
    return legacy_interactive.logical_response(item.format, body, item.option_map, spec)


def items_by_id(attempt):
    return {
        i.question_version.question.stable_id: i
        for i in attempt.items.select_related("question_version__question")
    }


def case_of(item):
    """Which invented case this item came from (by its title)."""
    title = item.question_version.body["title"]
    return next(k for k, v in _INVENTED.items() if v["title"] == title)


def start(client, part):
    client.post(reverse("assess_start", args=[part.pk]))
    return Attempt.objects.get(part=part, status="in_progress")


def attempt_data_attrs(html):
    """Every data-q payload in a page, parsed from the attribute (what the browser's engine reads)."""
    return [json.loads(unescape(m)) for m in re.findall(r'data-q="([^"]*)"', html)]


def spec_for(case, item):
    """A fully-right logical answer for an invented case, in legacy positions."""
    q = _INVENTED[case]
    t = q["type"]
    if t == "mc":
        return {"choice": q["a"]}
    if t == "cards":
        return {"answers": {i: it["a"] for i, it in enumerate(q["items"])}}
    if t == "spot":
        taps = re.findall(r"\[\[(!?)([\s\S]+?)\]\]", q["text"])
        return {"picked": [i for i, (bang, _) in enumerate(taps) if bang]}
    if t == "hotspot":
        return {"picked": [i for i, s in enumerate(q["spots"].values()) if s["ok"]]}
    if t == "sort":
        return {"placed": {i: it["b"] for i, it in enumerate(q["items"])}}
    if t == "match":
        return {"links": {i: i for i in range(len(q["pairs"]))}}
    if t == "order":
        return {"sequence": list(range(len(q["items"])))}
    if t == "pick":
        return {"picked": [i for i, it in enumerate(q["items"]) if it["ok"]]}
    if t == "build":
        return {
            "filled": {
                i: (s["a"][0] if isinstance(s["a"], list) else s["a"])
                for i, s in enumerate(q["slots"])
            }
        }
    if t == "settings":
        return {
            "values": {
                i: (
                    int(bool(r["want"]))
                    if r.get("kind") == "switch"
                    else (r["want"][0] if isinstance(r["want"], list) else r["want"])
                )
                for i, r in enumerate(q["rows"])
            }
        }
    if t == "dial":
        return {"values": {i: r["answer"] for i, r in enumerate(q["rows"])}}
    if t == "chat":
        return {
            "replies": [
                next(j for j, r in enumerate(s["replies"]) if r["s"] == 2) for s in q["steps"]
            ]
        }
    if t == "crossword":
        letters = {}
        for word in q["words"]:
            for offset, letter in enumerate(word["a"]):
                row = word["r"] + (offset if word["dir"] == "D" else 0)
                col = word["c"] + (offset if word["dir"] == "A" else 0)
                letters[f"{row},{col}"] = letter
        return {"letters": letters}
    raise AssertionError(t)


# --- a whole interactive attempt ---------------------------------------------------------------------------------


def test_answering_every_format_through_the_real_endpoint_scores_100(
    learner_client, interactive_part
):
    part = interactive_part()
    attempt = start(learner_client, part)
    assert attempt.items.count() == 15 and {i.format for i in attempt.items.all()} >= {
        "mc",
        "cards",
        "spot",
        "hotspot",
        "sort",
        "match",
        "order",
        "pick",
        "build",
        "settings",
        "dial",
        "chat",
    }
    for item in attempt.items.select_related("question_version"):
        case = case_of(item)
        response = logical(item, spec_for(case, item))
        assert post_response(learner_client, attempt, item.position, response).status_code == 200, (
            case
        )
    attempt.refresh_from_db()
    review = learner_client.get(reverse("attempt_review", args=[attempt.pk])).content.decode()
    assert "Every question is answered" in review
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    attempt.refresh_from_db()
    assert attempt.score == Decimal("100.0") and attempt.all_answered
    # the gate items were answered correctly, so nothing gated
    assert attempt.counted and not attempt.gate_breached


def test_a_blank_interactive_attempt_scores_only_what_is_right_by_default(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    attempt.refresh_from_db()
    assert attempt.score < Decimal("20") and not attempt.all_answered and attempt.counted


def test_the_saved_answer_comes_back_when_the_question_is_reopened(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    item = next(
        i for i in attempt.items.select_related("question_version") if case_of(i) == "inv-sort"
    )
    response = logical(item, {"placed": {0: 0, 1: 1}})
    post_response(learner_client, attempt, item.position, response)
    page = learner_client.get(
        reverse("attempt_question", args=[attempt.pk, item.position]), **HX
    ).content.decode()
    payload = attempt_data_attrs(page)[0]
    assert payload["response"] == {"placed": response["placed"]}
    data = learner_client.get(
        reverse("attempt_question_data", args=[attempt.pk, item.position])
    ).json()
    assert data["response"] == payload["response"] and data["format"] == "sort"


def test_a_partial_answer_is_saved_but_the_question_is_not_yet_answered(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    item = next(
        i for i in attempt.items.select_related("question_version") if case_of(i) == "inv-order"
    )
    post_response(learner_client, attempt, item.position, logical(item, {"sequence": [0, 1]}))
    item.refresh_from_db()
    assert not item.answered and item.response["sequence"]
    html = learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode()
    assert "attempt-head" in html


def test_marking_for_review_keeps_the_interactive_answer(learner_client, interactive_part):
    attempt = start(learner_client, interactive_part())
    item = next(
        i for i in attempt.items.select_related("question_version") if case_of(i) == "inv-mc"
    )
    post_response(learner_client, attempt, item.position, logical(item, {"choice": 0}))
    response = learner_client.post(
        reverse("attempt_answer", args=[attempt.pk]),
        {"position": item.position, "flag_present": "1", "flag": "on"},
        **HX,
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.response["flag"] is True and "choice" in item.response


def test_bad_json_and_foreign_tokens_are_refused_and_nothing_is_saved(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    item = attempt.items.first()
    url = reverse("attempt_answer", args=[attempt.pk])
    base = {"position": item.position, "flag_present": "1"}
    for response in ("not json", "[1,2]", "x" * 30000):
        assert learner_client.post(url, {**base, "response": response}, **HX).status_code == 400
    assert (
        post_response(learner_client, attempt, item.position, {"choice": "forged"}).status_code
        == 400
    )
    item.refresh_from_db()
    assert not item.response


def test_interactive_answers_cannot_be_changed_after_submitting(learner_client, interactive_part):
    attempt = start(learner_client, interactive_part())
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    item = attempt.items.first()
    closed = post_response(learner_client, attempt, item.position, {"choice": "x"})
    assert closed.status_code == 409


# --- journey 8: an interactive attempt with a gate choice --------------------------------------------------------


def test_journey8_a_gate_choice_is_scored_but_not_counted_and_shows_the_hint(
    learner_client, learner, interactive_part
):
    part = interactive_part(["inv-cards", "inv-mc", "inv-order"])
    attempt = start(learner_client, part)
    for item in attempt.items.select_related("question_version"):
        case = case_of(item)
        if (
            case == "inv-cards"
        ):  # card two is a safety-gate card: answering it wrongly gates the attempt
            answers = {
                0: 0,
                1: 0,
                2: 1,
                3: 0,
            }  # item 1 should be Risky (1); Fine (0) is the gate mistake
            spec = {"answers": answers}
        else:
            spec = spec_for(case, item)
        post_response(learner_client, attempt, item.position, logical(item, spec))
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    attempt.refresh_from_db()
    assert attempt.gate_breached and not attempt.counted
    assert attempt.score > 0  # scored, and shown
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "This attempt doesn&#x27;t count" in html or "This attempt doesn't count" in html
    assert "would have put a citizen at risk" in html and "Safety gate" in html
    assert "Invented hint for inv-cards." in html  # the hint is shown (D13)
    assert "Invented: this would endanger a citizen." not in html  # the internal reason is not
    assert "Passed" not in html
    assert AuditEvent.objects.filter(action="attempt.submitted").get().data["gate_breached"] is True
    assert learner.attempts.filter(counted=True).count() == 0


def test_a_gated_attempt_does_not_count_towards_the_best_score(learner_client, interactive_part):
    part = interactive_part(["inv-cards", "inv-mc"])
    first = start(learner_client, part)
    for item in first.items.select_related("question_version"):
        spec = (
            {"answers": {0: 0, 1: 0, 2: 1, 3: 0}}
            if case_of(item) == "inv-cards"
            else spec_for(case_of(item), item)
        )
        post_response(learner_client, first, item.position, logical(item, spec))
    learner_client.post(reverse("attempt_submit", args=[first.pk]))
    intro = learner_client.get(reverse("assess_intro", args=[part.pk])).content.decode()
    assert (
        "doesn't count" in intro
        or "doesn&#x27;t count" in intro
        and "Your best score so far" not in intro
    )


# --- journey 10: any assessment page, inspected in DevTools -----------------------------------------------------------


def test_journey10_no_page_or_json_response_of_an_interactive_attempt_has_a_key(
    learner_client, interactive_part
):
    part = interactive_part()
    attempt = start(learner_client, part)
    hints = {i.question_version.body["hint"] for i in attempt.items.all()}
    pages = [learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode()]
    jsons = []
    for item in attempt.items.select_related("question_version"):
        url = reverse("attempt_question", args=[attempt.pk, item.position])
        pages.append(learner_client.get(url, **HX).content.decode())
        pages.append(learner_client.get(url).content.decode())
        jsons.append(
            learner_client.get(
                reverse("attempt_question_data", args=[attempt.pk, item.position])
            ).json()
        )
        pages.append(
            post_response(
                learner_client,
                attempt,
                item.position,
                logical(item, spec_for(case_of(item), item)),
                flag=True,
            ).content.decode()
        )
    pages.append(learner_client.get(reverse("attempt_review", args=[attempt.pk])).content.decode())
    for page in pages:
        for hint in hints:
            assert hint not in page, "a hint was sent before submitting"
        assert (
            "Invented: this" not in page
            and "gate_message" not in page
            and "content_hash" not in page
        )
        for payload in attempt_data_attrs(page):  # what the engine reads from the page
            assert set(payload) <= ALLOWED[payload["format"]]
            assert not (
                keys_of({k: v for k, v in payload.items() if k != "response"})
                & set(FORBIDDEN_NAMES)
            )
    for payload in jsons:  # the JSON endpoint
        assert set(payload) <= ALLOWED[payload["format"]]
        assert (
            keys_of({k: v for k, v in payload.items() if k != "response"})
            <= ALLOWED[payload["format"]] | NESTED
        )
        assert not (
            keys_of({k: v for k, v in payload.items() if k != "response"}) & set(FORBIDDEN_NAMES)
        )


def test_the_result_page_of_an_interactive_attempt_has_no_answer_data(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    for item in attempt.items.select_related("question_version")[:5]:
        post_response(
            learner_client, attempt, item.position, logical(item, spec_for(case_of(item), item))
        )
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "data-q=" not in html and "data-engine" not in html and 'name="choice"' not in html
    # per-question: titles, right / partly / not quite, and the hint. Never the right items.
    assert html.count("Invented hint for") == 15
    for forbidden in ("Invented gate", "Invented reason", "Invented description"):
        assert forbidden not in html
    for case in ("inv-pick-need", "inv-build", "inv-order", "inv-match"):
        for needle in (
            "Invented pick A",
            "Invented chip 0",
            "Invented first step",
            "Invented right one",
        ):
            assert needle not in html, (case, needle)


def test_interactive_pages_have_no_inline_script_or_style_and_load_the_bundle(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part())
    html = learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode()
    # The only inline <script> allowed is a JSON data block (the engine labels, json_script): the
    # browser never runs it, so the CSP stays script-src self.
    executable = r'<script(?![^>]*\bsrc=)(?![^>]*type="application/json")'
    assert not re.search(executable, html) and not re.search(r"\sstyle=", html)
    assert "js/engine.js" in html and "css/engine.css" in html and "data-engine" in html
    assert "noscript" in html  # a message for browsers without JavaScript


def test_content_text_is_escaped_in_the_page_attribute(
    learner_client, interactive_part, make_interactive, module1
):
    part = interactive_part(["inv-mc"])
    question = Question.objects.get(module=module1)
    qservices.add_version(
        question,
        {
            **question.current_version.body,
            "title": "<img src=x onerror=alert(1)>",
            "options": question.current_version.body["options"],
        },
    )
    attempt = start(learner_client, part)
    html = learner_client.get(
        reverse("attempt_question", args=[attempt.pk, 1]), **HX
    ).content.decode()
    assert "<img src=x" not in html and "&lt;img" in html


# --- the hotspot picture ---------------------------------------------------------------------------------------------------


def png(size=(40, 30), exif=False):
    image = Image.new("RGB", size, (200, 220, 240))
    buffer = BytesIO()
    if exif:
        info = Image.Exif()
        info[0x010E] = "SECRET DESCRIPTION"
        image.save(buffer, format="JPEG", exif=info)
    else:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def upload(data, name="a.png", content_type="image/png"):
    return SimpleUploadedFile(name, data, content_type)


def test_a_picture_is_re_encoded_without_metadata():
    record = images.store_image(upload(png(exif=True), "a.jpg", "image/jpeg"))
    stored = record.file.open("rb").read()
    assert b"SECRET DESCRIPTION" not in stored and record.format == "jpeg"
    assert not Image.open(BytesIO(stored)).getexif()


@pytest.mark.parametrize(
    "data",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"GIF89a" + b"\x00" * 50,
        b"not an image at all",
        b"\x89PNG\r\n\x1a\n" + b"junk",
    ],
)
def test_svg_html_and_broken_files_are_refused_as_pictures(data):
    with pytest.raises(images.ImageRejected):
        images.store_image(upload(data, "x.svg", "image/svg+xml"))
    assert not QuestionImage.objects.exists()


def test_big_pictures_are_refused(monkeypatch):
    with pytest.raises(images.ImageRejected):
        images.store_image(upload(b"\x00" * (images.MAX_BYTES + 10)))
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    with pytest.raises(images.ImageRejected):
        images.store_image(upload(png((50, 50))))


def test_the_same_picture_is_stored_once():
    first = images.store_image(upload(png()))
    assert images.store_image(upload(png())).pk == first.pk and QuestionImage.objects.count() == 1


def test_the_picture_is_served_only_to_the_learner_who_has_that_question(
    learner_client, interactive_part, make_user, make_batch, client
):
    attempt = start(learner_client, interactive_part(["inv-hotspot", "inv-mc"]))
    spot = next(
        i for i in attempt.items.select_related("question_version") if i.format == "hotspot"
    )
    url = reverse("attempt_image", args=[attempt.pk, spot.position])
    response = learner_client.get(url)
    assert response.status_code == 200 and response["Content-Type"] == "image/png"
    assert "private" in response["Cache-Control"]
    assert b"".join(response.streaming_content)[1:4] == b"PNG"
    mc = next(i for i in attempt.items.all() if i.format == "mc")
    assert (
        learner_client.get(reverse("attempt_image", args=[attempt.pk, mc.position])).status_code
        == 404
    )
    stranger = make_user(batch=make_batch())
    client.force_login(stranger)
    assert client.get(url).status_code == 404
    client.logout()
    assert client.get(url).status_code == 302


def test_the_page_points_the_hotspot_at_the_private_endpoint_not_at_content(
    learner_client, interactive_part
):
    attempt = start(learner_client, interactive_part(["inv-hotspot"]))
    html = learner_client.get(
        reverse("attempt_question", args=[attempt.pk, 1]), **HX
    ).content.decode()
    assert f'data-image-url="/attempt/{attempt.pk}/q/1/image/"' in html
    assert "<img" not in html  # the renderer draws the picture and the regions from numbers
    assert not re.search(r'<svg(?![^>]*class="icon)', html)  # (the only SVGs are our own icons)


# --- publishing and parts ---------------------------------------------------------------------------------------------------


def make_draft(module, case, **kw):
    fmt, body = invented_body(case, image_id=kw.pop("image_id", None))
    return qservices.create_question(
        stable_id=kw.pop("stable_id", "M1-D1"),
        module=module,
        fmt=fmt,
        body=body,
        tags={},
        pool=kw.pop("pool", "module_quiz"),
    )


def test_interactive_questions_publish_without_a_pc_tag(module1):
    question = make_draft(module1, "inv-sort")
    assert qservices.publish(question).status == "live"


def test_crosswords_outside_module_eight_are_practice_only(module1):
    question = make_draft(module1, "inv-crossword")
    with pytest.raises(qservices.PublishError, match="practice only"):
        qservices.publish(question)
    question.pool = "practice"
    question.save()
    assert qservices.publish(question).status == "live"


def test_module_eight_crossword_scores_in_its_graded_part(learner_client):
    module = Module.objects.get(number=8)
    question = make_draft(module, "inv-crossword", stable_id="M8-C01")
    qservices.publish(question)
    part = AssessmentPart.objects.create(
        module=module, name="Part B: interactive", family="interactive", marks=50, selection="all"
    )
    rules.publish_part(part)
    attempt = start(learner_client, part)
    item = attempt.items.get()
    result = post_response(
        learner_client, attempt, 1, logical(item, spec_for("inv-crossword", item))
    )
    assert result.status_code == 200
    completed = services.submit(attempt.pk, attempt.user_id)
    assert completed.score == Decimal("100.0")
    assert completed.counted and completed.all_answered
    assert part.marks == 50


def test_a_hotspot_needs_its_picture_before_it_goes_live(module1):
    question = make_draft(module1, "inv-hotspot")
    with pytest.raises(qservices.PublishError, match="picture"):
        qservices.publish(question)


def test_a_draft_without_a_hint_cannot_go_live_whatever_the_format(module1):
    fmt, body = invented_body("inv-order")
    body["hint"] = ""
    question = qservices.create_question(
        stable_id="M1-D9", module=module1, fmt=fmt, body=body, tags={}, pool="module_quiz"
    )
    with pytest.raises(qservices.PublishError, match="hint"):
        qservices.publish(question)


def test_an_interactive_part_needs_live_questions_and_never_includes_crosswords(
    module1, make_interactive
):
    part = AssessmentPart.objects.create(
        module=module1, name="B", family="interactive", marks=50, selection="all"
    )
    assert rules.validate_part(part) == ["There are no live questions in this part's pool."]
    make_interactive("inv-mc")
    crossword = make_interactive("inv-crossword", pool="practice")
    assert rules.validate_part(part) == []
    assert crossword not in list(rules.live_questions(part))


def test_the_stage_2_mcq_part_still_ignores_interactive_questions(
    module1, make_part, make_interactive
):
    part = make_part(questions=12, draw_n=5)
    make_interactive("inv-mc")
    assert all(q.format == "mcq" for q in rules.live_questions(part))


def test_mcq_and_interactive_parts_can_share_a_module_at_50_and_50(
    module1, make_part, make_interactive
):
    make_part(questions=12, draw_n=5, marks=50)
    make_interactive("inv-sort")
    part_b = AssessmentPart.objects.create(
        module=module1, name="B", family="interactive", marks=50, selection="all"
    )
    assert rules.validate_part(part_b) == [] and rules.module_marks_total(module1) == 100


# --- a mixed attempt: MCQ and interactive can sit in one flow ----------------------------------------------------------------


def test_item_formats_are_frozen_with_the_attempt(learner_client, interactive_part):
    attempt = start(learner_client, interactive_part(["inv-mc", "inv-sort"]))
    assert {i.format for i in attempt.items.all()} == {"mc", "sort"}


# --- the legacy importer -------------------------------------------------------------------------------------------------------


def export_json(tmp_path):
    """An export file in the shape tools/legacy_export.mjs writes, built from invented questions."""
    by_type = {}
    for q in _INVENTED.values():
        by_type.setdefault(q["type"], []).append(q)
    modules = {
        "m01": {
            "meta": {},
            "questions": [q for t in ("mc", "cards", "spot", "sort") for q in by_type[t]],
        },
        "m03": {"meta": {}, "questions": by_type["chat"]},
        "m08": {"meta": {}, "questions": by_type["crossword"]},
        "m11": {
            "meta": {},
            "questions": [dict(q, mod="Module 4") for q in by_type["hotspot"] + by_type["pick"]]
            + [dict(by_type["order"][0], mod="All topics")],
        },
    }
    path = tmp_path / "interactive.json"
    path.write_text(json.dumps({"modules": modules}), encoding="utf-8")
    return path


def test_the_importer_loads_drafts_into_the_right_pools_and_the_mock(tmp_path, capsys):
    call_command("import_legacy_interactive", "--source", str(export_json(tmp_path)))
    out = capsys.readouterr().out
    assert "have no hint" in out and "INVENTED" not in out and "Invented" not in out
    assert set(Question.objects.values_list("status", flat=True)) == {"draft"}
    assert Question.objects.get(stable_id="M8-C01").pool == "practice"  # module 8's crosswords
    mixed = Question.objects.filter(stable_id__startswith="MIX-")
    assert mixed.count() == 4 and set(mixed.values_list("pool", flat=True)) == {"practice"}
    assert Question.objects.get(stable_id="M1-C01").pool == "module_quiz"
    assert (
        Question.objects.get(stable_id="MIX-04").module.number == 10
    )  # no module named: the capstone
    assert Question.objects.get(stable_id="MIX-01").module.number == 4
    from apps.assessments.models import ProgrammeAssessment

    assert ProgrammeAssessment.objects.get(kind="mock").blueprint["questions"] == [
        "MIX-01",
        "MIX-02",
        "MIX-03",
        "MIX-04",
    ]
    assert (
        AssessmentPart.objects.filter(name="Part B: interactive").count() == 8
    )  # 1-7 and 9, not 8
    assert not AssessmentPart.objects.filter(module__number=8, family="interactive").exists()


def test_the_importer_never_publishes_and_draws_the_hotspot_picture_without_storing_svg(tmp_path):
    call_command("import_legacy_interactive", "--source", str(export_json(tmp_path)))
    hotspot = Question.objects.get(stable_id="MIX-01")
    body = hotspot.current_version.body
    assert body["image_id"] and QuestionImage.objects.filter(pk=body["image_id"]).exists()
    assert "svg" not in json.dumps(body).lower() and len(body["regions"]) == 4
    assert all(r["shape"] == "rect" for r in body["regions"])
    with pytest.raises(qservices.PublishError, match="hint"):
        qservices.publish(hotspot)


def test_a_dry_run_saves_nothing_and_stores_no_files(tmp_path, capsys):
    call_command("import_legacy_interactive", "--source", str(export_json(tmp_path)), "--dry-run")
    assert "DRY RUN" in capsys.readouterr().out
    assert Question.objects.count() == 0 and QuestionImage.objects.count() == 0


def test_the_importer_is_create_only_and_refuses_after_an_edit(tmp_path):
    path = export_json(tmp_path)
    call_command("import_legacy_interactive", "--source", str(path))
    count = Question.objects.count()
    call_command("import_legacy_interactive", "--source", str(path))
    assert Question.objects.count() == count
    question = Question.objects.get(stable_id="M1-C01")
    qservices.add_version(
        question, {**question.current_version.body, "hint": "Written by the team."}
    )
    with pytest.raises(CommandError, match="edited in the app"):
        call_command("import_legacy_interactive", "--source", str(path))


def test_art_the_importer_cannot_draw_is_left_without_a_picture_and_reported(tmp_path, capsys):
    question = dict(
        _INVENTED["inv-hotspot"],
        svg='<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="2" data-h="a"/></svg>',
        spots={"a": {"label": "A", "ok": True, "why": "x"}},
    )
    path = tmp_path / "x.json"
    path.write_text(
        json.dumps({"modules": {"m11": {"meta": {}, "questions": [question]}}}), encoding="utf-8"
    )
    call_command("import_legacy_interactive", "--source", str(path))
    out = capsys.readouterr().out
    assert "INVALID" in out or "could not be drawn" in out
    assert not QuestionImage.objects.exists()


def test_svg_with_a_doctype_is_never_parsed():
    with pytest.raises(legacy_interactive.UnsupportedArt):
        legacy_interactive.render_png(
            '<!DOCTYPE svg [<!ENTITY x "boom">]><svg viewBox="0 0 10 10"/>'
        )


def test_every_invented_legacy_question_imports_and_renders(learner_client, interactive_part):
    """Done-when: every challenge imports (parity file) and the engine's page renders it."""
    attempt = start(learner_client, interactive_part())
    for item in attempt.items.all():
        page = learner_client.get(
            reverse("attempt_question", args=[attempt.pk, item.position]), **HX
        ).content.decode()
        assert "data-engine" in page and attempt_data_attrs(page)[0]["format"] == item.format


# --- the TypeScript bundle ---------------------------------------------------------------------------------------------------------


def test_the_engine_never_inserts_markup_or_evaluates_code():
    for path in [
        ROOT / "static" / "js" / "engine.js",
        *sorted((ROOT / "engine" / "src").rglob("*.ts")),
    ]:
        text = path.read_text(encoding="utf-8")
        for banned in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
            "DOMParser",
            "srcdoc",
        ):
            assert banned not in text, (path.name, banned)


def test_the_engine_bundle_is_built_from_the_current_source_and_registers_all_formats():
    bundle = (ROOT / "static" / "js" / "engine.js").read_text(encoding="utf-8")
    for fmt in (
        "mc",
        "cards",
        "spot",
        "hotspot",
        "sort",
        "match",
        "order",
        "pick",
        "build",
        "settings",
        "dial",
        "chat",
        "crossword",
    ):
        assert re.search(rf"\b{fmt}: render", bundle), fmt
    assert "data-engine" in bundle and "data-response" in bundle
    newest = max(p.stat().st_mtime for p in (ROOT / "engine" / "src").rglob("*.ts"))
    assert (ROOT / "static" / "js" / "engine.js").stat().st_mtime >= newest - 1, (
        "rebuild with tools/build_engine.mjs"
    )


def test_the_colour_triage_buttons_carry_a_name_and_a_shape_not_just_a_colour():
    bundle = (ROOT / "static" / "js" / "engine.js").read_text(encoding="utf-8")
    for name, shape in (("Red", "■"), ("Amber", "▲"), ("Yellow", "◆"), ("Green", "●")):
        assert f'name: t("{name}")' in bundle and shape in bundle  # translated (Stage 8)
    css = (ROOT / "static" / "css" / "engine.css").read_text(encoding="utf-8")
    for tone in ("red", "amber", "yellow", "green"):
        assert f".tri--{tone}" in css
    assert "Your choice" in css  # the selected state also says so in words


def test_stage2_services_still_expose_their_names():
    assert services.make_option_map and services.save_answer and schemas.SCHEMAS["mcq"]


# --- review fixes: untouched questions earn nothing; results do not repeat the right option ------------------------

BLANK_SCORING_CASES = ["inv-pick-free", "inv-settings", "inv-cards", "inv-mc", "inv-sort"]


def stale(attempt, days=8):
    from datetime import timedelta

    from django.utils import timezone

    Attempt.objects.filter(pk=attempt.pk).update(
        last_saved_at=timezone.now() - timedelta(days=days)
    )


def test_untouched_means_no_response_or_only_the_review_flag_or_empty_values():
    from apps.assessments.scoring import untouched

    assert untouched(None) and untouched({}) and untouched({"flag": True})
    assert untouched({"picked": [], "done": False, "flag": True})
    assert untouched({"values": {}, "done": False}) and untouched("not a dict")
    assert not untouched({"picked": [], "done": True})  # a deliberate "none of these"
    assert not untouched({"values": {"tok": 0}})  # a dial left at zero is still a value
    assert not untouched({"choice": "tok"})


def test_the_legacy_credit_for_leaving_things_alone_is_kept_in_the_format_scorers_only():
    """Untouched free pick scores 1/2 and untouched settings 1/3 in the legacy engine (parity); the
    attempt scorer must still give a blank item zero."""
    from apps.assessments.scoring import score_item
    from apps.questions import formats

    for case_id, legacy in (("inv-pick-free", Decimal(1) / 2), ("inv-settings", Decimal(1) / 3)):
        fmt, body = invented_body(case_id)
        m = formats.make_map(fmt, body)
        assert formats.score(fmt, body, m, None)[0] == legacy
        assert score_item(fmt, body, m, None) == (Decimal(0), False)
        assert score_item(fmt, body, m, {"flag": True}) == (Decimal(0), False)
        assert score_item(fmt, body, m, {}) == (Decimal(0), False)


def blank_part(interactive_part):
    return interactive_part(BLANK_SCORING_CASES)


def test_a_manual_submit_of_an_untouched_attempt_scores_zero(learner_client, interactive_part):
    attempt = start(learner_client, blank_part(interactive_part))
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    attempt.refresh_from_db()
    assert attempt.score == 0 and not attempt.all_answered and not attempt.gate_breached
    assert {i.score for i in attempt.items.all()} == {0}
    assert not any(i.gate_flag for i in attempt.items.all())
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert html.count("Not answered") == len(BLANK_SCORING_CASES)
    assert "Partly right" not in html


def test_an_auto_submit_of_an_untouched_attempt_scores_zero(
    learner_client, interactive_part, learner
):
    attempt = start(learner_client, blank_part(interactive_part))
    stale(attempt)
    assert services.auto_submit_stale() == 1
    attempt.refresh_from_db()
    assert attempt.status == "auto_submitted"
    assert attempt.score == 0 and not attempt.gate_breached
    assert {i.score for i in attempt.items.all()} == {0}


def test_flagging_a_question_for_review_alone_does_not_earn_credit(
    learner_client, interactive_part
):
    attempt = start(learner_client, blank_part(interactive_part))
    for item in attempt.items.all():
        post_response(learner_client, attempt, item.position, {}, flag=True)
    stale(attempt)
    services.auto_submit_stale()
    attempt.refresh_from_db()
    assert attempt.score == 0
    assert {i.score for i in attempt.items.all()} == {0}


@pytest.mark.parametrize("auto", [False, True])
def test_actual_answers_keep_their_credit_while_blank_ones_earn_none(
    learner_client, interactive_part, auto
):
    from apps.questions import formats

    attempt = start(learner_client, blank_part(interactive_part))
    by_case = {case_of(i): i for i in attempt.items.select_related("question_version")}
    # right: full marks; a partial card answer: some right, some wrong; a finished free pick with
    # nothing ticked is a deliberate answer and keeps the legacy half credit
    post_response(
        learner_client, attempt, by_case["inv-mc"].position,
        logical(by_case["inv-mc"], spec_for("inv-mc", by_case["inv-mc"])),
    )  # fmt: skip
    cards = by_case["inv-cards"]
    partial = {0: 0, 3: 0}  # two of four cards answered, both right, no gate card touched
    post_response(learner_client, attempt, cards.position, logical(cards, {"answers": partial}))
    free = by_case["inv-pick-free"]
    post_response(learner_client, attempt, free.position, logical(free, {"picked": []}))
    if auto:
        stale(attempt)
        services.auto_submit_stale()
    else:
        learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    attempt.refresh_from_db()
    scores = {case_of(i): i.score for i in attempt.items.select_related("question_version")}
    assert scores["inv-mc"] == 1
    assert 0 < scores["inv-cards"] < 1  # partial credit for what was actually answered
    fmt, body = free.format, free.question_version.body
    stored = Attempt.objects.get(pk=attempt.pk).items.get(pk=free.pk)
    assert (
        scores["inv-pick-free"] == formats.score(fmt, body, stored.option_map, stored.response)[0]
    )
    assert scores["inv-pick-free"] > 0
    assert scores["inv-settings"] == 0 and scores["inv-sort"] == 0  # never touched
    assert attempt.score > 0


def test_the_result_page_gives_status_and_hints_without_the_correct_option_text(
    learner_client, interactive_part
):
    part = interactive_part(["inv-mc", "inv-order"])
    attempt = start(learner_client, part)
    mc = next(i for i in attempt.items.all() if case_of(i) == "inv-mc")
    right_text = _INVENTED["inv-mc"]["opts"][_INVENTED["inv-mc"]["a"]]
    post_response(learner_client, attempt, mc.position, logical(mc, spec_for("inv-mc", mc)))
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = unescape(
        learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    )
    assert "Right." in html and "Wrong." in html  # the status of each question
    assert "Invented hint for inv-mc." in html and "Invented hint for inv-order." in html
    assert right_text not in html  # not even for the question the learner got right
    assert "Your answer" not in html
