"""`t(key, lang)` and the helpers that translate whole bodies (architecture §14, D24).

    reviewed + source_hash matches the current English  -> the translation
    draft    + source_hash matches, in learning units    -> the translation, tagged "draft"
    anything else (stale, missing, draft in assessments) -> English

Assessments call `translate_question_body(..., allow_draft=False)` only, so a draft can never show
there. A translated body is a *copy* of the stored body in which only the string leaves listed in
keys.QUESTION_TEXT are replaced: ids, keys, answers and flags stay exactly as stored, and scoring
always uses the stored QuestionVersion body, never a translated copy.
"""

from dataclasses import dataclass, field

from . import keys
from .models import TRANSLATED_LANGUAGES, Translation, TranslationStatus


@dataclass
class Lookup:
    """Translations for one language, loaded in one query, used for one page."""

    lang: str
    allow_draft: bool
    rows: dict = field(default_factory=dict)
    used_draft: bool = False

    @classmethod
    def load(cls, lang: str, wanted_keys, *, allow_draft: bool) -> "Lookup":
        lookup = cls(lang=lang, allow_draft=allow_draft)
        wanted = list(dict.fromkeys(wanted_keys))
        if lang not in TRANSLATED_LANGUAGES or not wanted:
            return lookup
        statuses = [TranslationStatus.REVIEWED]
        if allow_draft:
            statuses.append(TranslationStatus.DRAFT)
        for start in range(0, len(wanted), 2000):
            for row in Translation.objects.filter(
                language=lang, key__in=wanted[start : start + 2000], status__in=statuses
            ).only("key", "text", "source_hash", "status"):
                lookup.rows[row.key] = row
        return lookup

    def get(self, key: str, english: str) -> str:
        row = self.rows.get(key)
        if row is None or row.source_hash != keys.source_hash(english):
            return english
        if row.status == TranslationStatus.DRAFT:
            if not self.allow_draft:
                return english
            self.used_draft = True
        return row.text


def t(key: str, english: str, lang: str, *, allow_draft: bool = False) -> str:
    """One string. For pages with many strings, use Lookup.load once."""
    return Lookup.load(lang, [key], allow_draft=allow_draft).get(key, english)


def _apply(data, pairs, lookup: Lookup, strip_prefix: str):
    for key, english in pairs:
        text = lookup.get(key, english)
        if text != english:
            keys.set_path(data, key[len(strip_prefix) :], text)


def translate_question_body(stable_id: str, fmt: str, body: dict, lang: str) -> dict:
    """A display copy of a question body in `lang`: reviewed translations only (D24).

    Never used for scoring. Returns the stored body itself when nothing changes.
    """
    if lang not in TRANSLATED_LANGUAGES:
        return body
    pairs = keys.question_texts(stable_id, fmt, body)
    lookup = Lookup.load(lang, [k for k, _ in pairs], allow_draft=False)
    if not lookup.rows:
        return body
    copy = keys.deep_copy(body)
    _apply(copy, pairs, lookup, f"q:{stable_id}:")
    return copy


def question_hint(stable_id: str, english: str, lang: str) -> str:
    """The hint in `lang` if a reviewed translation exists (hints are assessment text, D24)."""
    return t(f"q:{stable_id}:hint", english, lang, allow_draft=False)


def translate_blocks(prefix: str, blocks: list[dict], lookup: Lookup) -> list[dict]:
    """A display copy of a unit's blocks. A translated paragraph keeps one plain span, or its
    single span's formatting and link when it had only one."""
    pairs = keys.block_texts(prefix, blocks)
    if not any(k in lookup.rows for k, _ in pairs):
        return blocks
    out = keys.deep_copy(blocks)
    for key, english in pairs:
        text = lookup.get(key, english)
        if text == english:
            continue
        parts = key[len(prefix) + 1 :].split(":")
        target = out
        node = None
        for index in parts[:-1]:
            node = target[int(index)]
            target = node.get("blocks", [])
        path = parts[-1]
        if node.get("type") == "paragraph" and path == "text":
            spans = node["spans"]
            keep = spans[0] if len(spans) == 1 else {}
            node["spans"] = [
                {
                    "text": text,
                    "bold": keep.get("bold", False),
                    "italic": keep.get("italic", False),
                    "href": keep.get("href", ""),
                }
            ]
        else:
            keys.set_path(node, path, text)
    return out


def block_keys(prefix: str, blocks: list[dict]) -> list[str]:
    return [k for k, _ in keys.block_texts(prefix, blocks)]


def translate_module(module, lookup: Lookup) -> dict:
    """{"title", "tagline", "overview"} for a module in the lookup's language."""
    title = lookup.get(f"mod:{module.number}:title", module.title) if module.title else ""
    tagline = lookup.get(f"mod:{module.number}:tagline", module.tagline) if module.tagline else ""
    overview = module.overview or {}
    pairs = [
        (f"mod:{module.number}:overview.{p}", text)
        for p, text in keys.text_fields(overview, keys.OVERVIEW_TEXT)
    ]
    if any(k in lookup.rows for k, _ in pairs):
        overview = keys.deep_copy(overview)
        _apply(overview, pairs, lookup, f"mod:{module.number}:overview.")
    return {"title": title, "tagline": tagline, "overview": overview}


def module_keys(module) -> list[str]:
    return [k for k, _ in keys.module_texts(module)]


def note(name: str, lang: str) -> str:
    """A fixed note (keys.NOTES) in `lang`: reviewed wording only, else English (D7)."""
    return t(f"note:{name}", keys.NOTES[name], lang, allow_draft=False)
