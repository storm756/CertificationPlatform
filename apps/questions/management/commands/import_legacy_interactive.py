from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.questions import legacy_interactive as legacy


class Command(BaseCommand):
    help = (
        "One-off import of the legacy interactive challenges as DRAFT questions "
        "(docs/legacy-sources.md). Prints counts and ids only, never question text. "
        "Export the input first with tools/legacy_export.mjs. Use --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(Path(settings.BASE_DIR) / "content-data" / "legacy" / "interactive.json"),
            help="The JSON from tools/legacy_export.mjs (kept in content-data/legacy/).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Check and count, save nothing.")

    def handle(self, *args, source, dry_run, **options):
        path = Path(source)
        if not path.exists():
            raise CommandError(f"{path} not found. Run tools/legacy_export.mjs first.")
        try:
            report = legacy.run(path, dry_run=dry_run)
        except legacy.LegacyImportRefused as exc:
            raise CommandError(str(exc)) from exc
        out = self.stdout.write
        out(
            ("DRY RUN: nothing was saved.\n" if dry_run else "")
            + f"Created {report.created} challenge(s) as drafts, {report.unchanged} unchanged."
        )
        out("  By format: " + ", ".join(f"{k} {v}" for k, v in sorted(report.by_format.items())))
        out("  By pool: " + ", ".join(f"{k} {v}" for k, v in sorted(report.by_pool.items())))
        if report.mixed:
            out(f"  {report.mixed} belong to the practice mock (mixed set).")
        if report.no_picture:
            out(
                "  Hotspot picture could not be drawn from the legacy art: "
                + ", ".join(report.no_picture)
            )
        if report.invalid:
            out(f"INVALID ({len(report.invalid)}), not imported: {', '.join(report.invalid)}")
        out(
            f"{report.missing_hints} imported challenge(s) have no hint (they only have a worked "
            "explanation, which is for practice). They stay drafts and cannot go live until the "
            "team supplies approved hints."
        )
