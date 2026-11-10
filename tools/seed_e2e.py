"""Invented data for the browser checks in tools/e2e_save_retry.mjs. Development database only.

    docker compose -f deploy/compose.dev.yml exec -T web python manage.py shell \
        < tools/seed_e2e.py

Creates an invented learner, an invented multiple-choice part and an invented interactive part
(from tests/fixtures/legacy_invented.json), starts one fresh attempt in each (resetting any earlier
ones), and prints one JSON line: {"email", "password", "mcq", "interactive", "mcq_count", ...}.
Nothing here comes from the real question banks.
"""

import json
from datetime import date

from allauth.account.models import EmailAddress
from django.conf import settings

from apps.accounts.models import Profile, User
from apps.assessments import rules, services
from apps.assessments.models import AssessmentPart, Attempt
from apps.batches.models import Batch, Enrolment
from apps.content.models import Module
from apps.questions import services as qservices
from apps.questions.models import Question
from tests.conftest import invented_body

assert "dev" in settings.SETTINGS_MODULE, "development settings only"

EMAIL, PASSWORD = "e2e.learner@example.com", "e2e-invented-pass-1"
module, _ = Module.objects.get_or_create(
    number=1, defaults={"slug": "module-1", "title_key": "module.1.title", "order": 1}
)

user = User.objects.filter(email=EMAIL).first()
if user is None:
    user = User.objects.create_user(EMAIL, PASSWORD, role="learner")
    EmailAddress.objects.create(user=user, email=EMAIL, primary=True, verified=True)
    Profile.objects.create(
        user=user, certificate_name="E2E Learner", date_of_birth=date(2000, 1, 1)
    )
    batch, _ = Batch.objects.get_or_create(
        code="E2E", defaults={"name": "E2E batch", "accepting": True, "seat_limit": 40}
    )
    Enrolment.objects.create(user=user, batch=batch)
Attempt.objects.filter(user=user).delete()


def question(stable_id, **kwargs):
    existing = Question.objects.filter(stable_id=stable_id).first()
    if existing:
        return existing
    made = qservices.create_question(stable_id=stable_id, module=module, **kwargs)
    qservices.publish(made)
    return made


# A multiple-choice part: 5 questions, all of them drawn.
for n in range(1, 6):
    options = [{"id": f"o{i}", "text": f"E2E question {n}, option {i}"} for i in (1, 2, 3, 4)]
    question(
        f"M1-E{n:02d}",
        body={
            "stem": f"E2E question {n}: pick the second option.",
            "options": options,
            "correct": "o2",
            "hint": f"E2E hint {n}.",
            "gate": {},
        },
        tags={"pc": "PC1", "type": "R"},
        pool="module_quiz",
    )
mcq_part = AssessmentPart.objects.filter(name="E2E multiple choice").first()
if mcq_part is None:
    mcq_part = AssessmentPart.objects.create(
        module=module, name="E2E multiple choice", marks=50, selection="all"
    )
    rules.publish_part(mcq_part)

# An interactive part: two single-choice formats, a tick list and (last) a chat.
CASES = ["inv-mc", "inv-mc-triage", "inv-pick-free", "inv-chat"]
for index, case_id in enumerate(CASES, start=1):
    fmt, body = invented_body(case_id)
    question(f"M1-X{index:02d}", fmt=fmt, body=body, tags={}, pool="module_quiz")
inter_part = AssessmentPart.objects.filter(name="E2E interactive").first()
if inter_part is None:
    inter_part = AssessmentPart.objects.create(
        module=module, name="E2E interactive", family="interactive", marks=50, selection="all"
    )
    rules.publish_part(inter_part)

mcq, _ = services.start(user, mcq_part)
inter, _ = services.start(user, inter_part)
print(
    json.dumps(
        {
            "email": EMAIL,
            "password": PASSWORD,
            "mcq": mcq.pk,
            "interactive": inter.pk,
            "mcq_count": mcq.items.count(),
            "interactive_count": inter.items.count(),
        }
    )
)
