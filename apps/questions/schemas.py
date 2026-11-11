"""Validation schemas for question bodies, one per format (architecture §6, §9.2, §13.2).

Only `mcq` exists in Stage 2. The body is the *server's* record: it holds the key (`correct`), the
hint and the gate reasons. The browser never sees it: see apps/questions/projections.py.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

__all__ = ["MCQBody", "MCQOption", "ValidationError", "parse_body", "publish_errors"]

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _plain(value: str) -> str:
    """Plain text only: collapse whitespace, refuse control characters. Templates escape it."""
    if _CONTROL.search(value):
        raise ValueError("contains control characters")
    return " ".join(value.split())


class MCQOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # An internal key. It is never sent to the browser: each attempt maps random tokens to it.
    id: str = Field(pattern=r"^o[1-6]$")
    text: str = Field(min_length=1, max_length=600)

    _clean = field_validator("text")(_plain)


class MCQBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stem: str = Field(min_length=1, max_length=1500)
    options: list[MCQOption] = Field(min_length=2, max_length=6)
    correct: str
    hint: str = Field(default="", max_length=1500)
    # Options that would put a citizen at risk, with the reason (D25). Never the correct option.
    gate: dict[str, str] = Field(default_factory=dict)

    _clean = field_validator("stem", "hint")(_plain)

    @model_validator(mode="after")
    def _consistent(self):
        ids = [o.id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate option ids")
        texts = [o.text.casefold() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("two options have the same text")
        if self.correct not in ids:
            raise ValueError(
                "exactly one option must be correct: the key is not one of the options"
            )
        for key, reason in self.gate.items():
            if key not in ids:
                raise ValueError(f"gate option {key} is not one of the options")
            if key == self.correct:
                raise ValueError("the correct option cannot be a safety-gate option")
            if not reason.strip():
                raise ValueError(f"gate option {key} needs a reason")
        return self


SCHEMAS = {"mcq": MCQBody}


def parse_body(fmt: str, data: dict) -> BaseModel:
    """Validate a body for its format. Raises pydantic.ValidationError."""
    if fmt not in SCHEMAS:
        raise ValueError(f"Format {fmt!r} is not available yet")
    return SCHEMAS[fmt].model_validate(data)


def publish_errors(fmt: str, data: dict) -> list[str]:
    """What stops this body from going live (§13.2): schema, one correct answer, a hint."""
    try:
        body = parse_body(fmt, data)
    except ValidationError as exc:
        return [f"{'.'.join(str(p) for p in e['loc']) or 'body'}: {e['msg']}" for e in exc.errors()]
    except ValueError as exc:
        return [str(exc)]
    errors = []
    if not body.hint.strip():
        errors.append("hint: a hint is required before a question can go live")
    return errors
