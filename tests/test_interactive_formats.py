"""Stage 3: the 13 interactive formats. Allow-listed projections, random tokens, response checks,
scorers and the schemas. Every question here is invented (tests/fixtures/legacy_invented.json)."""

import json
import re
from decimal import Decimal

import pytest

from apps.questions import formats, schemas

from .conftest import invented_body, invented_ids

IDS = invented_ids()

# The only keys the browser may ever receive, per format. Anything else is a leak.
COMMON = {"format", "title", "ask", "scene", "response"}
ALLOWED = {
    "mc": COMMON | {"options", "triage"},
    "cards": COMMON | {"labels", "items"},
    "spot": COMMON | {"segments", "style", "redact", "look_for"},
    "hotspot": COMMON | {"image", "legend", "regions"},
    "sort": COMMON | {"bins", "items"},
    "match": COMMON | {"lefts", "rights", "left_label", "right_label"},
    "order": COMMON | {"items"},
    "pick": COMMON | {"items", "need", "check_label"},
    "build": COMMON | {"slots", "chips", "scene_label"},
    "settings": COMMON | {"rows", "device", "screen", "check_label"},
    "dial": COMMON | {"rows"},
    "chat": COMMON | {"who", "total_steps", "steps"},
    "crossword": COMMON | {"rows", "cols", "cells", "words"},
}
NESTED = {  # nested object keys that are allowed (flattened across formats)
    "token", "text", "tone", "label", "shape", "coords", "alt", "available", "kind", "options", "start",
    "unit", "min", "max", "steps", "chips", "row", "col", "number", "dir", "clue", "length", "cells",
    "say", "chosen", "replies",
}  # fmt: skip
FORBIDDEN_NAMES = (
    "correct", "answer", "ok", "risky", "bin", "want", "score", "gate", "why", "hint", "tol", "tappable",
    "gate_message", "gate_if_missed", "image_id", "content_hash",
)  # fmt: skip


def keys_of(node):
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= keys_of(value)
    elif isinstance(node, list):
        for item in node:
            found |= keys_of(item)
    return found


def build(case_id):
    fmt, body = invented_body(case_id, image_id=1)
    return fmt, body, formats.make_map(fmt, body)


# --- projections: an allow-list, with no answer data in it -------------------------------------------------


@pytest.mark.parametrize("case_id", IDS)
def test_projection_has_only_allowed_keys_and_no_answer_data(case_id):
    fmt, body, m = build(case_id)
    projection = formats.project(fmt, body, m, None)
    assert set(projection) <= ALLOWED[fmt], set(projection) - ALLOWED[fmt]
    nested = keys_of({k: v for k, v in projection.items() if k not in ("response",)})
    assert nested <= ALLOWED[fmt] | NESTED, nested - ALLOWED[fmt] - NESTED
    blob = json.dumps(projection)
    for name in FORBIDDEN_NAMES:
        assert f'"{name}"' not in blob, (case_id, name)
    secrets_ = [t for t in (body["hint"], body.get("why"), body.get("gate_message")) if t]
    assert body["hint"] in secrets_
    for secret in secrets_:
        assert secret not in blob


@pytest.mark.parametrize("case_id", IDS)
def test_no_projection_contains_markup_or_svg_from_content(case_id):
    """Content is plain text: there is no HTML or SVG in what the browser receives."""
    fmt, body, m = build(case_id)
    blob = json.dumps(formats.project(fmt, body, m, None))
    assert "<" not in blob and ">" not in blob and "&lt;" not in blob


def test_html_in_legacy_text_never_survives_into_a_body():
    from apps.questions import legacy_interactive

    question = {
        "type": "pick", "title": "<script>alert(1)</script>Safe title", "ask": "<img src=x onerror=alert(1)> ask",
        "items": [{"t": "<b>bold</b> one", "ok": True}, {"t": "two<br>lines", "ok": False}], "why": "<i>why</i>",
    }  # fmt: skip
    _fmt, body = legacy_interactive.convert(question)
    blob = json.dumps(body)
    assert "<" not in blob and ">" not in blob
    assert body["title"] == "alert(1)Safe title" and body["items"][1]["text"] == "two lines"


# --- tokens: random per attempt, nothing to infer from ids, order or source position -------------------------


@pytest.mark.parametrize("case_id", IDS)
def test_tokens_are_random_unique_and_not_position_based(case_id):
    fmt, body, m = build(case_id)
    tokens = list(m["refs"])
    assert len(tokens) == len(set(tokens)) and tokens
    assert all(len(t) >= 10 and re.fullmatch(r"[A-Za-z0-9_-]+", t) for t in tokens)
    assert not any(
        re.fullmatch(r"[a-z]{1,3}\d{1,3}", t) for t in tokens
    )  # nothing like o00, c03, i00, r00
    other = formats.make_map(fmt, body)
    assert not (set(tokens) & set(other["refs"]))  # a second attempt shares no token


def correct_positions(fmt, body, m, samples=300):
    """Where do the right things land when tokens are sorted? (Should look like chance.)"""
    ranks = []
    for _ in range(samples):
        m = formats.make_map(fmt, body)
        if fmt == "pick":
            table, good = "items", [i for i, it in enumerate(body["items"]) if it["ok"]]
        elif fmt == "sort":
            table, good = "items", [i for i, it in enumerate(body["items"]) if it["bin"] == 0]
        elif fmt == "mc":
            table, good = "options", [body["correct"]]
        elif fmt == "build":
            table, good = "chips", [a for s in body["slots"] for a in s["answer"]]
        elif fmt == "match":
            table, good = "rights", list(range(len(body["pairs"])))
        else:  # order: the first step
            table, good = "items", [0]
        tokens = formats.by_index(m, table)
        ordered = sorted(tokens)
        ranks += [ordered.index(tokens[i]) / (len(tokens) - 1) for i in good]
    return sum(ranks) / len(ranks)


@pytest.mark.parametrize(
    "case_id", ["inv-pick-need", "inv-sort", "inv-mc", "inv-build", "inv-match", "inv-order"]
)
def test_sorting_the_tokens_reveals_nothing_about_the_answer(case_id):
    fmt, body, _ = build(case_id)
    mean = correct_positions(fmt, body, None)
    assert 0.42 < mean < 0.58, mean  # chance is 0.5: ids sorted by token say nothing


@pytest.mark.parametrize(
    "case_id", ["inv-pick-need", "inv-sort", "inv-order", "inv-match", "inv-cards"]
)
def test_the_display_order_is_not_the_source_order(case_id):
    """Authors list right answers first, so the shown order must not follow the source order."""
    fmt, body, _ = build(case_id)
    same = 0
    table = "items" if fmt != "match" else "lefts"
    for _ in range(100):
        m = formats.make_map(fmt, body)
        shown = [m["refs"][t][1] for t in m["lists"][table]]
        same += shown == sorted(shown)
    assert same < 20  # an unshuffled list would be 100


def test_an_order_question_is_never_shown_already_in_the_right_order():
    fmt, body, _ = build("inv-order")
    for _ in range(200):
        m = formats.make_map(fmt, body)
        assert [m["refs"][t][1] for t in m["lists"]["items"]] != list(range(len(body["items"])))


def test_colour_triage_keeps_the_four_colours_in_a_fixed_order_with_random_tokens():
    fmt, body, _ = build("inv-mc-triage")
    seen = set()
    for _ in range(20):
        m = formats.make_map(fmt, body)
        projection = formats.project(fmt, body, m, None)
        assert [o["tone"] for o in projection["options"]] == ["red", "amber", "yellow", "green"]
        assert projection["triage"] is True
        seen.add(projection["options"][2]["token"])  # the (correct) yellow button's token changes
    assert len(seen) == 20


def test_chat_only_sends_the_next_step_after_the_reply_is_saved():
    fmt, body, m = build("inv-chat")
    first = formats.project(fmt, body, m, None)
    assert len(first["steps"]) == 1 and "replies" in first["steps"][0]
    blob = json.dumps(first)
    assert (
        "Invented second line." not in blob and "Invented reply d" not in blob
    )  # step 2 is not here yet
    reply = first["steps"][0]["replies"][0]["token"]
    second = formats.project(fmt, body, m, {"replies": [reply]})
    assert len(second["steps"]) == 2 and second["steps"][0]["chosen"] == reply
    assert "Invented second line." in json.dumps(
        second
    ) and "Invented third line." not in json.dumps(second)
    for step in second["steps"][:1]:
        assert set(step) == {"say", "chosen", "text"}  # what they said, nothing about how it scored


def test_crossword_projection_has_the_grid_and_clues_but_no_letters():
    fmt, body, m = build("inv-crossword")
    projection = formats.project(fmt, body, m, None)
    blob = json.dumps(projection)
    for word in ("SAFE", "SALT", "EVEN"):
        assert word not in blob
    assert projection["rows"] == 4 and len(projection["words"]) == 3
    assert [w["number"] for w in projection["words"] if w["dir"] == "A"] == [1]


def test_hotspot_projection_has_shapes_but_not_which_are_right():
    fmt, body, m = build("inv-hotspot")
    projection = formats.project(fmt, body, m, None)
    assert projection["image"] == {"alt": "Invented hotspot", "available": True}
    assert len(projection["regions"]) == 4
    assert all(set(r) == {"token", "label", "shape", "coords"} for r in projection["regions"])


def test_spot_projection_hides_which_segments_are_risky():
    fmt, body, m = build("inv-spot-gate")
    projection = formats.project(fmt, body, m, None)
    tappable = [s for s in projection["segments"] if s["token"]]
    assert len(tappable) == 5 and '"risky"' not in json.dumps(projection)
    assert [s["text"] for s in projection["segments"]][0].startswith("Dear")


# --- responses: only tokens that belong to this item are accepted ---------------------------------------------


def some_token(m, table):
    return formats.by_index(m, table)[0]


@pytest.mark.parametrize(
    ("case_id", "bad"),
    [
        ("inv-mc", {"choice": "not-a-token"}),
        ("inv-mc", {"choice": 3}),
        ("inv-cards", {"answers": {"x": "y"}}),
        ("inv-spot-gate", {"picked": ["x"]}),
        ("inv-hotspot", {"picked": ["x"]}),
        ("inv-sort", {"placed": {"x": "y"}}),
        ("inv-match", {"links": {"x": "y"}}),
        ("inv-order", {"sequence": ["x"]}),
        ("inv-pick-need", {"picked": ["x"]}),
        ("inv-build", {"filled": {"x": "y"}}),
        ("inv-settings", {"values": {"x": 1}}),
        ("inv-dial", {"values": {"x": 1}}),
        ("inv-chat", {"replies": ["x"]}),
        ("inv-crossword", {"letters": {"x": "A"}}),
    ],
)
def test_foreign_tokens_are_refused_in_every_format(case_id, bad):
    fmt, body, m = build(case_id)
    with pytest.raises(formats.ResponseError):
        formats.clean_response(fmt, body, m, bad)


def test_tokens_from_another_attempt_or_another_table_are_refused():
    fmt, body, m = build("inv-sort")
    other = formats.make_map(fmt, body)
    item, bin_ = some_token(m, "items"), some_token(m, "bins")
    with pytest.raises(formats.ResponseError):
        formats.clean_response(fmt, body, m, {"placed": {some_token(other, "items"): bin_}})
    with pytest.raises(formats.ResponseError):
        formats.clean_response(
            fmt, body, m, {"placed": {item: item}}
        )  # an item token used as a bin
    assert formats.clean_response(fmt, body, m, {"placed": {item: bin_}}) == {
        "placed": {item: bin_}
    }


def test_shape_and_size_checks():
    fmt, body, m = build("inv-pick-need")
    items = formats.by_index(m, "items")
    with pytest.raises(formats.ResponseError):
        formats.clean_response(fmt, body, m, {"picked": items[:4]})  # more than need
    assert formats.clean_response(fmt, body, m, {"picked": [items[0], items[0]]})["picked"] == [
        items[0]
    ]
    fmt, body, m = build("inv-match")
    rights = formats.by_index(m, "rights")
    lefts = formats.by_index(m, "lefts")
    with pytest.raises(formats.ResponseError):
        formats.clean_response(fmt, body, m, {"links": {lefts[0]: rights[0], lefts[1]: rights[0]}})
    fmt, body, m = build("inv-dial")
    row = some_token(m, "rows")
    for bad in ("5", 5.5, True, 10**9):
        with pytest.raises(formats.ResponseError):
            formats.clean_response(fmt, body, m, {"values": {row: bad}})
    fmt, body, m = build("inv-crossword")
    cell = some_token(m, "cells")
    for bad in ("", "AB", "1", None):
        with pytest.raises(formats.ResponseError):
            formats.clean_response(fmt, body, m, {"letters": {cell: bad}})
    with pytest.raises(formats.ResponseError):
        formats.clean_response(fmt, body, m, {"letters": {f"t{i}": "A" for i in range(300)}})
    fmt, body, m = build("inv-chat")
    first = formats.by_index(m, "step0")[0]
    later = formats.by_index(m, "step1")[0]
    with pytest.raises(formats.ResponseError):
        formats.clean_response(
            fmt, body, m, {"replies": [later]}
        )  # a step-2 token in step 1's place
    assert formats.clean_response(fmt, body, m, {"replies": [first]}) == {"replies": [first]}


def test_build_only_accepts_cards_offered_for_that_slot():
    fmt, body, m = build("inv-build")
    slots, chips = formats.by_index(m, "slots"), formats.by_index(m, "chips")
    with pytest.raises(formats.ResponseError):
        formats.clean_response(
            fmt, body, m, {"filled": {slots[0]: chips[7]}}
        )  # chip 7 isn't offered for slot 1
    assert formats.clean_response(fmt, body, m, {"filled": {slots[0]: chips[0]}})


# --- completeness: what counts as "answered" -------------------------------------------------------------------


def test_completeness_per_format():
    fmt, body, m = build("inv-sort")
    items, bins = formats.by_index(m, "items"), formats.by_index(m, "bins")
    assert not formats.complete(fmt, body, m, {"placed": {items[0]: bins[0]}})
    assert formats.complete(fmt, body, m, {"placed": {i: bins[0] for i in items}})
    fmt, body, m = build("inv-pick-free")
    assert not formats.complete(fmt, body, m, {"picked": []}) and formats.complete(
        fmt, body, m, {"picked": [], "done": True}
    )
    fmt, body, m = build("inv-pick-need")
    items = formats.by_index(m, "items")
    assert formats.complete(fmt, body, m, {"picked": items[:3]}) and not formats.complete(
        fmt, body, m, {"picked": items[:2]}
    )
    fmt, body, m = build("inv-chat")
    assert not formats.complete(fmt, body, m, {"replies": [formats.by_index(m, "step0")[0]]})
    fmt, body, m = build("inv-mc")
    assert not formats.complete(fmt, body, m, {}) and not formats.complete(fmt, body, m, None)


# --- scorers: the rules, shown on small cases (parity with the legacy engine is in test_scorer_parity) ----------


def token_response(fmt, body, m, logical):
    from apps.questions import legacy_interactive

    return legacy_interactive.logical_response(fmt, body, m, logical)


def score_of(case_id, logical):
    fmt, body, m = build(case_id)
    return formats.score(fmt, body, m, token_response(fmt, body, m, logical))


def test_spot_wrong_taps_subtract_and_the_score_never_goes_below_zero():
    # three risky parts; tapping 1 right + 2 wrong floors at 0; 2 right + 1 wrong = 1/3
    assert score_of("inv-spot-gate", {"picked": [1]})[0] == Decimal(1) / 3
    assert score_of("inv-spot-gate", {"picked": [0, 3]})[0] == 0
    assert score_of("inv-spot-gate", {"picked": [1, 2, 0]})[0] == Decimal(1) / 3


def test_spot_gate_when_a_risky_part_is_missed_but_never_for_a_blank_question():
    assert score_of("inv-spot-gate", {"picked": [1]})[1] is True
    fmt, body, m = build("inv-spot-gate")
    assert formats.score(fmt, body, m, None)[1] is False  # nothing answered: no gate
    assert formats.score(fmt, body, m, {"picked": []})[1] is False  # not marked finished: no gate
    assert score_of("inv-spot-gate", {"picked": [1, 2, 4]}) == (Decimal(1), False)


def test_pick_with_need_scores_good_minus_bad_over_need_and_gates_a_bad_pick():
    perfect = score_of("inv-pick-need", {"picked": [0, 2, 4]})
    assert perfect == (Decimal(1), False)
    gated = score_of("inv-pick-need", {"picked": [0, 1, 2]})  # item 1 is a gate item and wrong
    assert gated == (Decimal(1) / 3, True)


def test_sort_scores_the_share_in_the_right_bin_and_a_gate_item_in_the_wrong_one_gates():
    perfect = {"placed": {0: 0, 1: 1, 2: 0, 3: 1, 4: 0}}
    assert score_of("inv-sort", perfect) == (Decimal(1), False)
    wrong_gate = {"placed": {0: 1, 1: 1, 2: 0, 3: 1, 4: 0}}
    assert score_of("inv-sort", wrong_gate) == (Decimal(4) / 5, True)


def test_order_counts_steps_in_the_right_place():
    assert score_of("inv-order", {"sequence": [0, 1, 2, 3, 4]})[0] == 1
    assert score_of("inv-order", {"sequence": [1, 0, 2, 3, 4]})[0] == Decimal(3) / 5


def test_chat_adds_reply_points_and_gates_on_a_gate_reply():
    best = {"replies": [0, 1, 1]}
    assert score_of("inv-chat", best) == (Decimal(6) / 6, False)
    assert score_of("inv-chat", {"replies": [2, 0, 0]}) == (Decimal(1) / 6, True)


def test_dial_uses_the_tolerance_and_wraps_times_around_midnight():
    assert score_of("inv-dial", {"values": {0: 600, 1: 7, 2: 1430}})[0] == 1
    assert (
        score_of("inv-dial", {"values": {0: 611, 1: 9, 2: 1430 - 1440}})[0] == Decimal(1) / 3
    )  # time wraps
    assert (
        score_of("inv-dial", {"values": {0: 590, 1: 8, 2: -10}})[0] == 1
    )  # within tolerance; -10 min == 23:50


def test_settings_check_untouched_rows_at_their_starting_value():
    fmt, body, m = build("inv-settings")
    assert formats.score(fmt, body, m, {})[0] == Decimal(1) / 3  # only the 'On' row starts right
    assert formats.score(fmt, body, m, {"done": True})[0] == Decimal(1) / 3


def test_build_gate_follows_the_chosen_chip_even_in_the_right_slot_count():
    result = score_of("inv-build", {"filled": {0: 1, 1: 3, 2: 6}})  # chip 1 is the gate chip
    assert result == (Decimal(2) / 3, True)


def test_match_ignores_decoys_and_crossword_scores_whole_words():
    assert score_of("inv-match", {"links": {0: 0, 1: 1, 2: 2, 3: 3}})[0] == 1
    assert score_of("inv-match", {"links": {0: 4, 1: 5, 2: 2, 3: 3}})[0] == Decimal(1) / 2
    assert (
        score_of("inv-crossword", {"letters": {"0,0": "S", "0,1": "A", "0,2": "F", "0,3": "E"}})[0]
        == Decimal(1) / 3
    )


def test_scores_are_decimals_never_floats():
    for case_id in IDS:
        fmt, body, m = build(case_id)
        score, gate = formats.score(fmt, body, m, None)
        assert isinstance(score, Decimal) and gate in (True, False)
        # nothing answered scores 0, except where leaving things alone is partly right: untouched
        # settings rows are checked at their starting value, and an unticked free "tick the right
        # ones" question gets credit for the items it correctly left unticked (legacy rule).
        expected = {"inv-settings": Decimal(1) / 3, "inv-pick-free": Decimal(1) / 2}.get(case_id, 0)
        assert score == expected, case_id


# --- schemas -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", IDS)
def test_every_invented_question_validates_and_has_a_hint_to_publish(case_id):
    fmt, body = invented_body(case_id, image_id=1)
    assert schemas.publish_errors(fmt, body) == []


@pytest.mark.parametrize(
    ("fmt", "change"),
    [
        ("mc", {"correct": 9}),
        ("mc", {"options": [{"text": "A", "tone": "red", "gate": False}, {"text": "B", "tone": "red", "gate": False}]}),
        ("cards", {"items": [{"text": "x", "answer": 9, "why": "", "gate": False}]}),
        ("spot", {"segments": [{"text": "plain", "tappable": False, "risky": False}]}),
        ("sort", {"items": [{"text": "x", "bin": 9, "why": "", "gate": False}]}),
        ("pick", {"need": 1}),
        ("build", {"slots": [{"label": "s", "answer": [99], "chips": None}]}),
        ("chat", {"steps": [{"say": "x", "replies": [{"text": "a", "score": 1, "why": "", "gate": False}, {"text": "b", "score": 0, "why": "", "gate": False}]}]}),
        ("crossword", {"words": [{"answer": "AB", "row": 0, "col": 0, "dir": "A", "clue": "c", "why": ""}, {"answer": "XB", "row": 0, "col": 0, "dir": "D", "clue": "c", "why": ""}]}),
    ],
)  # fmt: skip
def test_bad_bodies_are_refused(fmt, change):
    case = {
        "mc": "inv-mc",
        "cards": "inv-cards",
        "spot": "inv-spot-gate",
        "sort": "inv-sort",
        "pick": "inv-pick-need",
        "build": "inv-build",
        "chat": "inv-chat",
        "crossword": "inv-crossword",
    }[fmt]
    _, body = invented_body(case)
    with pytest.raises(schemas.ValidationError):
        schemas.parse_body(fmt, {**body, **change})


def test_the_correct_option_cannot_be_a_gate_option_and_extra_fields_are_refused():
    _, body = invented_body("inv-mc")
    body["options"][body["correct"]]["gate"] = True
    with pytest.raises(schemas.ValidationError):
        schemas.parse_body("mc", body)
    _, body = invented_body("inv-mc")
    with pytest.raises(schemas.ValidationError):
        schemas.parse_body("mc", {**body, "svg": "<svg/>"})


def test_gate_choices_need_a_reason_to_go_live():
    fmt, body = invented_body("inv-cards")
    body["gate_message"] = ""
    assert any("gate_message" in e for e in schemas.publish_errors(fmt, body))
    fmt, body = invented_body("inv-hotspot")
    assert any("image_id" in e for e in schemas.publish_errors(fmt, body))
