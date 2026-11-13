"""Stage 8 (D24): reviewed translations inside assessments, and why they are safe.

A translation may only ever change the words a learner reads. These tests prove it can't change a
score, an option's identity, the tokens, what the browser receives (no key, hint or `why`), and
that a draft or stale line never shows in an assessment.
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import translation

from apps.assessments import services
from apps.assessments.models import Attempt
from apps.questions import formats
from apps.questions.projections import client_projection
from apps.translations import keys
from apps.translations.assess import display_body, display_hint
from apps.translations.models import Translation, TranslationStatus
from apps.translations.service import translate_question_body

from .conftest import invented_body, invented_ids, right_token, wrong_token

pytestmark = pytest.mark.django_db

T = "हिं:"  # every invented translation starts with this, so it is easy to spot


def translate_all(stable_id, fmt, body, *, status=TranslationStatus.REVIEWED, lang="hi", reviewer):
    pairs = keys.question_texts(stable_id, fmt, body)
    for key, english in pairs:
        Translation.objects.update_or_create(
            key=key,
            language=lang,
            defaults={
                "text": T + english,
                "source_text": english,
                "source_hash": keys.source_hash(english),
                "status": status,
                "reviewed_by": reviewer if status == TranslationStatus.REVIEWED else None,
            },
        )
    return pairs


def skeleton(node, texts: set):
    """The body with every translatable string blanked: what must never change."""
    if isinstance(node, dict):
        return {k: skeleton(v, texts) for k, v in node.items()}
    if isinstance(node, list):
        return [skeleton(v, texts) for v in node]
    if isinstance(node, str) and (node in texts or node.startswith(T)):
        return "<text>"
    return node


def walk_pairs(a, b, path=""):
    """Yield (path, a_leaf, b_leaf) for two JSON trees that must have the same shape."""
    assert type(a) is type(b), path
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            yield from walk_pairs(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            yield from walk_pairs(x, y, f"{path}.{i}")
    else:
        yield path, a, b


@pytest.fixture
def reviewer(make_user):
    return make_user(role="admin")


# --- the body: only text changes ----------------------------------------------------------------


@pytest.mark.parametrize("case_id", invented_ids())
def test_translated_body_changes_only_text(case_id, reviewer):
    fmt, body = invented_body(case_id, image_id=1)
    stored = json.dumps(body, sort_keys=True)
    pairs = translate_all("M1-X01", fmt, body, reviewer=reviewer)
    shown = translate_question_body("M1-X01", fmt, body, "hi")
    texts = {e for _, e in pairs}
    assert skeleton(shown, texts) == skeleton(body, texts)
    if fmt == "crossword":
        assert shown == body  # D33: crosswords stay English
    else:
        assert shown != body
    assert json.dumps(body, sort_keys=True) == stored  # the stored body is never modified


@pytest.mark.parametrize("case_id", invented_ids())
def test_translation_never_changes_score_or_tokens(case_id, reviewer):
    """Score every response a learner could build against the stored body: the translated copy
    yields the same projection tokens and, when scored (which the app never does), the same score."""
    fmt, body = invented_body(case_id, image_id=1)
    translate_all("M1-X01", fmt, body, reviewer=reviewer)
    shown = translate_question_body("M1-X01", fmt, body, "hi")
    m = formats.make_map(fmt, body)
    english = client_projection(fmt, body, m)
    hindi = client_projection(fmt, shown, m)
    for path, a, b in walk_pairs(english, hindi):
        if a != b:
            assert isinstance(b, str) and b.startswith(T), f"{path} changed: {a!r} -> {b!r}"
    # the scorer is format logic over ids and tokens: the same response scores the same
    assert formats.score(fmt, body, m, None) == formats.score(fmt, shown, m, None)


@pytest.mark.parametrize("case_id", invented_ids())
def test_projection_never_carries_a_translated_hint_or_why(case_id, reviewer):
    fmt, body = invented_body(case_id, image_id=1)
    body["why"] = body.get("why") or "Invented explanation."
    translate_all("M1-X01", fmt, body, reviewer=reviewer)
    shown = translate_question_body("M1-X01", fmt, body, "hi")
    dumped = json.dumps(client_projection(fmt, shown, formats.make_map(fmt, body)), ensure_ascii=False)
    assert T + body["hint"] not in dumped
    assert T + body["why"] not in dumped


@pytest.mark.parametrize("status", [TranslationStatus.DRAFT])
def test_drafts_never_show_in_assessments(status, reviewer):
    fmt, body = invented_body(invented_ids()[0], image_id=1)
    translate_all("M1-X01", fmt, body, status=status, reviewer=reviewer)
    assert translate_question_body("M1-X01", fmt, body, "hi") is body


def test_stale_translation_falls_back_to_english(reviewer):
    fmt, body = invented_body(invented_ids()[0], image_id=1)
    translate_all("M1-X01", fmt, body, reviewer=reviewer)
    edited = json.loads(json.dumps(body))
    edited["ask"] = (edited.get("ask") or "") + " Changed."
    shown = translate_question_body("M1-X01", fmt, edited, "hi")
    assert shown["ask"] == edited["ask"]  # the English changed, so the old translation is stale


def test_english_is_never_translated(reviewer):
    fmt, body = invented_body(invented_ids()[0], image_id=1)
    translate_all("M1-X01", fmt, body, reviewer=reviewer)
    assert translate_question_body("M1-X01", fmt, body, "en") is body


def test_set_path_refuses_non_text():
    with pytest.raises(TypeError):
        keys.set_path({"correct": 2}, "correct", "3")


# --- MCQ end to end -------------------------------------------------------------------------------


def _translate_part_questions(attempt, reviewer, status=TranslationStatus.REVIEWED):
    for item in attempt.items.select_related("question_version__question"):
        version = item.question_version
        translate_all(
            version.question.stable_id, item.format, version.body, status=status, reviewer=reviewer
        )


def test_attempt_page_shows_reviewed_hindi_and_scores_the_same(
    learner, learner_client, make_part, reviewer
):
    part = make_part(questions=6, draw_n=3, min_per_tag=0)
    attempt, _new = services.start(learner, part)
    _translate_part_questions(attempt, reviewer)
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    items = list(attempt.items.select_related("question_version__question"))
    page = learner_client.get(reverse("attempt_question", args=[attempt.pk, 1]))
    html = page.content.decode()
    first = items[0].question_version.body
    assert T + first["stem"] in html
    assert first["stem"] not in html.replace(T + first["stem"], "")
    for option in first["options"]:
        assert T + option["text"] in html
    # option tokens on the page are the attempt's tokens, nothing derived from the translation
    for token in items[0].option_map["tokens"]:
        assert token in html
    # answer: right for 1 and 2, wrong for 3
    for item, token in zip(items, [right_token(items[0]), right_token(items[1]), wrong_token(items[2])], strict=True):  # fmt: skip
        services.save_answer(attempt.pk, learner, item.position, choice=token)
    closed = services.submit(attempt.pk, learner.pk)
    attempt.refresh_from_db()
    assert closed is not None
    expected = Decimal(2) / Decimal(3) * 100
    assert abs(attempt.score - expected) < Decimal("0.1")


def test_mid_attempt_switch_keeps_the_answer(learner, learner_client, make_part, reviewer):
    part = make_part(questions=6, draw_n=3, min_per_tag=0)
    attempt, _new = services.start(learner, part)
    _translate_part_questions(attempt, reviewer)
    item = attempt.items.select_related("question_version__question").get(position=1)
    token = right_token(item)
    learner_client.post(
        reverse("attempt_answer", args=[attempt.pk]),
        {"position": 1, "choice": token},
        HTTP_HX_REQUEST="true",
    )
    english = learner_client.get(reverse("attempt_question", args=[attempt.pk, 1])).content.decode()
    learner_client.post(reverse("set_language"), {"language": "hi", "next": "/"})
    hindi = learner_client.get(reverse("attempt_question", args=[attempt.pk, 1])).content.decode()
    stem = item.question_version.body["stem"]
    assert stem in english and T + stem not in english
    assert T + stem in hindi
    item.refresh_from_db()
    assert item.response["choice"] == token  # the saved answer is a token: unchanged by the switch
    # the same token is still checked on the Hindi page
    assert f'value="{token}"' in hindi


def test_draft_questions_stay_english_in_an_attempt(learner, learner_client, make_part, reviewer):
    part = make_part(questions=6, draw_n=3, min_per_tag=0)
    attempt, _new = services.start(learner, part)
    _translate_part_questions(attempt, reviewer, status=TranslationStatus.DRAFT)
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    html = learner_client.get(reverse("attempt_question", args=[attempt.pk, 1])).content.decode()
    assert T not in html


def test_result_hint_reviewed_only(learner, learner_client, make_part, reviewer):
    part = make_part(questions=6, draw_n=3, min_per_tag=0)
    attempt, _new = services.start(learner, part)
    items = list(attempt.items.select_related("question_version__question"))
    first = items[0].question_version
    hint_key = f"q:{first.question.stable_id}:hint"
    Translation.objects.create(
        key=hint_key, language="hi", text=T + "draft hint", source_text=first.body["hint"],
        source_hash=keys.source_hash(first.body["hint"]), status=TranslationStatus.DRAFT,
    )  # fmt: skip
    with translation.override("hi"):
        assert display_hint(first) == first.body["hint"]
    Translation.objects.filter(key=hint_key).update(
        status=TranslationStatus.REVIEWED, reviewed_by=reviewer
    )
    with translation.override("hi"):
        assert display_hint(first) == T + "draft hint"
    for item in items:
        services.save_answer(attempt.pk, learner, item.position, choice=wrong_token(item))
    services.submit(attempt.pk, learner.pk)
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert T + "draft hint" in html
    # the result page never shows option text, translated or not
    for option in first.body["options"]:
        assert option["text"] not in html and T + option["text"] not in html


def test_display_body_is_a_copy(make_question, reviewer):
    question = make_question(1)
    version = question.current_version
    translate_all(question.stable_id, "mcq", version.body, reviewer=reviewer)
    before = json.dumps(version.body, sort_keys=True)
    shown = display_body(version, "mcq", "hi")
    assert shown is not version.body
    assert shown["correct"] == version.body["correct"]
    assert [o["id"] for o in shown["options"]] == [o["id"] for o in version.body["options"]]
    version.refresh_from_db()
    assert json.dumps(version.body, sort_keys=True) == before
    assert Attempt.objects.count() == 0
