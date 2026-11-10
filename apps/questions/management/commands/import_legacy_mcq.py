from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.questions import legacy


class Command(BaseCommand):
    help = (
        "One-off import of the legacy MCQ bank as DRAFT questions (docs/legacy-sources.md). "
        "Prints counts only, never question text. Use --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(Path(settings.BASE_DIR) / "content-data" / "legacy" / "bank_booklet.json"),
            help="Path to bank_booklet.json (kept outside git, in content-data/legacy/).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Check and count, save nothing.")

    def handle(self, *args, source, dry_run, **options):
        path = Path(source)
        if not path.exists():
            raise CommandError(
                f"{path} not found. Copy bank_booklet.json into content-data/legacy/."
            )
        try:
            report = legacy.run(path, dry_run=dry_run)
        except legacy.LegacyImportRefused as exc:
            raise CommandError(str(exc)) from exc
        out = self.stdout.write
        out(
            ("DRY RUN: nothing was saved.\n" if dry_run else "")
            + f"Created {report.created} question(s) as drafts, {report.unchanged} unchanged."
        )
        for number in sorted(report.per_module):
            counts = report.per_module[number]
            out(
                f"  Module {number}: {counts['module_quiz']} quiz, {counts['practice']} practice, "
                f"fewest per PC in the quiz: {report.quiz_min_pc[number]}"
            )
        if report.invalid:
            out(f"INVALID ({len(report.invalid)}), not imported: {', '.join(report.invalid)}")
        out(
            f"{report.missing_hints} imported question(s) have no hint. They stay drafts and "
            "cannot go live until the team supplies approved hints."
        )
