"""Import the existing draft translations (build-stages Stage 8). Preview by default.

python manage.py import_draft_translations            # preview: counts and the report only
python manage.py import_draft_translations --apply    # save the matched lines as drafts

Reads private inputs from content-data/ (never in git). Writes the unmatched-lines report to
content-data/outputs/translation-import-report.csv for the team.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.translations import drafts

BASE = Path(settings.BASE_DIR)
DEFAULTS = {
    "sheets": "content-data/translations/translation-files-prefilled",
    "tables": "content-data/ccfr-release/ccfr-table-translations.draft.json",
    "prototype": "content-data/prototype/data/i18n",
    "phrases": "design-reference/frontend-prototype/js/phrases.js",
    "hints": "content-data/outputs",
    "report": "content-data/outputs/translation-import-report.csv",
}


class Command(BaseCommand):
    help = "Import draft translations from the private inputs, matched to stable keys."

    def add_arguments(self, parser):
        for name, default in DEFAULTS.items():
            parser.add_argument(f"--{name}", default=default)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, apply, **paths):
        p = {k: BASE / v for k, v in paths.items() if k in DEFAULTS}
        hint_files = sorted(p["hints"].rglob("*Hints-with-Translations.xlsx")) if p["hints"].is_dir() else [p["hints"]]  # fmt: skip
        entries = []
        counts = {}
        for name, found in (
            ("sheets", drafts.read_sheets(p["sheets"]) if p["sheets"].is_dir() else []),
            ("tables", drafts.read_tables(p["tables"])),
            ("hints", [e for f in hint_files for e in drafts.read_hints(f)]),
            ("prototype", drafts.read_prototype_i18n(p["prototype"])),
            ("phrases", drafts.read_phrases(p["phrases"])),
        ):
            counts[name] = len(found)
            entries += found
        for name, n in counts.items():
            self.stdout.write(f"read {name}: {n} lines")
        result = drafts.plan(entries)
        for origin, n in sorted(result.by_origin.items()):
            self.stdout.write(f"to import from {origin}: {n}")
        self.stdout.write(f"already translated (left alone): {result.skipped_existing}")
        self.stdout.write(f"refused by validation: {len(result.refused)}")
        self.stdout.write(f"unmatched (in the report): {len(result.unmatched)}")
        drafts.write_report(result, p["report"])
        self.stdout.write(f"report: {paths['report']}")
        if apply:
            saved = drafts.apply(result)
            self.stdout.write(self.style.SUCCESS(f"saved {saved} draft lines"))
        else:
            self.stdout.write("preview only: run again with --apply to save")
