"""XLSX round trip per module (architecture §14).

Export: one sheet with `key`, `English`, then the text and status of each language. Import is
all-or-nothing and refuses:

* unknown keys (not in that module's live course)
* `[[!markers]]` or `{placeholders}` that differ from the English
* `<` or `>` that the English does not have
* a blank cell where a translation already exists (blank-over-existing)

Every new or changed line becomes a draft uploaded by the importer; review happens in the app.
A line whose English column differs from today's English is saved against the sheet's English,
so it shows as stale (English is shown) until it is translated again.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

from apps.audit.services import audit

from . import keys, rules
from .models import Translation, TranslationLanguage
from .sources import course_sources

LANG_COLUMNS = {code: label for code, label in TranslationLanguage.choices}
MARKER = re.compile(r"\[\[!.*?\]\]|\{[A-Za-z0-9_]*\}")
MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024


class SheetRejected(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


@dataclass
class ImportResult:
    created: int = 0
    changed: int = 0
    same: int = 0
    stale: int = 0
    languages: set = field(default_factory=set)


def _text_cell(cell, value):
    cell.value = value
    cell.data_type = "s"  # never a formula, whatever the text starts with


def export_module(module_number: int) -> bytes:
    sources = course_sources(module_number)
    rows = {
        (r.key, r.language): r
        for r in Translation.objects.filter(key__in=[s.key for s in sources])
    }
    book = Workbook()
    sheet = book.active
    sheet.title = f"Module {module_number}"
    header = ["key", "English"]
    for label in LANG_COLUMNS.values():
        header += [label, f"{label} status"]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for line, source in enumerate(sources, start=2):
        values = [source.key, source.english]
        for code in LANG_COLUMNS:
            row = rows.get((source.key, code))
            if row is None:
                values += ["", "missing"]
            elif row.source_hash != keys.source_hash(source.english):
                values += [row.text, "stale"]
            else:
                values += [row.text, row.status]
        for column, value in enumerate(values, start=1):
            _text_cell(sheet.cell(row=line, column=column), value)
            sheet.cell(row=line, column=column).alignment = Alignment(wrap_text=True)
    widths = [28, 60] + [50, 12] * len(LANG_COLUMNS)
    for i, width in enumerate(widths):
        sheet.column_dimensions[chr(ord("A") + i)].width = width
    sheet.freeze_panes = "C2"
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def line_errors(english: str, text: str) -> list[str]:
    """Problems with one translated cell against its English."""
    errors = []
    if Counter(MARKER.findall(english)) != Counter(MARKER.findall(text)):
        errors.append("its [[!markers]] or {placeholders} differ from the English")
    for ch in "<>":
        if ch in text and ch not in english:
            errors.append(f"it contains '{ch}', which the English does not")
    return errors


def _read(upload) -> list[tuple]:
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SheetRejected(["The file is larger than 5 MB."])
    try:
        book = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - any unreadable upload is the same answer
        raise SheetRejected(["That file is not an Excel (.xlsx) workbook."]) from None
    sheet = book.worksheets[0]
    rows = []
    for i, row in enumerate(sheet.iter_rows(values_only=True)):
        if i > MAX_ROWS:
            raise SheetRejected([f"The sheet has more than {MAX_ROWS} rows."])
        rows.append(tuple("" if v is None else str(v) for v in row))
    return rows


def import_module(module_number: int, upload, user, request=None) -> ImportResult:
    rows = _read(upload)
    if not rows:
        raise SheetRejected(["The sheet is empty."])
    header = [h.strip() for h in rows[0]]
    if "key" not in header or "English" not in header:
        raise SheetRejected(["The first row needs the columns 'key' and 'English'."])
    columns = {code: header.index(label) for code, label in LANG_COLUMNS.items() if label in header}
    if not columns:
        raise SheetRejected(["The sheet has no Hindi, Marathi or Gujarati column."])
    key_col, en_col = header.index("key"), header.index("English")
    known = {s.key: s for s in course_sources(module_number)}
    existing = {
        (r.key, r.language): r for r in Translation.objects.filter(key__in=list(known))
    }
    errors, plan, seen = [], [], set()

    def cell(values, index):
        return values[index].strip() if index < len(values) else ""

    for number, values in enumerate(rows[1:], start=1):
        key, english = cell(values, key_col), cell(values, en_col)
        if not key and not any(cell(values, c) for c in columns.values()):
            continue
        where = f"Row {number} ({key or 'no key'})"
        if key not in known:
            errors.append(f"{where}: unknown key for module {module_number}.")
            continue
        if key in seen:
            errors.append(f"{where}: the key appears twice.")
            continue
        seen.add(key)
        english = english or known[key].english
        for code, index in columns.items():
            text = cell(values, index)
            label = LANG_COLUMNS[code]
            if not text:
                if (key, code) in existing:
                    errors.append(f"{where}, {label}: blank, but a translation exists.")
                continue
            errors += [f"{where}, {label}: {e}." for e in line_errors(english, text)]
            plan.append((key, code, text, english))
    if errors:
        raise SheetRejected(errors)
    result = ImportResult()
    with transaction.atomic():
        for key, code, text, english in plan:
            _row, outcome = rules.save_line(
                key=key, language=code, text=text, english=english, user=user, origin="xlsx"
            )
            setattr(result, outcome, getattr(result, outcome) + 1)
            result.languages.add(code)
            if keys.source_hash(english) != keys.source_hash(known[key].english):
                result.stale += 1
        audit(
            "translation.imported",
            actor=user,
            request=request,
            module=module_number,
            created=result.created,
            changed=result.changed,
        )
    return result
