"""Every interactive question shows its scenario (`scene`) to the learner (scene fix, Nov 2026).

Before this fix the question panel drew only the title and the ask, so the 52 real questions that
carry their whole case in `scene` (Module 1, 4 and 6 Part B, Module 7 Part B, the Module 8
crosswords, six in the mixed set) showed "Verdict 1 / Is this safe, or risky?" with nothing to
judge. These tests render the panel, the staff question preview and the part preview for one body
per format and check the scenario and the other learner-visible words are there.

The real bodies are private (content-data/, gitignored). When the file is present the tests also
run over every real question; in CI they skip that part and use the invented fixture below, which
has the same shapes (tests/fixtures/legacy_invented.json plus an invented scenario).
"""

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape

from apps.assessments import rules
from apps.assessments.models import AssessmentPart, Attempt
from apps.questions import formats, legacy_interactive, schemas
from apps.questions import services as qservices
from apps.questions.projections import client_projection

from .conftest import _INVENTED

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parent.parent
REAL = Path(
    os.environ.get("CCFR_LEGACY_INTERACTIVE", ROOT / "content-data/legacy/interactive.json")
)

# One invented question per format, each given a scenario in the shape of the real ones (a generic
# numbered title for mc, "They say" / "Case" labels for build and crossword).
SCENE = "Invented scene {case}: a message says your parcel is held; pay ₹25 at bit.ly/xq-{case}."
FALLBACK_CASES = [
    "inv-mc",
    "inv-mc-triage",
    "inv-cards",
    "inv-spot-gate",
    "inv-hotspot",
    "inv-sort",
    "inv-match",
    "inv-order",
    "inv-pick-need",
    "inv-build",
    "inv-settings",
    "inv-dial",
    "inv-chat",
    "inv-crossword",
]


def fallback_question(case: str) -> dict:
    q = copy.deepcopy(_INVENTED[case])
    q["scene"] = SCENE.format(case=case)
    if q["type"] == "mc" and case == "inv-mc":
        q["title"] = "Verdict 3"  # numbered like the real Part B titles
    if q["type"] in ("build", "crossword"):
        q["sceneLabel"] = "They say" if q["type"] == "build" else "Case"
    return q


def body_of(q: dict) -> tuple[str, dict]:
    fmt, body = legacy_interactive.convert(q)
    body["hint"] = "Invented hint."
    if '"gate": true' in json.dumps(body) or body.get("gate_if_missed"):
        body["gate_message"] = body.get("gate_message") or "Invented gate message."
    return fmt, schemas.parse_body(fmt, body).model_dump()


def panel_html(fmt: str, body: dict) -> str:
    """The learner's question panel, rendered exactly as the attempt page renders it."""
    option_map = formats.make_map(fmt, body)
    q = client_projection(fmt, body, option_map)
    return render_to_string(
        "assessments/_question_panel.html",
        {
            "attempt": SimpleNamespace(pk=1),
            "position": 2,
            "total": 10,
            "q": q,
            "q_json": json.dumps(q),
            "interactive": True,
            "data_url": "/x/",
        },
    )


def learner_text(fmt: str, body: dict) -> list[str]:
    """The words of the body a learner must be able to read, outside the engine's own drawing."""
    out = [body.get("scene", ""), body.get("ask", ""), formats.display_title(body.get("title", ""))]
    if body.get("scene") and body.get("scene_label"):
        out.append(body["scene_label"])
    return [t for t in out if t]


def check_panel(fmt: str, body: dict) -> None:
    html = panel_html(fmt, body)
    for text in learner_text(fmt, body):
        assert escape(text) in html, (fmt, text)
    if body.get("scene"):
        assert 'class="qcard__scene"' in html
        assert html.index("qcard__scene") < html.index("data-engine")  # read before answering
    # the scene_label goes to the engine too (build and crossword draw it next to the scene)
    q = client_projection(fmt, body, formats.make_map(fmt, body))
    assert q["scene"] == body.get("scene", "")
    assert q["scene_label"] == body.get("scene_label", "")


# --- the fallback fixture: always runs, one per format --------------------------------------


def test_the_fallback_fixture_covers_every_interactive_format():
    covered = {_INVENTED[c]["type"] for c in FALLBACK_CASES}
    assert covered == set(formats.FORMATS) - {"mcq"}


@pytest.mark.parametrize("case", FALLBACK_CASES)
def test_the_question_panel_shows_the_scene_for_every_format(case):
    fmt, body = body_of(fallback_question(case))
    assert body["scene"]
    check_panel(fmt, body)


@pytest.mark.parametrize("case", FALLBACK_CASES)
def test_the_staff_question_preview_shows_the_scene(case, mentor_client, module1):
    fmt, body = body_of(fallback_question(case))
    question = qservices.create_question(
        stable_id=f"M1-S{FALLBACK_CASES.index(case):02d}", module=module1, fmt=fmt, body=body,
        tags={}, pool="module_quiz",
    )  # fmt: skip
    html = mentor_client.get(reverse("staff_question_preview", args=[question.pk])).content.decode()
    for text in learner_text(fmt, body):
        assert escape(text) in html, (fmt, text)
    assert Attempt.objects.count() == 0


def test_the_part_preview_shows_every_scene(client, make_user, module1):
    from allauth.mfa.models import Authenticator

    from apps.accounts.models import Role

    # live needs a picture (hotspot) or Module 8 (crossword); both are covered by the tests above
    cases = [c for c in FALLBACK_CASES if c not in ("inv-hotspot", "inv-crossword")]
    for n, case in enumerate(cases):
        fmt, body = body_of(fallback_question(case))
        question = qservices.create_question(
            stable_id=f"M1-P{n:02d}", module=module1, fmt=fmt, body=body, tags={},
            pool="module_quiz",
        )  # fmt: skip
        qservices.publish(question)
    part = AssessmentPart.objects.create(
        module=module1, name="Part B: interactive", family="interactive", marks=50, selection="all"
    )
    rules.publish_part(part)
    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    html = client.get(reverse("preview_part", args=[part.pk])).content.decode()
    for case in cases:
        assert escape(SCENE.format(case=case)) in html, case
    assert escape("They say") in html
    assert "Verdict 3" not in html and "Verdict" in html


def test_the_scene_is_escaped_never_markup():
    q = fallback_question("inv-mc")
    q["scene"] = "Click <b>here</b> & win"
    fmt, body = body_of(q)
    body["scene"] = "<script>alert(1)</script> & win"  # as if stored raw: still drawn as text
    html = panel_html(fmt, body)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; win" in html


# --- generic numbered titles (bug 1b) --------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("Verdict 1", "Verdict"),
        ("Case 10", "Case"),
        ("Situation 7", "Situation"),
        ("Quick verdict 2", "Quick verdict"),
        ("Mrs Iyer, 68", "Mrs Iyer, 68"),
        ("Crossword 1 · Spot the infection", "Crossword 1 · Spot the infection"),
        ("Tap every warning sign in this SMS.", "Tap every warning sign in this SMS."),
        ("", ""),
    ],
)
def test_a_generic_numbered_title_loses_its_number(stored, shown):
    assert formats.display_title(stored) == shown


def test_the_learner_sees_no_number_but_the_stored_body_keeps_it():
    fmt, body = body_of(fallback_question("inv-mc"))
    assert body["title"] == "Verdict 3"
    html = panel_html(fmt, body)
    assert "Verdict 3" not in html and ">Verdict</h2>" in html
    assert body["title"] == "Verdict 3"  # projection never writes back


def test_review_and_result_name_a_generic_question_by_its_scene():
    fmt, body = body_of(fallback_question("inv-mc"))
    assert formats.display_label(body) == body["scene"]
    assert formats.label(body) == "Verdict 3"  # unchanged: duplicate checks compare it
    fmt, body = body_of(fallback_question("inv-chat"))
    assert formats.display_label(body) == body["title"]  # a real title stays
    assert formats.display_label({"stem": "An MCQ stem"}) == "An MCQ stem"


def test_an_open_attempt_keeps_its_items_and_tokens(learner_client, interactive_part):
    """Data safety: an attempt started before the fix renders with the same option map and
    response; only the words around the engine change."""
    part = interactive_part(ids=["inv-mc", "inv-build"])
    learner_client.post(reverse("assess_start", args=[part.pk]))
    attempt = Attempt.objects.get(part=part)
    before = {i.pk: (copy.deepcopy(i.option_map), i.response) for i in attempt.items.all()}
    for item in attempt.items.all():
        page = learner_client.get(reverse("attempt_question", args=[attempt.pk, item.position]))
        assert page.status_code == 200
    after = {i.pk: (i.option_map, i.response) for i in attempt.items.all()}
    assert before == after


# --- the real content, when it is here (skips in CI) ----------------------------------------


def real_questions():
    if not REAL.exists():
        return []
    modules = json.loads(REAL.read_text("utf-8"))["modules"]
    return [
        (legacy_interactive.stable_id(key, i), q)
        for key, entry in modules.items()
        for i, q in enumerate(entry["questions"], start=1)
    ]


@pytest.mark.skipif(not REAL.exists(), reason="private content-data/ is not here (CI)")
def test_every_real_question_shows_its_scene_and_words():
    questions = real_questions()
    assert len(questions) == 104
    with_scene = 0
    for qid, q in questions:
        fmt, body = body_of(q)
        check_panel(fmt, body)
        with_scene += bool(body["scene"])
        assert formats.display_title(body["title"]).strip(), qid
    assert with_scene == 52
