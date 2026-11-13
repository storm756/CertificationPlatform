"""Fill empty UI strings in locale/{hi,mr,gu}/django.po with draft translations (Stage 8).

python manage.py fill_ui_drafts [--extra drafts.json] [--dry-run]

Sources, by exact English: the prototype's js/phrases.js, its data/i18n/*.js, the team's
`_framework-labels-verify.csv`, then an optional JSON file {"English": {"hi": …, "mr": …, "gu": …}}.
A filled entry gets the translator comment "draft: needs review" so reviewers can find it in
Rosetta. An existing translation is never replaced. A draft whose placeholders (%(name)s, {x}) or
HTML tags differ from the English is skipped and listed.
"""

import json
import re
from collections import Counter
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.translations import drafts

BASE = Path(settings.BASE_DIR)
DRAFT_NOTE = "draft: needs review"
_PLACEHOLDERS = re.compile(r"%\(\w+\)[sd]|%[sd]|\{\w*\}|</?[a-zA-Z][^>]*>|&\w+;")


def tokens(text: str) -> Counter:
    return Counter(_PLACEHOLDERS.findall(text))


class Command(BaseCommand):
    help = "Fill empty .po entries with draft translations from the prototype and the team."

    def add_arguments(self, parser):
        parser.add_argument("--extra", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, extra, dry_run, **options):
        table: dict[str, dict] = {}
        sources = [
            drafts.read_phrases(BASE / "design-reference/frontend-prototype/js/phrases.js"),
            drafts.read_prototype_i18n(BASE / "content-data/prototype/data/i18n"),
        ]
        labels = BASE / "content-data/translations/translation-files-prefilled"
        if labels.is_dir():
            sources.append(
                [e for e in drafts.read_sheets(labels) if e.where.startswith("_framework")]
            )
        plurals: dict[str, dict] = {}
        if extra:
            data = json.loads(Path(extra).read_text("utf-8"))
            plurals = data.pop("__plural__", {})  # {msgid: {"hi": [one, other], …}}
            sources.insert(0, [drafts.Entry(k, v, "extra", "extra") for k, v in data.items()])
        for entries in sources:
            for entry in entries:
                slot = table.setdefault(" ".join(entry.english.split()), {})
                for code, text in entry.texts.items():
                    slot.setdefault(code, text)
        for code in ("hi", "mr", "gu"):
            path = BASE / "locale" / code / "LC_MESSAGES" / "django.po"
            po = polib.pofile(str(path), wrapwidth=100)
            filled, skipped, missing = 0, [], 0
            for entry in po:
                if entry.msgid_plural and not entry.translated() and entry.msgid in plurals:
                    forms = plurals[entry.msgid].get(code, [])
                    want = [tokens(entry.msgid), tokens(entry.msgid_plural)]
                    if len(forms) == 2 and [tokens(f) for f in forms] == want:
                        entry.msgstr_plural = {0: forms[0], 1: forms[1]}
                        entry.tcomment = DRAFT_NOTE
                        filled += 1
                    else:
                        skipped.append(entry.msgid[:60])
                    continue
                if entry.obsolete or entry.translated() or entry.msgid_plural:
                    continue
                text = table.get(" ".join(entry.msgid.split()), {}).get(code)
                if not text:
                    missing += 1
                    continue
                if tokens(text) != tokens(entry.msgid):
                    skipped.append(entry.msgid[:60])
                    continue
                entry.msgstr = text
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                if DRAFT_NOTE not in (entry.tcomment or ""):
                    entry.tcomment = DRAFT_NOTE
                filled += 1
            empty_plurals = sum(1 for e in po if e.msgid_plural and not e.translated())
            self.stdout.write(
                f"{code}: filled {filled}, still empty {missing}, "
                f"plural forms empty {empty_plurals}, skipped {len(skipped)} (placeholders differ)"
            )
            for msg in skipped[:10]:
                self.stdout.write(f"  skipped: {msg}")
            if not dry_run:
                po.save(str(path))
