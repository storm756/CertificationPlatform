"""The Python scorers must give the same score and safety-gate as the real legacy engine.

tests/fixtures/legacy_invented.json holds invented questions in the legacy shape. The expected
results in legacy_parity_expected.json were produced ONCE by running the real legacy engine.js on
those questions with generated answers (tools/legacy_parity.mjs), then frozen here. Nothing in
these fixtures is real content.
"""

import json
from pathlib import Path

import pytest

from apps.questions import formats, legacy_interactive, schemas

FIXTURES = Path(__file__).parent / "fixtures"
QUESTIONS = {
    e["id"]: e["question"]
    for e in json.loads((FIXTURES / "legacy_invented.json").read_text("utf-8"))
}
CASES = json.loads((FIXTURES / "legacy_parity_expected.json").read_text("utf-8"))


def test_the_fixture_covers_all_13_formats_and_safety_gates():
    assert {c["type"] for c in CASES} == {
        "mc", "cards", "spot", "hotspot", "sort", "match", "order", "pick", "build",
        "settings", "dial", "chat", "crossword",
    }  # fmt: skip
    assert len(CASES) >= 120 and not [c for c in CASES if "error" in c]
    assert sum(1 for c in CASES if c["js"]["gate"]) >= 20
    assert {c["js"]["score"] for c in CASES} >= {0, 1}


def test_python_scores_and_gates_match_the_legacy_engine_on_every_case():
    matched, mismatched = legacy_interactive.parity(QUESTIONS, CASES)
    assert not mismatched, mismatched
    assert matched == len(CASES)


@pytest.mark.parametrize("entry", list(QUESTIONS.items()), ids=list(QUESTIONS))
def test_every_invented_legacy_question_converts_to_a_valid_body(entry):
    _id, question = entry
    fmt, body = legacy_interactive.convert(question)
    parsed = schemas.parse_body(fmt, body)
    assert parsed.hint == ""  # the legacy challenges have no hint: nothing is invented
    assert schemas.publish_errors(fmt, body)  # so none can go live yet


def test_a_gate_answer_raises_the_gate_in_the_engine_and_python_alike():
    gated = [c for c in CASES if c["js"]["gate"]]
    assert gated and any(c["js"]["score"] < 1 for c in gated)  # a gate can come with a high score
    matched, mismatched = legacy_interactive.parity(QUESTIONS, gated)
    assert matched == len(gated) and not mismatched


def test_markup_in_legacy_text_is_flattened_to_plain_text():
    assert legacy_interactive.plain("<b>Bold</b> &amp; <i>fine</i><br>next") == "Bold & fine next"
    segments = legacy_interactive._spot_segments("Hi [[friend]], tap [[!this <b>link</b>]] now.")
    assert [s["text"] for s in segments] == ["Hi ", "friend", ", tap ", "this link", " now."]
    assert [s["risky"] for s in segments] == [False, False, False, True, False]


def test_formats_registry_has_every_format():
    assert set(formats.FORMATS) == {
        "mcq", "mc", "cards", "spot", "hotspot", "sort", "match", "order", "pick", "build",
        "settings", "dial", "chat", "crossword",
    }  # fmt: skip
