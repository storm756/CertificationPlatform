"""Creating, versioning and publishing questions. Versions are only ever added."""

import hashlib
import json

from django.db import transaction

from . import schemas
from .models import Question, QuestionStatus, QuestionVersion


class PublishError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def canonical(body: dict) -> dict:
    """The validated body in a stable form (internal option order kept: it is part of the key)."""
    return json.loads(json.dumps(body, sort_keys=True))


def content_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(canonical(body), sort_keys=True).encode()).hexdigest()


@transaction.atomic
def add_version(question: Question, body: dict) -> tuple[QuestionVersion, bool]:
    """Validate and store `body` as the next version. Returns (version, created).

    A body identical to the latest version creates nothing. Draft bodies may lack a hint; going
    live is `publish()`.
    """
    parsed = schemas.parse_body(question.format, body)
    clean = canonical(parsed.model_dump())
    digest = content_hash(clean)
    Question.objects.select_for_update().get(pk=question.pk)
    latest = question.versions.order_by("-version").first()
    if latest and latest.content_hash == digest:
        return latest, False
    number = (latest.version + 1) if latest else 1
    version = QuestionVersion.objects.create(
        question=question, version=number, body=clean, content_hash=digest
    )
    return version, True


@transaction.atomic
def create_question(*, stable_id, module, fmt="mcq", body, tags, pool, points=1, is_anchor=False):
    question = Question.objects.create(
        stable_id=stable_id,
        module=module,
        format=fmt,
        tags=tags,
        pool=pool,
        points=points,
        is_anchor=is_anchor,
    )
    add_version(question, body)
    return question


def publish(question: Question) -> Question:
    """Make a question live. Needs a valid body with a hint, a pool and tags (§13.2)."""
    version = question.current_version
    errors = [] if version else ["no content yet"]
    if version:
        errors += schemas.publish_errors(question.format, version.body)
    if not question.tags.get("pc"):
        errors.append("tags: a PC tag is required")
    if not question.pool:
        errors.append("pool: a pool is required")
    if errors:
        raise PublishError(errors)
    question.status = QuestionStatus.LIVE
    question.save(update_fields=["status", "updated_at"])
    return question


def retire(question: Question) -> Question:
    question.status = QuestionStatus.RETIRED
    question.save(update_fields=["status", "updated_at"])
    return question
