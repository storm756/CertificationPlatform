"""Stage 8: the UI catalogues (gettext) for Hindi, Marathi and Gujarati, and the engine's labels."""

import json
import re
from collections import Counter
from pathlib import Path

import polib
import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from apps.questions.engine_labels import LABELS, engine_labels
from apps.translations.drafts import script_problem

PLACEHOLDER = re.compile(r"%\(\w+\)[sd]|%[sd%]|\{\w*\}|</?[a-zA-Z][^>]*>")


def catalogue(code):
    return polib.pofile(
        str(Path(settings.BASE_DIR) / "locale" / code / "LC_MESSAGES" / "django.po")
    )


@pytest.mark.parametrize("code", ["hi", "mr", "gu"])
def test_every_ui_string_is_translated_with_the_same_placeholders(code):
    po = catalogue(code)
    assert po.metadata["Plural-Forms"] == "nplurals=2; plural=(n != 1);"
    for entry in po:
        if entry.obsolete:
            continue
        assert entry.translated(), f"{code}: {entry.msgid!r} is not translated"
        assert "fuzzy" not in entry.flags
        pairs = (
            [(entry.msgid, entry.msgstr_plural[0]), (entry.msgid_plural, entry.msgstr_plural[1])]
            if entry.msgid_plural
            else [(entry.msgid, entry.msgstr)]
        )
        for english, text in pairs:
            assert Counter(PLACEHOLDER.findall(english)) == Counter(PLACEHOLDER.findall(text)), (
                f"{code}: placeholders differ in {english!r}"
            )
            assert script_problem(code, text) is None, f"{code}: wrong script for {english!r}"


@pytest.mark.parametrize("code", ["hi", "mr", "gu"])
def test_compiled_catalogue_is_current(code):
    po_path = Path(settings.BASE_DIR) / "locale" / code / "LC_MESSAGES" / "django.po"
    mo = polib.mofile(str(po_path.with_suffix(".mo")))
    compiled = {e.msgid: e.msgstr for e in mo}
    for entry in catalogue(code):
        if not entry.obsolete and not entry.msgid_plural:
            assert compiled.get(entry.msgid) == entry.msgstr, (
                f"run compilemessages ({entry.msgid!r})"
            )


def test_engine_labels_are_translated_and_carry_no_content():
    with translation.override("hi"):
        labels = engine_labels()
    assert set(labels) == set(LABELS)
    assert labels["Choose one answer"] != "Choose one answer"
    with translation.override("en"):
        assert engine_labels() == {}


@pytest.mark.django_db
def test_attempt_page_carries_engine_labels(learner, learner_client, interactive_part):
    from apps.assessments import services

    part = interactive_part()
    attempt, _new = services.start(learner, part)
    learner.profile.preferred_language = "gu"
    learner.profile.save()
    html = learner_client.get(reverse("attempt_question", args=[attempt.pk, 1])).content.decode()
    found = re.search(r'<script id="engine-labels" type="application/json">(.*?)</script>', html)
    assert found
    with translation.override("gu"):
        assert json.loads(found.group(1)) == engine_labels()
