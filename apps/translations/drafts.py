"""Import the existing draft translations as `draft` rows (build-stages Stage 8).

The sources are matched to stable keys by their English text, never stored by English: once a
line has a key, a later English edit makes it stale instead of silently breaking it (the reason
the prototype's phrases.js method was rejected). Sources (all private, outside git):

* the team's pre-filled sheets (`content-data/translations/translation-files-prefilled/*.csv`):
  `id, English, Hindi, Hindi status, …`. Every status there is "draft - needs review" or
  "to translate"; whatever a sheet says, a line imported here is a draft (review is in the app).
* the corrected-table drafts (`content-data/ccfr-release/ccfr-table-translations.draft.json`)
* the prototype's `data/i18n/{hi,mr,gu}.js` (English -> text) and `js/phrases.js`
* the hint sheet (`CCFR-Question-Hints-with-Translations.xlsx`), keyed by question ID

Earlier sources in that list win when two disagree. An existing row is never overwritten. Lines
that match no key go in a report for the team (kept in `content-data/`, never in git).
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from . import rules
from .models import TRANSLATED_LANGUAGES, Translation
from .sources import course_sources
from .xlsx import line_errors

LANG_NAMES = {"hi": "Hindi", "mr": "Marathi", "gu": "Gujarati"}
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def match_text(text: str) -> str:
    """The loose form used only to *find* a key: whitespace, curly quotes and dashes ignored."""
    return " ".join(str(text).translate(_QUOTES).split()).strip().casefold()


@dataclass
class Entry:
    english: str
    texts: dict  # lang -> text
    origin: str
    where: str  # file and row/id, for the report
    key: str | None = None  # set for keyed sources (hints)


@dataclass
class Plan:
    rows: list = field(default_factory=list)  # (key, lang, text, english, origin)
    unmatched: list = field(default_factory=list)  # Entry
    refused: list = field(default_factory=list)  # (key, lang, reason, origin)
    skipped_existing: int = 0
    by_origin: dict = field(default_factory=dict)


# --- readers ------------------------------------------------------------------------------------


def read_sheets(folder: Path) -> list[Entry]:
    out = []
    for path in sorted(folder.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for number, row in enumerate(csv.DictReader(handle), start=2):
                texts = {}
                for code, name in LANG_NAMES.items():
                    value = (row.get(name) or row.get(f"{name} ({_native(code)})") or "").strip()
                    if value:
                        texts[code] = value
                english = (row.get("English") or "").strip()
                if english and texts:
                    where = f"{path.name} row {number} ({row.get('id', '')})"
                    out.append(Entry(english, texts, "sheet", where))
    return out


def _native(code):
    return {"hi": "हिंदी", "mr": "मराठी", "gu": "ગુજરાતી"}[code]


def read_tables(path: Path) -> list[Entry]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text("utf-8"))
    out = []
    for record in data.get("records", []):
        texts = {
            c: record[c].strip() for c in TRANSLATED_LANGUAGES if (record.get(c) or "").strip()
        }
        if record.get("english") and texts:
            where = f"{path.name} ({', '.join(record.get('locations', [])[:2])})"
            out.append(Entry(record["english"], texts, "tables", where))
    return out


_I18N = re.compile(r"\.(hi|mr|gu)\s*=\s*(\{.*\})\s*;?\s*$", re.S)


def read_prototype_i18n(folder: Path) -> list[Entry]:
    merged: dict[str, dict] = {}
    for code in TRANSLATED_LANGUAGES:
        path = folder / f"{code}.js"
        if not path.is_file():
            continue
        found = _I18N.search(path.read_text("utf-8"))
        if not found:
            continue
        for english, text in json.loads(found.group(2)).items():
            if isinstance(text, str) and text.strip():
                merged.setdefault(english, {})[code] = text.strip()
    return [Entry(e, t, "prototype", f"i18n/*.js ({e[:40]})") for e, t in merged.items()]


_JS_STR = r"'((?:[^'\\]|\\.)*)'"
_PHRASE = re.compile(_JS_STR + r"\s*:\s*\[\s*" + r"\s*,\s*".join([_JS_STR] * 3) + r"\s*,?\s*\]")


def _unjs(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def read_phrases(path: Path) -> list[Entry]:
    """`js/phrases.js`: 'English': ['Hindi', 'Marathi', 'Gujarati'] (single-quoted JS)."""
    if not path.is_file():
        return []
    out = []
    for found in _PHRASE.finditer(path.read_text("utf-8")):
        english, *texts = (_unjs(g) for g in found.groups())
        langs = {c: t for c, t in zip(TRANSLATED_LANGUAGES, texts, strict=True) if t.strip()}
        if langs:
            out.append(Entry(english, langs, "phrases", f"phrases.js ({english[:40]})"))
    return out


def read_hints(path: Path) -> list[Entry]:
    """The hint workbook: a header row with Question ID … Hindi/Marathi/Gujarati hint."""
    if not path.is_file():
        return []
    from openpyxl import load_workbook

    out = []
    book = load_workbook(path, read_only=True, data_only=True)
    for sheet in book.worksheets:
        header = None
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).strip() for v in row]
            if header is None:
                if "Question ID" in cells:
                    header = cells
                continue
            get = dict(zip(header, cells, strict=False))
            qid, english = get.get("Question ID", ""), get.get("Approved hint", "")
            texts = {c: get.get(f"{n} hint", "") for c, n in LANG_NAMES.items()}
            texts = {c: t for c, t in texts.items() if t}
            if qid and english and texts:
                out.append(
                    Entry(english, texts, "hints", f"{path.name} {qid}", key=f"q:{qid}:hint")
                )
    return out


# --- planning -------------------------------------------------------------------------------------


def plan(entries: list[Entry]) -> Plan:
    """Match entries to keys. Entries earlier in the list win."""
    sources = course_sources()
    by_text: dict[str, list] = {}
    english_of = {}
    for source in sources:
        by_text.setdefault(match_text(source.english), []).append(source.key)
        english_of[source.key] = source.english
    existing = set(Translation.objects.values_list("key", "language"))
    chosen: dict[tuple, tuple] = {}
    result = Plan()
    for entry in entries:
        if entry.key:
            targets = [entry.key] if entry.key in english_of else []
        else:
            targets = by_text.get(match_text(entry.english), [])
        if not targets:
            result.unmatched.append(entry)
            continue
        for key in targets:
            for code, text in entry.texts.items():
                if (key, code) in existing:
                    result.skipped_existing += 1
                elif (key, code) not in chosen:
                    # A keyed entry (a hint) is stored against the English it was written for, so
                    # if the hint changed since, it is stale rather than wrong.
                    english = entry.english if entry.key else english_of[key]
                    problems = line_errors(english, text)
                    if problems:
                        result.refused.append((key, code, "; ".join(problems), entry.where))
                        continue
                    chosen[(key, code)] = (key, code, text, english, entry.origin)
    result.rows = list(chosen.values())
    for row in result.rows:
        result.by_origin[row[4]] = result.by_origin.get(row[4], 0) + 1
    return result


def apply(result: Plan) -> int:
    with transaction.atomic():
        for key, code, text, english, origin in result.rows:
            rules.save_line(
                key=key, language=code, text=text, english=english, user=None, origin=origin
            )
    return len(result.rows)


def write_report(result: Plan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Source", "Where", "English", "Languages", "Why"])
        for entry in result.unmatched:
            if entry.origin == "phrases":
                continue  # UI phrases: they fill the .po catalogues, not course keys
            why = "question ID not live" if entry.key else "no live course text with this English"
            writer.writerow(
                [entry.origin, entry.where, entry.english, " ".join(sorted(entry.texts)), why]
            )
        for key, code, reason, where in result.refused:
            writer.writerow(["refused", where, key, code, reason])
