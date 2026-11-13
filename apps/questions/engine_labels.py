"""The interactive engine's interface labels, translated with gettext (Stage 8).

The engine (engine/src/i18n.ts) reads {English: translation} from a json_script element on the
page. Interface labels only: never question text, never answers. Crossword labels are not here:
crosswords stay English (D33).
"""

from django.utils.translation import gettext, gettext_noop

LABELS = [
    gettext_noop("Red"),
    gettext_noop("Amber"),
    gettext_noop("Yellow"),
    gettext_noop("Green"),
    gettext_noop("Tap a card, then tap where it belongs ({n} left)"),
    gettext_noop("All placed. Tap a card to move it."),
    gettext_noop(
        "Tap an item on the left, then its partner on the right. Tap again to change a pair."
    ),
    gettext_noop("Situation"),
    gettext_noop("Goes with"),
    gettext_noop("Your order"),
    gettext_noop("Tap the steps below in the order you would do them."),
    gettext_noop("Tap to remove"),
    gettext_noop("Steps to place"),
    gettext_noop("Cards for: {label}"),
    gettext_noop("Tap a slot to change it"),
    gettext_noop("You"),
    gettext_noop("What do you say or do?"),
    gettext_noop("That is the end of the conversation. Your replies are saved."),
    gettext_noop("Choose one answer"),
    gettext_noop("All cards are answered. Use Previous to change one."),
    gettext_noop("Previous"),
    gettext_noop("Your verdict"),
    gettext_noop("The picture for this question is not available yet."),
    gettext_noop("Settings"),
    gettext_noop("I have finished this question"),
    gettext_noop("✓ Marked as finished"),
    gettext_noop("This question can't be shown."),
]


def engine_labels() -> dict[str, str]:
    """{English: translation} for the active language; labels with no translation are left out."""
    out = {}
    for english in LABELS:
        shown = gettext(english)
        if shown != english:
            out[english] = shown
    return out
