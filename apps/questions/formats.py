"""The question formats: tokens, safe browser payloads, response checks and scorers.

For every question in an attempt, `make_map()` creates the **option map**: random, per-attempt
tokens for each choice, item, bin, slot, cell, region and reply, plus the order each list is shown
in. The map stays on the server (AttemptItem.option_map). `project()` builds what the browser
may receive from an allow-list: text and tokens only, never a key, a risky flag, a canonical order
or a score rule. `clean_response()` accepts only tokens that belong to this item. `score()` runs
on the server from the frozen question version.

MCQ keeps its Stage 2 shapes. The 13 interactive formats are ported from the legacy engine's
scoring (docs/legacy-sources.md); parity is tested against frozen outputs of the real legacy
engine (tests/test_scorer_parity.py).
"""

import random
import secrets
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")
TONE_RANK = {"red": 0, "amber": 1, "yellow": 2, "green": 3}
MAX_RESPONSE_ITEMS = 200


class ResponseError(ValueError):
    """The browser sent something that doesn't belong to this question."""


def ratio(num: int, den: int) -> Decimal:
    """An exact-as-possible fraction as a Decimal (never a float)."""
    return Decimal(num) / Decimal(den) if den else ZERO


def clamp01(value: Decimal) -> Decimal:
    return max(ZERO, min(ONE, value))


# --- tokens --------------------------------------------------------------------------------


class Mapper:
    """Builds an option map: random tokens per table, and the display order of each table."""

    def __init__(self, rng=None):
        self.rng = rng or random.SystemRandom()
        self.refs: dict[str, list] = {}
        self.lists: dict[str, list[str]] = {}

    def _new(self) -> str:
        token = secrets.token_urlsafe(9)
        while token in self.refs:
            token = secrets.token_urlsafe(9)
        return token

    def table(self, name, count, *, shuffle=True, avoid_identity=False) -> list[str]:
        """Create `count` tokens for `name`. Returns them index-aligned with the body's list."""
        tokens = [self._new() for _ in range(count)]
        for index, token in enumerate(tokens):
            self.refs[token] = [name, index]
        shown = list(tokens)
        if shuffle:
            self.rng.shuffle(shown)
            guard = 0
            while avoid_identity and count > 1 and shown == tokens and guard < 20:
                self.rng.shuffle(shown)
                guard += 1
        self.lists[name] = shown
        return tokens

    def result(self) -> dict:
        return {"v": 2, "refs": self.refs, "lists": self.lists}


def by_index(option_map: dict, table: str) -> list[str]:
    """The tokens of `table`, index-aligned with the body's list."""
    found = {ref[1]: token for token, ref in option_map["refs"].items() if ref[0] == table}
    return [found[i] for i in range(len(found))]


def ref_index(option_map: dict, token, table: str) -> int | None:
    ref = option_map["refs"].get(token) if isinstance(token, str) else None
    return ref[1] if ref and ref[0] == table else None


def _need_token(option_map, token, table) -> int:
    index = ref_index(option_map, token, table)
    if index is None:
        raise ResponseError("That is not part of this question.")
    return index


def _need_dict(value, name):
    if not isinstance(value, dict) or len(value) > MAX_RESPONSE_ITEMS:
        raise ResponseError(f"{name} must be an object.")
    return value


def _need_list(value, name):
    if not isinstance(value, list) or len(value) > MAX_RESPONSE_ITEMS:
        raise ResponseError(f"{name} must be a list.")
    return value


def _flag(response, key="done") -> bool:
    return bool(response.get(key)) if isinstance(response, dict) else False


# --- the formats ---------------------------------------------------------------------------


class Format:
    name = ""

    def make_map(self, body: dict, rng=None) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def project(self, body: dict, m: dict, response: dict | None) -> dict:  # pragma: no cover
        raise NotImplementedError

    def clean_response(self, body: dict, m: dict, response: dict) -> dict:  # pragma: no cover
        raise NotImplementedError

    def score(self, body: dict, m: dict, response: dict | None) -> tuple[Decimal, bool]:
        raise NotImplementedError  # pragma: no cover

    def complete(self, body: dict, m: dict, response: dict | None) -> bool:
        raise NotImplementedError  # pragma: no cover

    # the fields every projection carries; nothing here is an answer
    def head(self, body: dict, response) -> dict:
        return {
            "format": self.name,
            "title": body.get("title", ""),
            "ask": body.get("ask", ""),
            "scene": body.get("scene", ""),
            "response": {k: v for k, v in (response or {}).items() if k != "flag"},
        }

    def done_flag(self, response):
        return _flag(response)


class MCQ(Format):
    """Stage 2 multiple choice: body options have internal ids; the map is {order, tokens}."""

    name = "mcq"

    def make_map(self, body, rng=None):
        rng = rng or random.SystemRandom()
        keys = [o["id"] for o in body["options"]]
        rng.shuffle(keys)
        tokens, order = {}, []
        for key in keys:
            token = secrets.token_urlsafe(9)
            while token in tokens:
                token = secrets.token_urlsafe(9)
            tokens[token] = key
            order.append(token)
        return {"order": order, "tokens": tokens}

    def project(self, body, m, response):
        text = {o["id"]: o["text"] for o in body["options"]}
        return {
            "format": "mcq",
            "stem": body["stem"],
            "options": [{"token": t, "text": text[m["tokens"][t]]} for t in m["order"]],
        }

    def clean_response(self, body, m, response):
        token = response.get("choice") if isinstance(response, dict) else None
        if token not in m["tokens"]:
            raise ResponseError("That is not one of the options.")
        return {"choice": token}

    def score(self, body, m, response):
        token = (response or {}).get("choice")
        key = m["tokens"].get(token) if token else None
        if key is None:
            return ZERO, False
        return (ONE if key == body["correct"] else ZERO), key in body.get("gate", {})

    def complete(self, body, m, response):
        return bool((response or {}).get("choice"))


class MC(Format):
    name = "mc"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        tokens = mapper.table("options", len(body["options"]), shuffle=not body["keep_order"])
        if any(o.get("tone") for o in body["options"]):  # colour triage: fixed colour order
            ranked = sorted(range(len(tokens)), key=lambda i: TONE_RANK[body["options"][i]["tone"]])
            mapper.lists["options"] = [tokens[i] for i in ranked]
        return mapper.result()

    def project(self, body, m, response):
        tokens = by_index(m, "options")
        out = self.head(body, response)
        out["options"] = [
            {"token": t, "text": body["options"][tokens.index(t)]["text"],
             "tone": body["options"][tokens.index(t)].get("tone")}
            for t in m["lists"]["options"]
        ]  # fmt: skip
        out["triage"] = any(o.get("tone") for o in body["options"])
        return out

    def clean_response(self, body, m, response):
        _need_token(m, (response or {}).get("choice"), "options")
        return {"choice": response["choice"]}

    def score(self, body, m, response):
        index = ref_index(m, (response or {}).get("choice"), "options")
        if index is None:
            return ZERO, False
        return (ONE if index == body["correct"] else ZERO), bool(body["options"][index].get("gate"))

    def complete(self, body, m, response):
        return ref_index(m, (response or {}).get("choice"), "options") is not None


class Cards(Format):
    name = "cards"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("labels", len(body["labels"]), shuffle=False)
        mapper.table("items", len(body["items"]))
        return mapper.result()

    def project(self, body, m, response):
        labels, items = by_index(m, "labels"), by_index(m, "items")
        out = self.head(body, response)
        out["labels"] = [
            {"token": labels[i], "text": lab["text"], "tone": lab.get("tone")}
            for i, lab in enumerate(body["labels"])
        ]
        out["items"] = [
            {"token": t, "text": body["items"][items.index(t)]["text"]} for t in m["lists"]["items"]
        ]
        return out

    def clean_response(self, body, m, response):
        answers = _need_dict((response or {}).get("answers", {}), "answers")
        clean = {}
        for item_token, label_token in answers.items():
            _need_token(m, item_token, "items")
            _need_token(m, label_token, "labels")
            clean[item_token] = label_token
        return {"answers": clean}

    def score(self, body, m, response):
        answers = (response or {}).get("answers", {})
        right, gate = 0, False
        for i, item in enumerate(body["items"]):
            chosen = ref_index(m, answers.get(by_index(m, "items")[i]), "labels")
            if chosen == item["answer"]:
                right += 1
            elif chosen is not None and item.get("gate"):  # a wrong verdict, not a blank one
                gate = True
        return ratio(right, len(body["items"])), gate

    def complete(self, body, m, response):
        return len((response or {}).get("answers", {})) == len(body["items"])


class Spot(Format):
    name = "spot"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("segments", sum(1 for s in body["segments"] if s["tappable"]), shuffle=False)
        return mapper.result()

    def _tappable(self, body):
        return [s for s in body["segments"] if s["tappable"]]

    def project(self, body, m, response):
        tokens = iter(by_index(m, "segments"))
        out = self.head(body, response)
        out["segments"] = [
            {"text": s["text"], "token": next(tokens) if s["tappable"] else None}
            for s in body["segments"]
        ]  # which segments are risky is not in here
        out["style"] = body.get("style", "")
        out["redact"] = bool(body.get("redact"))
        if body.get("show_count"):
            out["look_for"] = sum(1 for s in body["segments"] if s["risky"])
        return out

    def clean_response(self, body, m, response):
        picked = _need_list((response or {}).get("picked", []), "picked")
        for token in picked:
            _need_token(m, token, "segments")
        return {"picked": list(dict.fromkeys(picked)), "done": _flag(response)}

    def score(self, body, m, response):
        picked = {ref_index(m, t, "segments") for t in (response or {}).get("picked", [])} - {None}
        flags = hit = fal = 0
        for index, seg in enumerate(self._tappable(body)):
            on = index in picked
            if seg["risky"]:
                flags += 1
                hit += on
            else:
                fal += on
        # Missing a risky part is a gate only once the learner has said they are done (the legacy
        # engine checked on "Check"): leaving a question blank endangers no one.
        gate = bool(body.get("gate_if_missed")) and hit < flags and _flag(response)
        return clamp01(ratio(max(0, hit - fal), flags)), gate

    def complete(self, body, m, response):
        return _flag(response)


class Hotspot(Format):
    name = "hotspot"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("regions", len(body["regions"]))
        return mapper.result()

    def project(self, body, m, response):
        tokens = by_index(m, "regions")
        out = self.head(body, response)
        out["image"] = {
            "alt": body.get("image_alt", ""),
            "available": body.get("image_id") is not None,
        }
        out["legend"] = body.get("legend", "")
        out["regions"] = [
            {
                "token": t,
                "label": body["regions"][tokens.index(t)]["label"],
                "shape": body["regions"][tokens.index(t)]["shape"],
                "coords": body["regions"][tokens.index(t)]["coords"],
            }
            for t in m["lists"]["regions"]
        ]
        return out

    def clean_response(self, body, m, response):
        picked = _need_list((response or {}).get("picked", []), "picked")
        for token in picked:
            _need_token(m, token, "regions")
        return {"picked": list(dict.fromkeys(picked)), "done": _flag(response)}

    def score(self, body, m, response):
        picked = {ref_index(m, t, "regions") for t in (response or {}).get("picked", [])} - {None}
        need = hit = fal = 0
        gate = False
        for index, region in enumerate(body["regions"]):
            on = index in picked
            if region["ok"]:
                need += 1
                hit += on
            elif on:
                fal += 1
                gate = gate or bool(region.get("gate"))
        return clamp01(ratio(max(0, hit - fal), need)), gate

    def complete(self, body, m, response):
        return _flag(response)


class Sort(Format):
    name = "sort"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("bins", len(body["bins"]), shuffle=False)
        mapper.table("items", len(body["items"]))
        return mapper.result()

    def project(self, body, m, response):
        bins, items = by_index(m, "bins"), by_index(m, "items")
        out = self.head(body, response)
        out["bins"] = [
            {"token": bins[i], "text": b["text"], "tone": b.get("tone")}
            for i, b in enumerate(body["bins"])
        ]
        out["items"] = [
            {"token": t, "text": body["items"][items.index(t)]["text"]} for t in m["lists"]["items"]
        ]
        return out

    def clean_response(self, body, m, response):
        placed = _need_dict((response or {}).get("placed", {}), "placed")
        for item_token, bin_token in placed.items():
            _need_token(m, item_token, "items")
            _need_token(m, bin_token, "bins")
        return {"placed": dict(placed)}

    def score(self, body, m, response):
        placed = (response or {}).get("placed", {})
        items = by_index(m, "items")
        right, gate = 0, False
        for i, item in enumerate(body["items"]):
            put = ref_index(m, placed.get(items[i]), "bins")
            if put == item["bin"]:
                right += 1
            elif put is not None and item.get("gate"):  # placed wrongly, not left unplaced
                gate = True
        return ratio(right, len(body["items"])), gate

    def complete(self, body, m, response):
        return len((response or {}).get("placed", {})) == len(body["items"])


class Match(Format):
    name = "match"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("lefts", len(body["pairs"]))
        mapper.table("rights", len(body["pairs"]) + len(body.get("extra", [])))
        return mapper.result()

    def project(self, body, m, response):
        lefts, rights = by_index(m, "lefts"), by_index(m, "rights")
        texts = [p["right"] for p in body["pairs"]] + list(body.get("extra", []))
        out = self.head(body, response)
        out["left_label"] = body.get("left_label", "")
        out["right_label"] = body.get("right_label", "")
        out["lefts"] = [
            {"token": t, "text": body["pairs"][lefts.index(t)]["left"]} for t in m["lists"]["lefts"]
        ]
        out["rights"] = [{"token": t, "text": texts[rights.index(t)]} for t in m["lists"]["rights"]]
        return out

    def clean_response(self, body, m, response):
        links = _need_dict((response or {}).get("links", {}), "links")
        for left, right in links.items():
            _need_token(m, left, "lefts")
            _need_token(m, right, "rights")
        if len(set(links.values())) != len(links):
            raise ResponseError("Each item on the right can be used once.")
        return {"links": dict(links)}

    def score(self, body, m, response):
        links = (response or {}).get("links", {})
        lefts = by_index(m, "lefts")
        right = sum(
            1 for i in range(len(body["pairs"])) if ref_index(m, links.get(lefts[i]), "rights") == i
        )
        return ratio(right, len(body["pairs"])), False

    def complete(self, body, m, response):
        return len((response or {}).get("links", {})) == len(body["pairs"])


class Order(Format):
    name = "order"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("items", len(body["items"]), avoid_identity=True)
        return mapper.result()

    def project(self, body, m, response):
        items = by_index(m, "items")
        out = self.head(body, response)
        out["items"] = [
            {"token": t, "text": body["items"][items.index(t)]["text"]} for t in m["lists"]["items"]
        ]
        return out

    def clean_response(self, body, m, response):
        sequence = _need_list((response or {}).get("sequence", []), "sequence")
        for token in sequence:
            _need_token(m, token, "items")
        if len(set(sequence)) != len(sequence):
            raise ResponseError("Each step can be used once.")
        return {"sequence": list(sequence)}

    def score(self, body, m, response):
        sequence = (response or {}).get("sequence", [])
        right = sum(1 for pos, token in enumerate(sequence) if ref_index(m, token, "items") == pos)
        return ratio(right, len(body["items"])), False

    def complete(self, body, m, response):
        return len((response or {}).get("sequence", [])) == len(body["items"])


class Pick(Format):
    name = "pick"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("items", len(body["items"]))
        return mapper.result()

    def project(self, body, m, response):
        items = by_index(m, "items")
        out = self.head(body, response)
        out["items"] = [
            {"token": t, "text": body["items"][items.index(t)]["text"]} for t in m["lists"]["items"]
        ]
        out["need"] = body.get("need", 0)
        out["check_label"] = body.get("check_label", "")
        return out

    def clean_response(self, body, m, response):
        picked = _need_list((response or {}).get("picked", []), "picked")
        for token in picked:
            _need_token(m, token, "items")
        picked = list(dict.fromkeys(picked))
        if body.get("need") and len(picked) > body["need"]:
            raise ResponseError("You can pick only {need}.".format(need=body["need"]))
        return {"picked": picked, "done": _flag(response)}

    def score(self, body, m, response):
        picked = {ref_index(m, t, "items") for t in (response or {}).get("picked", [])} - {None}
        right = good = bad = 0
        gate = False
        for index, item in enumerate(body["items"]):
            on = index in picked
            if on == bool(item["ok"]):
                right += 1
            if on and item["ok"]:
                good += 1
            if on and not item["ok"]:
                bad += 1
                gate = gate or bool(item.get("gate"))
        need = body.get("need", 0)
        score = ratio(max(0, good - bad), need) if need else ratio(right, len(body["items"]))
        return clamp01(score), gate

    def complete(self, body, m, response):
        need = body.get("need", 0)
        count = len((response or {}).get("picked", []))
        return count == need if need else _flag(response)


class Build(Format):
    name = "build"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("slots", len(body["slots"]), shuffle=False)
        mapper.table("chips", len(body["chips"]))
        return mapper.result()

    def project(self, body, m, response):
        slots, chips = by_index(m, "slots"), by_index(m, "chips")
        out = self.head(body, response)
        out["scene_label"] = body.get("scene_label", "")
        out["slots"] = [
            {
                "token": slots[i],
                "label": slot["label"],
                "chips": None
                if slot.get("chips") is None
                else [chips[c] for c in slot["chips"] if c is not None],
            }
            for i, slot in enumerate(body["slots"])
        ]
        out["chips"] = [
            {"token": t, "text": body["chips"][chips.index(t)]["text"]} for t in m["lists"]["chips"]
        ]
        return out

    def clean_response(self, body, m, response):
        filled = _need_dict((response or {}).get("filled", {}), "filled")
        for slot_token, chip_token in filled.items():
            slot = _need_token(m, slot_token, "slots")
            chip = _need_token(m, chip_token, "chips")
            offered = body["slots"][slot].get("chips")
            if offered is not None and chip not in offered:
                raise ResponseError("That card is not offered for this slot.")
        if len(set(filled.values())) != len(filled):
            raise ResponseError("Each card can be used once.")
        return {"filled": dict(filled)}

    def score(self, body, m, response):
        filled = (response or {}).get("filled", {})
        slots = by_index(m, "slots")
        right, gate = 0, False
        for i, slot in enumerate(body["slots"]):
            chip = ref_index(m, filled.get(slots[i]), "chips")
            if chip is not None and chip in slot["answer"]:
                right += 1
            if chip is not None and body["chips"][chip].get("gate"):
                gate = True
        return ratio(right, len(body["slots"])), gate

    def complete(self, body, m, response):
        return len((response or {}).get("filled", {})) == len(body["slots"])


class Settings(Format):
    name = "settings"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("rows", len(body["rows"]), shuffle=False)
        for i, row in enumerate(body["rows"]):
            if row["kind"] == "choice":
                mapper.table(f"row{i}", len(row["options"]), shuffle=False)
        return mapper.result()

    def project(self, body, m, response):
        rows = by_index(m, "rows")
        out = self.head(body, response)
        out["device"] = body.get("device", "")
        out["screen"] = body.get("screen", "")
        out["check_label"] = body.get("check_label", "")
        out["rows"] = []
        for i, row in enumerate(body["rows"]):
            if row["kind"] == "switch":
                out["rows"].append(
                    {
                        "token": rows[i],
                        "text": row["text"],
                        "kind": "switch",
                        "options": [],
                        "start": row["start"],
                    }
                )
            else:
                opts = by_index(m, f"row{i}")
                out["rows"].append(
                    {
                        "token": rows[i],
                        "text": row["text"],
                        "kind": "choice",
                        "options": [
                            {"token": opts[j], "text": text}
                            for j, text in enumerate(row["options"])
                        ],
                        "start": opts[row["start"]],
                    }
                )
        return out

    def clean_response(self, body, m, response):
        values = _need_dict((response or {}).get("values", {}), "values")
        clean = {}
        for row_token, value in values.items():
            i = _need_token(m, row_token, "rows")
            if body["rows"][i]["kind"] == "switch":
                if value not in (0, 1) or isinstance(value, bool):
                    raise ResponseError("A switch is on or off.")
                clean[row_token] = value
            else:
                _need_token(m, value, f"row{i}")
                clean[row_token] = value
        return {"values": clean, "done": _flag(response)}

    def _value(self, body, m, response, i):
        row = body["rows"][i]
        raw = (response or {}).get("values", {}).get(by_index(m, "rows")[i])
        if raw is None:
            return row[
                "start"
            ]  # an untouched row is checked at its starting value, like the legacy engine
        if row["kind"] == "switch":
            return raw
        index = ref_index(m, raw, f"row{i}")
        return row["start"] if index is None else index

    def score(self, body, m, response):
        right = sum(
            1
            for i, row in enumerate(body["rows"])
            if self._value(body, m, response, i) in row["want"]
        )
        return ratio(right, len(body["rows"])), False

    def complete(self, body, m, response):
        return _flag(response)


class Dial(Format):
    name = "dial"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("rows", len(body["rows"]), shuffle=False)
        return mapper.result()

    def project(self, body, m, response):
        rows = by_index(m, "rows")
        out = self.head(body, response)
        steps = {"time": [-60, -10, -5, 5, 10, 60], "number": [-1, 1]}
        out["rows"] = [
            {
                "token": rows[i], "label": r["label"], "kind": r["kind"], "unit": r.get("unit", ""),
                "start": r["start"], "min": r.get("min"), "max": r.get("max"),
                "steps": r.get("steps") or steps[r["kind"]],
            }
            for i, r in enumerate(body["rows"])
        ]  # fmt: skip
        return out

    def clean_response(self, body, m, response):
        values = _need_dict((response or {}).get("values", {}), "values")
        clean = {}
        for row_token, value in values.items():
            i = _need_token(m, row_token, "rows")
            if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 100000:
                raise ResponseError("A dial holds a whole number.")
            row = body["rows"][i]
            if row["kind"] != "time":
                if row.get("min") is not None:
                    value = max(row["min"], value)
                if row.get("max") is not None:
                    value = min(row["max"], value)
            clean[row_token] = value
        return {"values": clean, "done": _flag(response)}

    def score(self, body, m, response):
        rows = by_index(m, "rows")
        right = 0
        for i, row in enumerate(body["rows"]):
            value = (response or {}).get("values", {}).get(rows[i], row["start"])
            answer = row["answer"]
            if row["kind"] == "time":
                value, answer = value % 1440, answer % 1440
            if abs(value - answer) <= row.get("tol", 0):
                right += 1
        return ratio(right, len(body["rows"])), False

    def complete(self, body, m, response):
        return _flag(response)


class Chat(Format):
    name = "chat"

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        for i, step in enumerate(body["steps"]):
            mapper.table(f"step{i}", len(step["replies"]))
        return mapper.result()

    def project(self, body, m, response):
        replies = (response or {}).get("replies", [])
        out = self.head(body, response)
        out["who"] = body["who"]
        out["total_steps"] = len(body["steps"])
        shown = []
        for i, step in enumerate(body["steps"][: len(replies) + 1]):
            tokens = by_index(m, f"step{i}")
            if i < len(replies):  # answered: show the line and what they said, nothing about it
                chosen = ref_index(m, replies[i], f"step{i}")
                shown.append(
                    {
                        "say": step["say"],
                        "chosen": replies[i],
                        "text": step["replies"][chosen]["text"],
                    }
                )
            else:  # the current step: its replies, as tokens (later steps are not sent yet)
                shown.append(
                    {
                        "say": step["say"],
                        "replies": [
                            {"token": t, "text": step["replies"][tokens.index(t)]["text"]}
                            for t in m["lists"][f"step{i}"]
                        ],
                    }
                )
        out["steps"] = shown
        return out

    def clean_response(self, body, m, response):
        replies = _need_list((response or {}).get("replies", []), "replies")
        if len(replies) > len(body["steps"]):
            raise ResponseError("There are not that many steps.")
        for i, token in enumerate(replies):
            _need_token(m, token, f"step{i}")
        return {"replies": list(replies)}

    def score(self, body, m, response):
        replies = (response or {}).get("replies", [])
        points, gate = 0, False
        for i, token in enumerate(replies[: len(body["steps"])]):
            index = ref_index(m, token, f"step{i}")
            if index is not None:
                reply = body["steps"][i]["replies"][index]
                points += reply["score"]
                gate = gate or bool(reply.get("gate"))
        return ratio(points, 2 * len(body["steps"])), gate

    def complete(self, body, m, response):
        return len((response or {}).get("replies", [])) == len(body["steps"])


class Crossword(Format):
    name = "crossword"

    @staticmethod
    def cells(body):
        found = {}
        for word in body["words"]:
            for i, letter in enumerate(word["answer"]):
                at = (
                    word["row"] + (i if word["dir"] == "D" else 0),
                    word["col"] + (i if word["dir"] == "A" else 0),
                )
                found.setdefault(at, letter)
        return sorted(found)  # reading order

    def make_map(self, body, rng=None):
        mapper = Mapper(rng)
        mapper.table("cells", len(self.cells(body)), shuffle=False)
        return mapper.result()

    def project(self, body, m, response):
        positions = self.cells(body)
        tokens = by_index(m, "cells")
        token_at = dict(zip(positions, tokens, strict=True))
        starts = sorted({(w["row"], w["col"]) for w in body["words"]})
        number = {at: n for n, at in enumerate(starts, start=1)}
        words = []
        for w in body["words"]:
            cells = [
                token_at[
                    (
                        w["row"] + (i if w["dir"] == "D" else 0),
                        w["col"] + (i if w["dir"] == "A" else 0),
                    )
                ]
                for i in range(len(w["answer"]))
            ]
            words.append(
                {
                    "number": number[(w["row"], w["col"])],
                    "dir": w["dir"],
                    "clue": w["clue"],
                    "length": len(cells),
                    "cells": cells,
                }
            )
        words.sort(key=lambda w: (w["dir"] != "A", w["number"]))
        out = self.head(body, response)
        out["rows"] = max(r for r, _ in positions) + 1
        out["cols"] = max(c for _, c in positions) + 1
        out["cells"] = [{"token": token_at[at], "row": at[0], "col": at[1]} for at in positions]
        out["words"] = words
        return out

    def clean_response(self, body, m, response):
        letters = _need_dict((response or {}).get("letters", {}), "letters")
        clean = {}
        for token, letter in letters.items():
            _need_token(m, token, "cells")
            if not isinstance(letter, str) or len(letter) != 1 or not letter.isalpha():
                raise ResponseError("A cell holds one letter.")
            clean[token] = letter.upper()
        return {"letters": clean}

    def score(self, body, m, response):
        letters = (response or {}).get("letters", {})
        token_at = dict(zip(self.cells(body), by_index(m, "cells"), strict=True))
        right = 0
        for w in body["words"]:
            ok = all(
                letters.get(
                    token_at[
                        (
                            w["row"] + (i if w["dir"] == "D" else 0),
                            w["col"] + (i if w["dir"] == "A" else 0),
                        )
                    ]
                )
                == ch
                for i, ch in enumerate(w["answer"])
            )
            right += ok
        return ratio(right, len(body["words"])), False

    def complete(self, body, m, response):
        return len((response or {}).get("letters", {})) == len(self.cells(body))


FORMATS = {
    f.name: f
    for f in (
        MCQ(), MC(), Cards(), Spot(), Hotspot(), Sort(), Match(), Order(), Pick(), Build(),
        Settings(), Dial(), Chat(), Crossword(),
    )
}  # fmt: skip


def get(fmt: str) -> Format:
    try:
        return FORMATS[fmt]
    except KeyError:
        raise ValueError(f"Unknown format {fmt!r}") from None


def label(body: dict) -> str:
    """The short line that names a question on the review and result pages (plain text)."""
    return (
        body.get("stem") or body.get("title") or body.get("ask") or body.get("scene") or "Question"
    )


def make_option_map(body: dict, rng=None) -> dict:
    """MCQ's option map (kept under its Stage 2 name)."""
    return FORMATS["mcq"].make_map(body, rng)


def make_map(fmt, body, rng=None):
    return get(fmt).make_map(body, rng)


def project(fmt, body, m, response=None):
    return get(fmt).project(body, m, response)


def clean_response(fmt, body, m, response):
    return get(fmt).clean_response(body, m, response)


def score(fmt, body, m, response):
    return get(fmt).score(body, m, response)


def complete(fmt, body, m, response):
    return get(fmt).complete(body, m, response)
