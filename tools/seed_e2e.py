"""Invented data for the browser check tools/e2e_save_retry.mjs. Development database only.

    docker compose -f deploy/compose.dev.yml exec -T web python manage.py shell < tools/seed_e2e.py

Creates an invented learner and a published invented multiple-choice part, starts a fresh attempt
(deleting any earlier ones) and prints one JSON line. Nothing here is from the real question bank.
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

assert "dev" in settings.SETTINGS_MODULE, "development settings only"
EMAIL, PASSWORD = "e2e.learner@example.com", "e2e-invented-pass-1"  # noqa: S105
module = Module.objects.get(number=1)
for n in range(1, 6):
    sid = f"M1-E{n:02d}"
    if Question.objects.filter(stable_id=sid).exists():
        continue
    q = qservices.create_question(
        stable_id=sid,
        module=module,
        pool="module_quiz",
        tags={"pc": "PC1", "type": "R"},
        body={
            "stem": f"E2E question {n}: pick the second option.",
            "options": [{"id": f"o{i}", "text": f"E2E {n} option {i}"} for i in (1, 2, 3, 4)],
            "correct": "o2",
            "hint": f"E2E hint {n}.",
            "gate": {},
        },
    )
    qservices.publish(q)
part = AssessmentPart.objects.filter(name="E2E multiple choice").first()
if part is None:
    part = AssessmentPart.objects.create(
        module=module, name="E2E multiple choice", marks=50, selection="all"
    )
    rules.publish_part(part)
user = User.objects.filter(email=EMAIL).first()
if user is None:
    user = User.objects.create_user(EMAIL, PASSWORD, role="learner")
    EmailAddress.objects.create(user=user, email=EMAIL, primary=True, verified=True)
    Profile.objects.create(
        user=user, certificate_name="E2E Learner", date_of_birth=date(2000, 1, 1)
    )
    batch, _ = Batch.objects.get_or_create(code="E2E", defaults={"name": "E2E", "accepting": True})
    Enrolment.objects.create(user=user, batch=batch)
Attempt.objects.filter(user=user).delete()
attempt, _ = services.start(user, part)
print(
    json.dumps(
        {
            "email": EMAIL,
            "password": PASSWORD,
            "attempt": attempt.pk,
            "count": attempt.items.count(),
        }
    )
)
