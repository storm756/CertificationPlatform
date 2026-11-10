"""What the browser may receive about a question: `client_projection()` (architecture §9.2).

Every format has one. It is built from an allow-list, never by removing fields from the body, so a
new field in the body can't leak by accident. For MCQ the browser gets the stem and the options
as one-off tokens in shuffled order: no key, no hint, no gate flag, no internal option ids.
"""


def client_projection(fmt: str, body: dict, option_map: dict) -> dict:
    if fmt == "mcq":
        return _mcq(body, option_map)
    raise ValueError(f"No projection for format {fmt!r}")


def _mcq(body: dict, option_map: dict) -> dict:
    text_by_key = {o["id"]: o["text"] for o in body["options"]}
    return {
        "format": "mcq",
        "stem": body["stem"],
        "options": [
            {"token": token, "text": text_by_key[option_map["tokens"][token]]}
            for token in option_map["order"]
        ],
    }
