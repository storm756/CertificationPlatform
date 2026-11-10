import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.questions import legacy_interactive as legacy


class Command(BaseCommand):
    help = (
        "Private check that the Python scorers match the real legacy engine on the real legacy "
        "questions. Input: interactive.json (tools/legacy_export.mjs) and the cases file from "
        "tools/legacy_parity.mjs. Prints counts and ids only, never question text."
    )

    def add_arguments(self, parser):
        base = Path(settings.BASE_DIR) / "content-data" / "legacy"
        parser.add_argument("--source", default=str(base / "interactive.json"))
        parser.add_argument("--cases", default=str(base / "parity-real.json"))

    def handle(self, *args, source, cases, **options):
        for path in (source, cases):
            if not Path(path).exists():
                raise CommandError(f"{path} not found.")
        modules = legacy.load(Path(source))
        lookup = {
            f"{file}:{i}": q
            for file, entry in modules.items()
            for i, q in enumerate(entry["questions"], start=1)
        }
        data = json.loads(Path(cases).read_text(encoding="utf-8"))
        matched, mismatched = legacy.parity(lookup, data)
        undriven = sum(1 for c in data if "js" not in c)
        self.stdout.write(
            f"Python scorers match the legacy engine on {matched} of {matched + len(mismatched)} "
            f"cases ({undriven} cases the harness could not drive)."
        )
        if mismatched:
            self.stdout.write(f"MISMATCHES ({len(mismatched)}): {', '.join(mismatched[:40])}")
            raise CommandError("scorer parity failed")
