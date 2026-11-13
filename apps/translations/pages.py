"""Putting translations on learning pages (architecture §14).

The view loads one Lookup for the page and swaps text on the in-memory objects it renders
(module title, tagline and overview, unit version titles, assessment part names). These objects are
display copies for this request only: they are never saved (UnitVersion refuses any title change,
and the views that call this never save a module or part).

Learning text (modules, units, blocks) may show drafts with a tag. Part names are assessment
text, so they show reviewed wording only (D24).
"""

from django.utils import translation

from . import keys
from .models import TRANSLATED_LANGUAGES
from .service import Lookup, translate_module


def current_language() -> str:
    lang = (translation.get_language() or "en").split("-")[0]
    return lang if lang in TRANSLATED_LANGUAGES else "en"


def learning_lookup(modules=(), units=(), extra_keys=(), lang=None) -> Lookup:
    """One Lookup (drafts allowed) for these modules, (module number, unit) pairs and extra keys."""
    lang = lang or current_language()
    wanted = list(extra_keys)
    for module in modules:
        wanted += [k for k, _ in keys.module_texts(module)]
    for number, unit in units:
        wanted.append(title_key(number, unit))
    return Lookup.load(lang, wanted, allow_draft=True)


def title_key(module_number: int, unit) -> str:
    return f"{keys.unit_prefix(module_number, unit.slug)}:title"


def localise_module(module, lookup: Lookup) -> None:
    if lookup.lang not in TRANSLATED_LANGUAGES:
        return
    shown = translate_module(module, lookup)
    if shown["title"]:
        module.title = shown["title"]
    if shown["tagline"]:
        module.tagline = shown["tagline"]
    module.overview = shown["overview"]


def localise_rows(module_number: int, rows, lookup: Lookup) -> None:
    """Unit titles on rows of {"unit", "version"} (the module outline)."""
    if lookup.lang not in TRANSLATED_LANGUAGES:
        return
    for row in rows:
        version = row["version"]
        version.title = lookup.get(title_key(module_number, row["unit"]), version.title)


def localise_parts(parts, lang=None) -> None:
    """Assessment part names: reviewed wording only (D24)."""
    lang = lang or current_language()
    parts = list(parts)
    if lang not in TRANSLATED_LANGUAGES or not parts:
        return
    lookup = Lookup.load(lang, [f"part:{p.pk}:name" for p in parts], allow_draft=False)
    for part in parts:
        part.name = lookup.get(f"part:{part.pk}:name", part.name)
