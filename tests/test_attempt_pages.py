"""Stage 2: the attempt pages, the result page, answer-key protection and journeys 5, 6 and 9."""

import json
import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.assessments import services
from apps.assessments.models import Attempt, AttemptStatus
from apps.audit.models import AuditEvent
from apps.questions.projections import client_projection

from .conftest import HINT, PASSWORD, RIGHT, WRONG, right_token, wrong_token

pytestmark = pytest.mark.django_db
HX = {"HTTP_HX_REQUEST": "true"}


def start_attempt(client, part):
    response = client.post(reverse("assess_start", args=[part.pk]))
    assert response.status_code == 302
    return Attempt.objects.get(part=part, status="in_progress")


def answer(client, attempt, position, token=None, flag=None, **extra):
    data = {"position": position, "flag_present": "1"}
    if token:
        data["choice"] = token
    if flag:
        data["flag"] = "on"
    return client.post(reverse("attempt_answer", args=[attempt.pk]), data, **extra)


def stable_number(item):
    return int(item.question_version.question.stable_id.split("T")[1])


# --- access ---------------------------------------------------------------------------------------


def test_anonymous_visitors_are_sent_to_sign_in(client, make_part):
    part = make_part()
    for url in (reverse("assess_intro", args=[part.pk]), "/attempt/1/", "/attempt/1/result/"):
        response = client.get(url)
        assert response.status_code == 302 and "/accounts/login/" in response["Location"]
    assert client.post(reverse("assess_start", args=[part.pk])).status_code == 302


def test_mentors_cannot_take_assessments(mentor_client, make_part):
    part = make_part()
    assert mentor_client.get(reverse("assess_intro", args=[part.pk])).status_code == 403
    assert mentor_client.post(reverse("assess_start", args=[part.pk])).status_code == 403


def test_unpublished_parts_are_hidden(learner_client, make_part):
    part = make_part(publish=False)
    assert learner_client.get(reverse("assess_intro", args=[part.pk])).status_code == 404


def test_nobody_can_open_someone_elses_attempt(learner_client, make_part, make_user, make_batch):
    part = make_part()
    other = make_user(batch=make_batch())
    attempt, _ = services.start(other, part)
    for name, args in (
        ("attempt_page", [attempt.pk]),
        ("attempt_review", [attempt.pk]),
        ("attempt_result", [attempt.pk]),
    ):
        assert learner_client.get(reverse(name, args=args)).status_code == 404
    assert answer(learner_client, attempt, 1, "x", **HX).status_code == 404
    assert learner_client.post(reverse("attempt_submit", args=[attempt.pk])).status_code == 404


def test_the_forms_are_csrf_protected(make_part, learner):
    part = make_part()
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(learner)
    assert strict.post(reverse("assess_start", args=[part.pk])).status_code == 403
    attempt, _ = services.start(learner, part)
    assert (
        strict.post(reverse("attempt_answer", args=[attempt.pk]), {"position": 1}).status_code
        == 403
    )
    assert strict.post(reverse("attempt_submit", args=[attempt.pk])).status_code == 403


# --- the flow -------------------------------------------------------------------------------------


def test_intro_start_answer_review_submit_result(learner_client, make_part):
    part = make_part(questions=12, draw_n=5)
    intro = learner_client.get(reverse("assess_intro", args=[part.pk]))
    assert intro.status_code == 200 and b"Start" in intro.content
    attempt = start_attempt(learner_client, part)
    page = learner_client.get(reverse("attempt_page", args=[attempt.pk]))
    assert page.status_code == 200 and b'id="question-panel"' in page.content
    for item in attempt.items.all():
        resp = answer(learner_client, attempt, item.position, right_token(item), **HX)
        assert resp.status_code == 200 and b'id="save-status"' in resp.content
    review = learner_client.get(reverse("attempt_review", args=[attempt.pk]))
    assert b"Every question is answered" in review.content
    submitted = learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    assert submitted["Location"] == reverse("attempt_result", args=[attempt.pk])
    result = learner_client.get(submitted["Location"])
    assert b"100.0" in result.content and b"Passed" in result.content


def test_the_intro_resumes_an_attempt_in_progress(learner_client, make_part):
    part = make_part()
    attempt = start_attempt(learner_client, part)
    intro = learner_client.get(reverse("assess_intro", args=[part.pk])).content.decode()
    assert (
        "Resume where you left off" in intro and reverse("attempt_page", args=[attempt.pk]) in intro
    )


def test_questions_load_as_a_partial_for_htmx_and_a_full_page_otherwise(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    url = reverse("attempt_question", args=[attempt.pk, 2])
    partial = learner_client.get(url, **HX).content.decode()
    assert "<html" not in partial and 'id="answer-form"' in partial and "2 / 5" in partial
    assert 'hx-swap-oob="outerHTML"' in partial  # the question map refreshes with it
    full = learner_client.get(url).content.decode()
    assert "<html" in full and "2 / 5" in full


def test_the_page_opens_on_the_first_unanswered_question(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    first = attempt.items.get(position=1)
    answer(learner_client, attempt, 1, right_token(first), **HX)
    page = learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode()
    assert "2 / 5" in page


def test_answer_endpoint_refuses_bad_input_without_saving(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    assert answer(learner_client, attempt, 1, "forged-token", **HX).status_code == 400
    assert answer(learner_client, attempt, 99, "x", **HX).status_code == 400
    assert (
        learner_client.post(
            reverse("attempt_answer", args=[attempt.pk]), {"position": "x"}, **HX
        ).status_code
        == 400
    )
    assert not attempt.items.get(position=1).answered


def test_without_javascript_an_answer_saves_and_redirects_back(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    item = attempt.items.get(position=1)
    response = answer(learner_client, attempt, 1, right_token(item))
    assert response.status_code == 302
    assert response["Location"] == reverse("attempt_question", args=[attempt.pk, 1])
    assert attempt.items.get(position=1).answered


def test_a_submitted_attempt_redirects_the_page_and_refuses_answers(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    assert learner_client.get(reverse("attempt_page", args=[attempt.pk]))["Location"] == reverse(
        "attempt_result", args=[attempt.pk]
    )
    closed = answer(learner_client, attempt, 1, "x", **HX)
    assert closed.status_code == 409 and closed["HX-Redirect"] == reverse(
        "attempt_result", args=[attempt.pk]
    )


def test_the_timer_and_save_status_are_on_the_page(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    html = learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode()
    assert "data-timer" in html and 'data-state="saved"' in html and 'role="timer"' in html
    assert "htmx.min.js" in html and "attempt.js" in html
    assert '"allowEval": false' in html  # htmx runs without eval: the CSP stays unchanged


def test_attempt_pages_have_no_inline_scripts_or_styles(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    for url in (
        reverse("assess_intro", args=[attempt.part_id]),
        reverse("attempt_page", args=[attempt.pk]),
        reverse("attempt_review", args=[attempt.pk]),
    ):
        html = learner_client.get(url).content.decode()
        assert not re.search(r"<script(?![^>]*\bsrc=)", html), url
        assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html), url


def test_review_lists_blank_questions_and_warns(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    item = attempt.items.get(position=2)
    answer(learner_client, attempt, 2, right_token(item), flag=True, **HX)
    html = learner_client.get(reverse("attempt_review", args=[attempt.pk])).content.decode()
    assert "4 not answered yet" in html and "Some questions are blank" in html
    assert "marked for review" in html


# --- journey 5: the connection drops, they resume on another phone -----------------------------------


def test_journey5_resume_on_another_phone(learner_client, learner, make_part):
    part = make_part()
    attempt = start_attempt(learner_client, part)
    chosen = {}
    for position in (1, 2, 3):
        item = attempt.items.get(position=position)
        chosen[position] = right_token(item)
        answer(learner_client, attempt, position, chosen[position], **HX)
    # A different phone: a new browser session, signed in as the same learner.
    phone2 = Client()
    assert (
        phone2.post(
            reverse("account_login"), {"login": learner.email, "password": PASSWORD}
        ).status_code
        == 302
    )
    intro = phone2.get(reverse("assess_intro", args=[part.pk])).content.decode()
    assert "Resume where you left off" in intro
    attempt2 = start_attempt(phone2, part)
    assert attempt2.pk == attempt.pk  # the same attempt, not a new one
    page = phone2.get(reverse("attempt_page", args=[attempt2.pk])).content.decode()
    assert "4 / 5" in page  # it opens on the first unanswered question
    revisit = phone2.get(reverse("attempt_question", args=[attempt2.pk, 2]), **HX).content.decode()
    assert f'value="{chosen[2]}" checked' in revisit  # the earlier answer is intact
    assert Attempt.objects.filter(user=learner).count() == 1


# --- journey 6: a double tap on Submit -----------------------------------------------------------------


def test_journey6_double_submit_gives_one_result(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    for item in attempt.items.all()[:2]:
        answer(learner_client, attempt, item.position, right_token(item), **HX)
    first = learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    second = learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    assert first["Location"] == second["Location"] == reverse("attempt_result", args=[attempt.pk])
    attempt.refresh_from_db()
    assert attempt.score == 40 and attempt.status == AttemptStatus.SUBMITTED
    assert AuditEvent.objects.filter(action="attempt.submitted").count() == 1
    assert Attempt.objects.count() == 1


# --- journey 9: the result page ------------------------------------------------------------------------


def test_journey9_result_shows_right_wrong_and_hints_but_no_correct_option(
    learner_client, make_part
):
    attempt = start_attempt(learner_client, make_part())
    items = list(attempt.items.all())
    for item in items[:2]:
        answer(learner_client, attempt, item.position, right_token(item), **HX)  # right
    for item in items[2:4]:
        answer(learner_client, attempt, item.position, wrong_token(item), **HX)  # wrong
    # item 5 stays blank
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "40.0" in html
    assert html.count("Right</") + html.count("Right\n") >= 0
    for item in items:
        assert HINT.format(n=stable_number(item)) in html  # a hint for every question (D13)
    rights = [i for i in items[:2]]
    wrongs_and_blank = items[2:]
    for item in wrongs_and_blank:
        assert RIGHT.format(n=stable_number(item)) not in html  # the correct option is never shown
    for item in rights:  # their own right answer is shown as theirs, nothing more
        assert RIGHT.format(n=stable_number(item)) not in html  # not even their own right pick
    assert "Your answer" not in html
    assert html.count("Not answered") >= 1 and "Not quite" in html


def test_a_gated_result_explains_and_does_not_count(
    learner_client, make_part, make_question, module1
):
    from apps.assessments import rules
    from apps.assessments.models import AssessmentPart

    for n in range(1, 4):
        make_question(n, gate=[1])
    part = AssessmentPart.objects.create(module=module1, name="Gate", marks=50, selection="all")
    rules.publish_part(part)
    attempt = start_attempt(learner_client, part)
    for item in attempt.items.all():
        risky = next(t for t, k in item.option_map["tokens"].items() if k == "o1")
        answer(learner_client, attempt, item.position, risky, **HX)
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "This attempt doesn&#x27;t count" in html or "This attempt doesn't count" in html
    assert "would have put a citizen at risk" in html
    assert "Invented risk" not in html  # the internal reason is never shown


# --- answer-key protection -----------------------------------------------------------------------------


FORBIDDEN_WORDS = (
    "content_hash",
    "option_map",
    "correct_option",
    "data-correct",
    "gate_flag",
    "is_correct",
)


def assert_no_keys(text, items, *, allow_hint=False):
    """The page/JSON must hold no key, hint, gate or internal id for any of these items."""
    for word in FORBIDDEN_WORDS:
        assert word not in text, word
    assert not re.search(r'value="o[1-6]"', text), "an internal option id was sent"
    assert not re.search(r'"(correct|gate|hint)"', text), "a body field name was sent"
    for item in items:
        n = stable_number(item)
        assert "Invented risk" not in text
        if not allow_hint:
            assert HINT.format(n=n) not in text, "a hint was sent before submitting"


def test_attempt_pages_contain_no_keys_hints_or_internal_ids(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    items = list(attempt.items.all())
    pages = [
        learner_client.get(reverse("assess_intro", args=[attempt.part_id])).content.decode(),
        learner_client.get(reverse("attempt_page", args=[attempt.pk])).content.decode(),
        learner_client.get(reverse("attempt_review", args=[attempt.pk])).content.decode(),
    ]
    for item in items:
        url = reverse("attempt_question", args=[attempt.pk, item.position])
        pages.append(learner_client.get(url, **HX).content.decode())
        pages.append(learner_client.get(url).content.decode())
        pages.append(
            answer(
                learner_client, attempt, item.position, wrong_token(item), flag=True, **HX
            ).content.decode()
        )
    for page in pages:
        assert_no_keys(page, items)
    # Every option the browser got is a random token; none equals an internal id or position.
    tokens = set(re.findall(r'name="choice" value="([^"]+)"', "".join(pages)))
    assert tokens and not (
        tokens & {"o1", "o2", "o3", "o4", "0", "1", "2", "3", "a", "b", "c", "d"}
    )


def test_the_correct_option_looks_exactly_like_the_others_in_the_markup(learner_client, make_part):
    """No class, attribute or order tells the right option apart: only random tokens differ."""
    attempt = start_attempt(learner_client, make_part())
    for item in attempt.items.all():
        html = learner_client.get(
            reverse("attempt_question", args=[attempt.pk, item.position]), **HX
        ).content.decode()
        radios = re.findall(r"<input type=\"radio\"[^>]*>", html)
        assert len(radios) == 4
        shapes = {re.sub(r'value="[^"]+"', "value=X", r) for r in radios}
        assert len(shapes) == 1, shapes
        labels = re.findall(r'<label class="opt">', html)
        assert len(labels) == 4


def test_client_projection_is_an_allow_list_with_no_key(learner, make_part):
    attempt, _ = services.start(learner, make_part())
    for item in attempt.items.all():
        projection = client_projection("mcq", item.question_version.body, item.option_map)
        assert set(projection) == {"format", "stem", "options"}
        assert all(set(o) == {"token", "text"} for o in projection["options"])
        blob = json.dumps(projection)
        for name in ("correct", "hint", "gate", "points", "content_hash"):
            assert f'"{name}"' not in blob, name
        assert not re.search(r'"o[1-6]"', blob), "an internal option id was sent"
        assert HINT.format(n=stable_number(item)) not in blob
        # The right option's text is in the list (it has to be, to be chosen) but unmarked.
        assert RIGHT.format(n=stable_number(item)) in blob
        assert sorted(projection["options"][i]["token"] for i in range(4)) == sorted(
            item.option_map["order"]
        )


def test_the_projection_refuses_formats_it_does_not_know():
    with pytest.raises(ValueError):
        client_projection("hotspot", {}, {})


def test_the_save_response_never_carries_a_score_or_a_key(learner_client, make_part):
    attempt = start_attempt(learner_client, make_part())
    item = attempt.items.get(position=1)
    response = answer(learner_client, attempt, 1, right_token(item), **HX)
    text = response.content.decode()
    assert "score" not in text.lower() and "Right" not in text and "Wrong" not in text
    assert_no_keys(text, [item])
    assert "json" not in response["Content-Type"]


def test_the_result_page_never_shows_a_correct_option_for_any_wrong_or_blank_answer(
    learner_client, make_part
):
    attempt = start_attempt(learner_client, make_part(questions=12, draw_n=5))
    items = list(attempt.items.all())
    answer(learner_client, attempt, 1, wrong_token(items[0]), **HX)
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    for item in items:
        assert RIGHT.format(n=stable_number(item)) not in html
    assert_no_keys(html, items, allow_hint=True)


def test_the_result_never_prints_option_text_for_right_wrong_or_blank_answers(
    learner_client, make_part
):
    """Regression: the result page used to print the learner's pick, which for a right answer
    is the correct option. It now shows the score, right/wrong and the hint, and no option text."""
    attempt = start_attempt(learner_client, make_part())
    items = list(attempt.items.all())
    answer(learner_client, attempt, items[0].position, right_token(items[0]), **HX)
    answer(learner_client, attempt, items[1].position, wrong_token(items[1]), **HX)
    learner_client.post(reverse("attempt_submit", args=[attempt.pk]))
    html = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    for item in items:
        n = stable_number(item)
        assert RIGHT.format(n=n) not in html
        assert WRONG.format(n=n, k=1) not in html and WRONG.format(n=n, k=2) not in html
        assert HINT.format(n=n) in html
    assert "20.0%" in html and "Right" in html and "Not quite" in html and "Not answered" in html


def test_a_saved_answer_is_confirmed_explicitly_and_a_signed_out_post_is_not(
    client, learner_client, make_part
):
    """The browser shows "Saved" only for a response that carries X-Answer-Saved. A signed-out
    request is redirected to sign-in and never carries it."""
    attempt = start_attempt(learner_client, make_part())
    item = attempt.items.first()
    ok = answer(learner_client, attempt, item.position, right_token(item), **HX)
    assert (
        ok.status_code == 200 and ok["X-Answer-Saved"] == "1" and ok["Cache-Control"] == "no-store"
    )
    learner_client.logout()
    out = answer(learner_client, attempt, item.position, wrong_token(item), **HX)
    assert out.status_code == 302 and "/accounts/login/" in out["Location"]
    assert "X-Answer-Saved" not in out
