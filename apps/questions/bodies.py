"""Body schemas for the 13 interactive formats (architecture §6, §9.2).

Each body is the server's record and holds the answer data. Internal references (an item's bin, a
slot's right chip, a risky segment) are plain positions in these lists. That is fine here, because
the body never leaves the server: the browser only ever sees per-attempt random tokens
(apps/questions/formats.py). All text is plain text: the legacy importer strips markup, and
templates and renderers only ever insert it as text, never as HTML.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import SCHEMAS, _plain

Text = Field(min_length=1, max_length=600)
Tone = Literal["red", "amber", "yellow", "green"] | None


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    ask: str = Field(default="", max_length=800)  # the instruction shown above the question
    scene: str = Field(default="", max_length=1500)  # a plain-text scene or message shown first
    hint: str = Field(default="", max_length=1500)  # shown after submitting; never the answer (D13)
    why: str = Field(default="", max_length=3000)  # the worked explanation: practice only (D13)
    gate_message: str = Field(default="", max_length=800)  # why a gate choice endangers a citizen

    _clean = field_validator("title", "ask", "scene", "hint", "why", "gate_message")(_plain)


def _texts(*names):
    return field_validator(*names)(_plain)


# --- mc: one choice, with optional colour-triage tones -------------------------------------


class MCOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    tone: Tone = None  # red / amber / yellow / green: the colour-triage buttons
    gate: bool = False
    _clean = _texts("text")


class MCBody(Base):
    options: list[MCOption] = Field(min_length=2, max_length=6)
    correct: int
    keep_order: bool = False

    @model_validator(mode="after")
    def _check(self):
        if not 0 <= self.correct < len(self.options):
            raise ValueError("exactly one option must be correct: the key is out of range")
        if self.options[self.correct].gate:
            raise ValueError("the correct option cannot be a safety-gate option")
        tones = [o.tone for o in self.options]
        if any(tones) and (not all(tones) or len(set(tones)) != len(tones)):
            raise ValueError("colour triage needs every option to have a different tone")
        return self


# --- cards: one verdict per card -----------------------------------------------------------


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    tone: Tone = None
    _clean = _texts("text")


class CardItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    answer: int  # index into labels
    why: str = Field(default="", max_length=1500)
    gate: bool = False
    _clean = _texts("text", "why")


class CardsBody(Base):
    labels: list[Label] = Field(min_length=2, max_length=4)
    items: list[CardItem] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _check(self):
        if any(not 0 <= i.answer < len(self.labels) for i in self.items):
            raise ValueError("a card's answer must be one of the labels")
        return self


# --- spot: tap the risky phrases in a message ----------------------------------------------


class Segment(BaseModel):
    """A piece of the message. Spaces matter here, so the text is kept as written."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=800)
    tappable: bool = False
    risky: bool = False  # server only

    @model_validator(mode="after")
    def _check(self):
        if self.risky and not self.tappable:
            raise ValueError("a risky segment must be tappable")
        return self


class SpotBody(Base):
    segments: list[Segment] = Field(min_length=1, max_length=200)
    style: str = Field(default="", max_length=20)
    redact: bool = False
    show_count: bool = False
    gate_if_missed: str = Field(default="", max_length=800)

    @model_validator(mode="after")
    def _check(self):
        if not any(s.risky for s in self.segments):
            raise ValueError("at least one segment must be risky")
        return self


# --- hotspot: tap regions of an uploaded image ---------------------------------------------


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Text
    shape: Literal["rect", "circle", "poly"]
    coords: list[float] = Field(min_length=3, max_length=40)  # percent of the image, 0 to 100
    ok: bool = False
    why: str = Field(default="", max_length=1500)
    gate: bool = False
    _clean = _texts("label", "why")

    @model_validator(mode="after")
    def _check(self):
        n = len(self.coords)
        if any(not 0 <= c <= 100 for c in self.coords):
            raise ValueError("region coordinates are percentages from 0 to 100")
        if self.shape == "rect" and n != 4:
            raise ValueError("a rect needs x, y, width, height")
        if self.shape == "circle" and n != 3:
            raise ValueError("a circle needs cx, cy, r")
        if self.shape == "poly" and (n < 6 or n % 2):
            raise ValueError("a polygon needs at least three x, y pairs")
        return self


class HotspotBody(Base):
    image_id: int | None = None  # a QuestionImage; None until the picture is uploaded (draft)
    image_alt: str = Field(default="", max_length=400)
    legend: str = Field(default="", max_length=600)
    regions: list[Region] = Field(min_length=1, max_length=30)
    _clean2 = _texts("image_alt", "legend")

    @model_validator(mode="after")
    def _check(self):
        if not any(r.ok for r in self.regions):
            raise ValueError("at least one region must be a correct one")
        return self


# --- sort / match / order / pick / build ---------------------------------------------------


class SortItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    bin: int
    why: str = Field(default="", max_length=1500)
    gate: bool = False
    _clean = _texts("text", "why")


class SortBody(Base):
    bins: list[Label] = Field(min_length=2, max_length=6)
    items: list[SortItem] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _check(self):
        if any(not 0 <= i.bin < len(self.bins) for i in self.items):
            raise ValueError("an item's bin must be one of the bins")
        return self


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: str = Text
    right: str = Text
    why: str = Field(default="", max_length=1500)
    _clean = _texts("left", "right", "why")


class MatchBody(Base):
    pairs: list[Pair] = Field(min_length=2, max_length=12)
    extra: list[str] = Field(default_factory=list, max_length=6)  # decoy right-hand items
    left_label: str = Field(default="", max_length=60)
    right_label: str = Field(default="", max_length=60)
    _clean2 = _texts("left_label", "right_label")

    @field_validator("extra")
    @classmethod
    def _extra(cls, value):
        return [_plain(v) for v in value]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    why: str = Field(default="", max_length=1500)
    _clean = _texts("text", "why")


class OrderBody(Base):
    items: list[Step] = Field(min_length=2, max_length=12)  # in the CORRECT order


class PickItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    ok: bool = False
    why: str = Field(default="", max_length=1500)
    gate: bool = False
    _clean = _texts("text", "why")


class PickBody(Base):
    items: list[PickItem] = Field(min_length=2, max_length=30)
    need: int = 0
    check_label: str = Field(default="", max_length=60)

    @model_validator(mode="after")
    def _check(self):
        good = sum(1 for i in self.items if i.ok)
        if not good:
            raise ValueError("at least one item must be a correct pick")
        if self.need and self.need != good:
            raise ValueError("need must equal the number of correct items")
        return self


class Chip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    gate: bool = False
    _clean = _texts("text")


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Text
    answer: list[int] = Field(min_length=1)  # chips that are right here (the key)
    chips: list[int] | None = None  # chips offered for this slot (None: all)
    _clean = _texts("label")


class BuildBody(Base):
    chips: list[Chip] = Field(min_length=2, max_length=30)
    slots: list[Slot] = Field(min_length=1, max_length=12)
    scene_label: str = Field(default="", max_length=60)

    @model_validator(mode="after")
    def _check(self):
        n = len(self.chips)
        for slot in self.slots:
            if any(not 0 <= c < n for c in slot.answer + (slot.chips or [])):
                raise ValueError("a slot refers to a chip that does not exist")
            if slot.chips is not None and not set(slot.answer) <= set(slot.chips):
                raise ValueError("a slot's right chip must be among the chips offered for it")
        return self


# --- settings / dial -----------------------------------------------------------------------


class SettingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    kind: Literal["switch", "choice"] = "choice"
    options: list[str] = Field(default_factory=list, max_length=6)  # for kind=choice
    start: int  # the starting option index, or 0/1 for a switch (0 = off)
    want: list[int] = Field(min_length=1)  # right values (the key)
    why: str = Field(default="", max_length=1500)
    _clean = _texts("text", "why")

    @field_validator("options")
    @classmethod
    def _options(cls, value):
        return [_plain(v) for v in value]

    @model_validator(mode="after")
    def _check(self):
        n = 2 if self.kind == "switch" else len(self.options)
        if self.kind == "choice" and n < 2:
            raise ValueError("a choice row needs at least two options")
        if not 0 <= self.start < n or any(not 0 <= w < n for w in self.want):
            raise ValueError("start and want must be valid option positions")
        return self


class SettingsBody(Base):
    rows: list[SettingRow] = Field(min_length=1, max_length=12)
    device: str = Field(default="", max_length=60)
    screen: str = Field(default="", max_length=80)
    check_label: str = Field(default="", max_length=60)


class DialRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Text
    kind: Literal["time", "number"] = "number"
    unit: str = Field(default="", max_length=20)
    start: int
    min: int | None = None
    max: int | None = None
    steps: list[int] | None = None
    answer: int  # the key
    tol: int = 0
    why: str = Field(default="", max_length=1500)
    _clean = _texts("label", "unit", "why")

    @model_validator(mode="after")
    def _check(self):
        if self.steps is not None and (not self.steps or any(s == 0 for s in self.steps)):
            raise ValueError("steps must be non-zero numbers")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min is above max")
        return self

    def step_list(self) -> list[int]:
        return self.steps or ([-60, -10, -5, 5, 10, 60] if self.kind == "time" else [-1, 1])


class DialBody(Base):
    rows: list[DialRow] = Field(min_length=1, max_length=8)


# --- chat ----------------------------------------------------------------------------------


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Text
    score: Literal[0, 1, 2]
    why: str = Field(default="", max_length=1500)
    gate: bool = False
    _clean = _texts("text", "why")


class ChatStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    say: str = Text
    replies: list[Reply] = Field(min_length=2, max_length=6)
    _clean = _texts("say")

    @model_validator(mode="after")
    def _check(self):
        if not any(r.score == 2 for r in self.replies):
            raise ValueError("each step needs a best reply (score 2)")
        return self


class ChatBody(Base):
    who: str = Field(min_length=1, max_length=60)
    steps: list[ChatStep] = Field(min_length=1, max_length=10)
    _clean2 = _texts("who")


# --- crossword (practice only) -------------------------------------------------------------


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=2, max_length=30)  # the key
    row: int = Field(ge=0, le=30)
    col: int = Field(ge=0, le=30)
    dir: Literal["A", "D"]
    clue: str = Text
    why: str = Field(default="", max_length=1500)
    _clean = _texts("clue", "why")

    @field_validator("answer")
    @classmethod
    def _answer(cls, value):
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("an answer is letters only")
        return value


class CrosswordBody(Base):
    words: list[Word] = Field(min_length=2, max_length=20)
    scene_label: str = Field(default="", max_length=60)

    @model_validator(mode="after")
    def _check(self):
        cells: dict[tuple[int, int], str] = {}
        for word in self.words:
            for i, letter in enumerate(word.answer):
                at = (
                    word.row + (i if word.dir == "D" else 0),
                    word.col + (i if word.dir == "A" else 0),
                )
                if cells.setdefault(at, letter) != letter:
                    raise ValueError("two words disagree about a shared letter")
        return self


SCHEMAS.update(
    {
        "mc": MCBody,
        "cards": CardsBody,
        "spot": SpotBody,
        "hotspot": HotspotBody,
        "sort": SortBody,
        "match": MatchBody,
        "order": OrderBody,
        "pick": PickBody,
        "build": BuildBody,
        "settings": SettingsBody,
        "dial": DialBody,
        "chat": ChatBody,
        "crossword": CrosswordBody,
    }
)
