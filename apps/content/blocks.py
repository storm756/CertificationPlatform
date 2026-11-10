"""Block schemas for unit text (architecture §13.1). Plain text only: no HTML is ever stored.

Every block has a `type`. Templates in templates/learn/blocks/ draw them and escape all text. Links
are http/https only. The inline interactions (reveal, mythfact, check) keep their answer on the
server: the page shows the prompt, and the answer arrives only after the learner commits
(apps/content/views.py). Flip cards hold reference text (rules, helplines), not answers.
"""

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from apps.questions.schemas import _plain

Short = Field(min_length=1, max_length=300)
Text = Field(min_length=1, max_length=4000)


def _clean(*names):
    return field_validator(*names)(_plain)


def _clean_list(values: list[str]) -> list[str]:
    return [_plain(v) for v in values]


class B(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- text ------------------------------------------------------------------------------------


class Heading(B):
    type: Literal["heading"]
    text: str = Short
    level: Literal[2, 3] = 2
    _c = _clean("text")


class Span(B):
    text: str = Field(min_length=1, max_length=4000)
    bold: bool = False
    italic: bool = False
    href: str = ""

    @field_validator("text")
    @classmethod
    def _text(cls, v):
        if _plain(v) == "":
            raise ValueError("empty text")
        return v.replace("\x00", "")

    @field_validator("href")
    @classmethod
    def _href(cls, v):
        if not v:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("links must be http or https")
        return v


class Paragraph(B):
    type: Literal["paragraph"]
    spans: list[Span] = Field(min_length=1, max_length=200)


class ListBlock(B):
    type: Literal["list"]
    items: list[str] = Field(min_length=1, max_length=60)
    ordered: bool = False
    _c = field_validator("items")(_clean_list)


class Pairs(B):
    """Label → value rows (the booklet's 'kv' blocks)."""

    type: Literal["pairs"]
    rows: list[tuple[str, str]] = Field(min_length=1, max_length=60)

    @field_validator("rows")
    @classmethod
    def _rows(cls, rows):
        return [(_plain(k), _plain(v)) for k, v in rows]


class Table(B):
    type: Literal["table"]
    caption: str = Field(default="", max_length=300)
    head: list[str] = Field(default_factory=list, max_length=12)
    rows: list[list[str]] = Field(min_length=1, max_length=120)
    being_fixed: bool = False  # a jumbled legacy table: shown with a "table being fixed" notice

    @field_validator("head")
    @classmethod
    def _head(cls, v):
        return _clean_list(v)

    @field_validator("rows")
    @classmethod
    def _rows(cls, rows):
        return [_clean_list(r) for r in rows]


class Card(B):
    label: str = Field(default="", max_length=120)
    title: str = Short
    text: str = Text
    _c = _clean("label", "title", "text")


class Cards(B):
    type: Literal["cards"]
    heading: str = Field(default="", max_length=300)
    cards: list[Card] = Field(min_length=1, max_length=20)
    _c = _clean("heading")


class Signs(B):
    type: Literal["signs"]
    heading: str = Field(default="", max_length=300)
    items: list[str] = Field(min_length=1, max_length=30)
    _c = _clean("heading")
    _i = field_validator("items")(_clean_list)


class UrgencyRow(B):
    colour: Literal["red", "amber", "yellow", "green"]
    label: str = Short
    level: str = Short
    when: str = Text
    action: str = Text
    time: str = Short
    _c = _clean("label", "level", "when", "action", "time")


class Urgency(B):
    type: Literal["urgency"]
    heading: str = Field(default="", max_length=300)
    rows: list[UrgencyRow] = Field(min_length=1, max_length=8)
    _c = _clean("heading")


class Callout(B):
    """A labelled note: key rule, think aloud, what good looks like, discuss, self-check."""

    type: Literal["callout"]
    tone: Literal["key", "ask", "remember", "case"] = "key"
    label: str = Short
    text: str = Text
    _c = _clean("label", "text")


class StopSaveReport(B):
    type: Literal["stop_save_report"]
    stop: list[str] = Field(default_factory=list, max_length=12)
    save: list[str] = Field(default_factory=list, max_length=12)
    report: list[str] = Field(default_factory=list, max_length=12)
    _c = field_validator("stop", "save", "report")(_clean_list)


class AskYourself(B):
    type: Literal["ask_yourself"]
    items: list[str] = Field(min_length=1, max_length=20)
    _c = field_validator("items")(_clean_list)


class Image(B):
    type: Literal["image"]
    asset: int
    alt: str = Field(default="", max_length=300)
    caption: str = Field(default="", max_length=300)
    _c = _clean("alt", "caption")


class TranscriptLine(B):
    t0: float = Field(ge=0)
    t1: float = Field(ge=0)
    en: str = Field(default="", max_length=1000)
    hi: str = Field(default="", max_length=1000)
    _c = _clean("en", "hi")


class Video(B):
    type: Literal["video"]
    youtube_id: str = Field(default="", pattern=r"^([A-Za-z0-9_-]{11})?$")
    mp4: int | None = None  # MediaAsset id
    poster: int | None = None  # MediaAsset id
    duration: float = Field(default=0, ge=0)
    transcript: list[TranscriptLine] = Field(default_factory=list, max_length=400)


class Attachment(B):
    type: Literal["attachment"]
    asset: int
    label: str = Short
    _c = _clean("label")


# --- inline interactions ---------------------------------------------------------------------


class Reveal(B):
    """Predict, then reveal: the learner thinks (or picks) first, the server then shows the answer."""

    type: Literal["reveal"]
    label: str = Field(default="Predict, then reveal", max_length=120)
    prompt: str = Text
    answer: str = Text  # never in the page until the learner asks for it
    _c = _clean("label", "prompt", "answer")


class FlipCard(B):
    front: str = Short
    back: str = Text
    _c = _clean("front", "back")


class FlipCards(B):
    type: Literal["flipcards"]
    heading: str = Field(default="", max_length=300)
    cards: list[FlipCard] = Field(min_length=1, max_length=12)
    _c = _clean("heading")


class MythFact(B):
    type: Literal["mythfact"]
    statement: str = Text
    is_fact: bool  # never in the page: the verdict comes from the server after the learner picks
    why: str = Text
    _c = _clean("statement", "why")


class Check(B):
    """A practice question (practice pool only) answered through POST /learn/check."""

    type: Literal["check"]
    question: str = Field(pattern=r"^[A-Z0-9-]{2,30}$")  # Question.stable_id


Inner = Annotated[Paragraph | ListBlock, Field(discriminator="type")]


class Case(B):
    type: Literal["case"]
    blocks: list[Inner] = Field(min_length=1, max_length=20)


class Remember(B):
    type: Literal["remember"]
    blocks: list[Inner] = Field(min_length=1, max_length=20)


Block = Annotated[
    Heading | Paragraph | ListBlock | Pairs | Table | Cards | Signs | Urgency | Callout | StopSaveReport | AskYourself | Image | Video | Attachment | Reveal | FlipCards | MythFact | Check | Case | Remember,
    Field(discriminator="type"),
]  # fmt: skip

INTERACTIONS = {"reveal", "flipcards", "mythfact", "check", "ask_yourself"}
_ADAPTER = TypeAdapter(list[Block])


class BlocksInvalid(ValueError):
    pass


def validate_blocks(blocks) -> list[dict]:
    """The blocks as clean dicts, or BlocksInvalid with readable reasons."""
    try:
        parsed = _ADAPTER.validate_python(blocks)
    except ValidationError as exc:
        reasons = [
            f"block {e['loc'][0] if e['loc'] else '?'}: {e['msg']}" for e in exc.errors()[:10]
        ]
        raise BlocksInvalid("; ".join(reasons)) from None
    return [b.model_dump(mode="json") for b in parsed]


def has_interaction(blocks: list[dict]) -> bool:
    return any(b.get("type") in INTERACTIONS for b in blocks)


# --- the module overview (module page) ---------------------------------------------------------


class ModuleOverview(B):
    what: str = Field(default="", max_length=4000)
    outcomes: list[str] = Field(default_factory=list, max_length=20)
    callout: str = Field(default="", max_length=2000)
    stop: list[str] = Field(default_factory=list, max_length=12)
    save: list[str] = Field(default_factory=list, max_length=12)
    report: list[str] = Field(default_factory=list, max_length=12)
    _c = _clean("what", "callout")
    _l = field_validator("outcomes", "stop", "save", "report")(_clean_list)


def validate_overview(data: dict) -> dict:
    return ModuleOverview.model_validate(data).model_dump(mode="json")
