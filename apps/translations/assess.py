"""Translated questions inside assessments (D24, architecture §14).

The single entry point for showing a question in another language. Rules:

* Reviewed translations only. A draft is never shown in an assessment or a practice check.
* A translation applies only while the English it was made from is still the English in this
  version (source_hash), so an edited or re-ordered question falls back to English.
* The result is a display copy. Only the text leaves in keys.QUESTION_TEXT change; option ids,
  answers, flags and the per-attempt option map are untouched, and scoring and response checks
  always use the stored `QuestionVersion.body`, never this copy.
* Answers are stored as per-attempt tokens, so switching language mid-attempt changes only the
  words on screen (architecture §14).
* Crosswords stay English (D33): they have no translatable text paths.
"""

from .pages import current_language
from .service import question_hint, translate_question_body


def display_body(version, fmt: str, lang: str | None = None) -> dict:
    """What the learner reads for this question version. Never pass the result to a scorer."""
    return translate_question_body(
        version.question.stable_id, fmt, version.body, lang or current_language()
    )


def display_hint(version, lang: str | None = None) -> str:
    english = version.body.get("hint", "")
    if not english:
        return ""
    return question_hint(version.question.stable_id, english, lang or current_language())
