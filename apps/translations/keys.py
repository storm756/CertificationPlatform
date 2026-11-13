"""Translation keys and where their English text lives (architecture §14).

Key grammar (all keys are server-side only; they never reach the browser):

    q:<stable id>:<path>             a question's text, e.g. q:M1-04:options.2.text
    blk:<module>.<unit>:title        a unit's title, e.g. blk:1.t3:title
    blk:<module>.<unit>:<i>:<path>   a block's text, e.g. blk:1.t3:4:items.0
    mod:<module>:<path>              a module's title, tagline and overview
    part:<part id>:name              an assessment part's name
    note:<name>                      a fixed note written in code (NOTES below)

A path is a dotted walk through the JSON body. List positions in a path are fine here: the key is
never sent to the browser, and a translation is used only while the English at that path still has
the hash it was translated from (source_hash), so a re-ordered or edited source is never mislabelled.
"""

import copy
import hashlib

# What a translator may change, per question format. Everything else in a body (ids, keys,
# answers, coordinates, tones, gate flags, scores) is never touched. Crosswords stay English (D33).
_BASE = ["title", "ask", "scene", "hint", "why", "gate_message"]
QUESTION_TEXT: dict[str, list[str]] = {
    "mcq": ["stem", "options.*.text", "hint"],
    "mc": _BASE + ["options.*.text"],
    "cards": _BASE + ["labels.*.text", "items.*.text", "items.*.why"],
    "spot": _BASE + ["segments.*.text", "gate_if_missed"],
    "hotspot": _BASE + ["image_alt", "legend", "regions.*.label", "regions.*.why"],
    "sort": _BASE + ["bins.*.text", "items.*.text", "items.*.why"],
    "match": _BASE
    + ["pairs.*.left", "pairs.*.right", "pairs.*.why", "extra.*", "left_label", "right_label"],
    "order": _BASE + ["items.*.text", "items.*.why"],
    "pick": _BASE + ["items.*.text", "items.*.why", "check_label"],
    "build": _BASE + ["chips.*.text", "slots.*.label", "scene_label"],
    "settings": _BASE
    + ["rows.*.text", "rows.*.options.*", "rows.*.why", "device", "screen", "check_label"],
    "dial": _BASE + ["rows.*.label", "rows.*.unit", "rows.*.why"],
    "chat": _BASE + ["who", "steps.*.say", "steps.*.replies.*.text", "steps.*.replies.*.why"],
    "crossword": [],
}

# Text fields per lesson block type (apps/content/blocks.py). A paragraph is translated whole
# (`text`, its spans joined), so a sentence is never split between translators.
BLOCK_TEXT: dict[str, list[str]] = {
    "heading": ["text"],
    "paragraph": [],  # handled as a whole: see block_texts()
    "list": ["items.*"],
    "pairs": ["rows.*.0", "rows.*.1"],
    "table": ["caption", "head.*", "rows.*.*"],
    "cards": ["heading", "cards.*.label", "cards.*.title", "cards.*.text"],
    "signs": ["heading", "items.*"],
    "urgency": [
        "heading",
        "rows.*.label",
        "rows.*.level",
        "rows.*.when",
        "rows.*.action",
        "rows.*.time",
    ],
    "callout": ["label", "text"],
    "stop_save_report": ["stop.*", "save.*", "report.*"],
    "ask_yourself": ["items.*"],
    "image": ["alt", "caption"],
    "video": [],  # films have their own caption files
    "attachment": ["label"],
    "reveal": ["label", "prompt", "answer"],
    "flipcards": ["heading", "cards.*.front", "cards.*.back"],
    "mythfact": ["statement", "why"],
    "check": [],  # a practice question: translated through its q: keys
    "case": [],  # inner blocks: see block_texts()
    "remember": [],
}

OVERVIEW_TEXT = ["what", "outcomes.*", "callout", "stop.*", "save.*", "report.*"]

# Fixed notes written in code that go through the Translation workflow.
NOTES = {
    # D33: Module 8's graded crosswords stay English in every language.
    "m8-crosswords-english": (
        "The crosswords in this module stay in English, whichever language you choose. "
        "The rest of the module is shown in your language where a translation is ready."
    ),
}


def normalise(text: str) -> str:
    return " ".join(str(text).split())


def source_hash(english: str) -> str:
    return hashlib.sha256(normalise(english).encode("utf-8")).hexdigest()


def _walk(node, parts, prefix):
    if not parts:
        if isinstance(node, str) and node.strip():
            yield prefix, node
        return
    head, rest = parts[0], parts[1:]
    if head == "*":
        if isinstance(node, list | tuple):
            for i, child in enumerate(node):
                yield from _walk(child, rest, (*prefix, str(i)))
    elif isinstance(node, dict):
        if head in node:
            yield from _walk(node[head], rest, (*prefix, head))
    elif isinstance(node, list | tuple) and head.isdigit() and int(head) < len(node):
        yield from _walk(node[int(head)], rest, (*prefix, head))


def text_fields(data, patterns) -> list[tuple[str, str]]:
    """[(path, english)] for every non-empty string matching the patterns, in order."""
    out = []
    for pattern in patterns:
        out += [(".".join(p), text) for p, text in _walk(data, pattern.split("."), ())]
    return out


def set_path(data, path: str, value: str) -> None:
    """Set a string leaf in place. The leaf must already be a string (never changes a type)."""
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        index = int(last)
        if not isinstance(node[index], str):
            raise TypeError(f"{path} is not text")
        node[index] = value
    else:
        if not isinstance(node.get(last), str):
            raise TypeError(f"{path} is not text")
        node[last] = value


def question_texts(stable_id: str, fmt: str, body: dict) -> list[tuple[str, str]]:
    """[(key, english)] for a question version's body."""
    return [(f"q:{stable_id}:{p}", text) for p, text in text_fields(body, QUESTION_TEXT[fmt])]


def paragraph_text(block: dict) -> str:
    return "".join(span.get("text", "") for span in block.get("spans", []))


def block_texts(prefix: str, blocks: list[dict]) -> list[tuple[str, str]]:
    """[(key, english)] for a unit version's blocks. `prefix` is `blk:<module>.<unit>`."""
    out = []
    for i, block in enumerate(blocks):
        out += _one_block(f"{prefix}:{i}", block)
    return out


def _one_block(prefix: str, block: dict) -> list[tuple[str, str]]:
    kind = block.get("type")
    if kind == "paragraph":
        text = paragraph_text(block)
        return [(f"{prefix}:text", text)] if text.strip() else []
    if kind in ("case", "remember"):
        out = []
        for j, inner in enumerate(block.get("blocks", [])):
            out += _one_block(f"{prefix}:{j}", inner)
        return out
    return [(f"{prefix}:{p}", text) for p, text in text_fields(block, BLOCK_TEXT.get(kind, []))]


def unit_prefix(module_number: int, unit_slug: str) -> str:
    return f"blk:{module_number}.{unit_slug}"


def module_texts(module) -> list[tuple[str, str]]:
    out = []
    for field in ("title", "tagline"):
        value = getattr(module, field, "")
        if value and value.strip():
            out.append((f"mod:{module.number}:{field}", value))
    out += [
        (f"mod:{module.number}:overview.{p}", text)
        for p, text in text_fields(module.overview or {}, OVERVIEW_TEXT)
    ]
    return out


def deep_copy(data):
    return copy.deepcopy(data)
