"""Invented learners for the dashboard screenshots (Stage 5). Development database only.

    docker compose -f deploy/compose.dev.yml exec -T web python manage.py shell \
        < tools/seed_dashboard.py

Creates three invented learners (new, midway, eligible) with the password below, two modules with
two published parts each, and invented anchor questions. Nothing here is from the real banks.
"""

from datetime import date

from allauth.account.models import EmailAddress
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Profile, User
from apps.assessments import programme
from apps.assessments.models import AssessmentPart, Attempt, AttemptStatus
from apps.batches.models import Batch, Enrolment
from apps.content.models import Module
from apps.questions import services as qservices
from apps.questions.models import Question

assert "dev" in settings.SETTINGS_MODULE, "development settings only"
PASSWORD = "s5-invented-pass-1"  # noqa: S105 (invented, development only)
batch, _ = Batch.objects.get_or_create(
    code="S5", defaults={"name": "Stage 5 batch", "accepting": True, "seat_limit": 40}
)
for n in (1, 2):
    module, _ = Module.objects.get_or_create(
        number=n, defaults={"slug": f"module-{n}", "title_key": "x", "order": n}
    )
    module.title = module.title or f"Invented module {n}"
    module.hours = module.hours or 2
    module.save()
    for name in ("Part A: multiple choice", "Part B: interactive"):
        AssessmentPart.objects.get_or_create(
            module=module,
            name=name,
            defaults={"marks": 50, "selection": "all", "is_published": True},
        )
for i in range(1, 5):
    stable = f"M1-S5A{i}"
    if not Question.objects.filter(stable_id=stable).exists():
        q = qservices.create_question(
            stable_id=stable, module=Module.objects.get(number=1), pool="final",
            body={
                "stem": f"Invented anchor {i}: pick the second option.",
                "options": [
                    {"id": f"o{k}", "text": f"Option {k} of anchor {i}"} for k in (1, 2, 3, 4)
                ],
                "correct": "o2",
                "hint": "Invented hint.",
                "gate": {},
            },
            tags={"pc": "PC1", "type": "R"},
        )  # fmt: skip
        Question.objects.filter(pk=q.pk).update(is_anchor=True)
        qservices.publish(Question.objects.get(pk=q.pk))


def learner(email):
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email, PASSWORD, role="learner")
        EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
        Profile.objects.create(
            user=user, certificate_name=email.split(".")[0].title() + " Invented",
            date_of_birth=date(1995, 1, 1), pretest_prompted_at=timezone.now(),
        )  # fmt: skip
        Enrolment.objects.create(user=user, batch=batch)
    Attempt.objects.filter(user=user).delete()
    return user


def submitted(user, score, *, part=None, kind=None, number=1, answered=True):
    return Attempt.objects.create(
        user=user, part=part, number=number,
        programme_assessment=programme.get_assessment(kind) if kind else None,
        status=AttemptStatus.SUBMITTED, score=score, counted=True, all_answered=answered,
        submitted_at=timezone.now(),
    )  # fmt: skip


learner("new.learner@example.com")
mid = learner("mid.learner@example.com")
parts = {
    p.name[:6] + str(p.module.number): p
    for p in AssessmentPart.objects.filter(module__number__in=(1, 2))
}
submitted(mid, 72, part=parts["Part A1"])
submitted(mid, 41, part=parts["Part B1"], answered=False)
done = learner("done.learner@example.com")
for p in parts.values():
    submitted(done, 78, part=p)
submitted(done, 35, kind="pretest")
submitted(done, 82, kind="final")
print("ok", PASSWORD)
