"""CSV export of a batch (architecture §15). Safe to open in Excel.

Excel and other spreadsheets run a cell that starts with = + - @ (or a tab or carriage return) as a
formula. A learner chooses their own certificate name, so every text cell is made inert by a
leading apostrophe (OWASP "CSV injection"). The file is UTF-8 with a byte-order mark so Hindi,
Marathi and Gujarati names open correctly, and it is downloaded, never shown in the browser.
"""

import csv
import io

DANGEROUS = ("=", "+", "-", "@", "\t", "\r", "\n")
BOM = "﻿"


def safe_cell(value) -> str:
    """Text that a spreadsheet will never run as a formula."""
    text = "" if value is None else str(value)
    stripped = text.lstrip(" ")
    if stripped.startswith(DANGEROUS) or text.startswith(DANGEROUS):
        return "'" + text
    return text


def batch_csv(overview: dict, batch) -> str:
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    head = ["Batch", "Name", "Email", "Status"]
    head += [f"Module {number} %" for number, _ in overview["modules"]]
    head += ["Final %", "Overall %", "Eligible"]
    writer.writerow([safe_cell(h) for h in head])
    for row in overview["rows"]:
        line = [batch.code, row["name"], row["user"].email, row["status"]]
        line += [str(c["value"]) if c["parts"] else "" for c in row["cells"]]
        line += ["" if row["final"] is None else str(row["final"]), str(row["overall"]), "yes" if row["eligible"] else "no"]  # fmt: skip
        writer.writerow([safe_cell(x) for x in line])
    return out.getvalue()
