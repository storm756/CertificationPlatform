"""What the browser may receive about a question: `client_projection()` (architecture §9.2).

Every format has one (apps/questions/formats.py). It is built from an allow-list, never by removing
fields from the body, so a new field in the body can't leak by accident. The browser gets the text
and one-off random tokens: no key, no hint, no `why`, no gate flag, no risky-segment flag, no
canonical order and no internal id.
"""

from . import formats


def client_projection(fmt: str, body: dict, option_map: dict, response: dict | None = None) -> dict:
    return formats.project(fmt, body, option_map, response)
