from datetime import date

import pytest
from allauth.account.models import EmailAddress
from django.core.cache import cache

from apps.accounts.models import Profile, Role, User
from apps.batches.models import Batch, BatchMentor, Enrolment

PASSWORD = "correct-horse-battery-9"


@pytest.fixture(autouse=True)
def _fast_hashing(settings):
    # Argon2 is deliberately slow; tests don't need that.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _locmem_email(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # django-ratelimit counters live here


@pytest.fixture
def make_batch(db):
    counter = {"n": 10}

    def make(accepting=True, seat_limit=40, mentor=None, **extra):
        counter["n"] += 1
        batch = Batch.objects.create(
            code=extra.pop("code", f"T{counter['n']}"),
            name=extra.pop("name", f"Test batch {counter['n']}"),
            accepting=accepting,
            seat_limit=seat_limit,
            **extra,
        )
        if mentor:
            BatchMentor.objects.create(batch=batch, mentor=mentor)
        return batch

    return make


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def make(role=Role.LEARNER, batch=None, verified=True, dob=date(2000, 1, 1), **extra):
        counter["n"] += 1
        email = extra.pop("email", f"{role}{counter['n']}@example.com")
        user = User.objects.create_user(email, PASSWORD, role=role, **extra)
        EmailAddress.objects.create(user=user, email=email, primary=True, verified=verified)
        if role == Role.LEARNER:
            Profile.objects.create(
                user=user, certificate_name=f"Learner {counter['n']}", date_of_birth=dob
            )
        if batch is not None:
            Enrolment.objects.create(user=user, batch=batch)
        return user

    return make


@pytest.fixture
def mentor(make_user):
    return make_user(role=Role.MENTOR)


@pytest.fixture
def mentor_client(client, mentor):
    """A signed-in mentor who has TOTP set up, so the 2FA gate lets them through."""
    from allauth.mfa.models import Authenticator

    Authenticator.objects.create(user=mentor, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(mentor)
    return client


# --- Stage 2 fixtures: invented questions only (real ones are private and never in tests) ------

RIGHT = "RIGHT-{n}-xq"  # the correct option's text; a unique marker so leaks are easy to spot
WRONG = "WRONG-{n}-{k}-xq"
HINT = "HINT-{n}-xq"


@pytest.fixture
def module1(db):
    from apps.content.models import Module

    # get_or_create: a transactional test (threads) flushes the seeded modules away afterwards.
    module, _ = Module.objects.get_or_create(
        number=1,
        defaults={"slug": "module-1", "title_key": "module.1.title", "order": 1},
    )
    return module


@pytest.fixture
def make_question(db, module1):
    from apps.questions import services

    def make(
        n, *, module=None, pc="PC1", pool="module_quiz", hint=True, live=True, gate=None, points=1
    ):
        options = [
            {"id": "o1", "text": WRONG.format(n=n, k=1)},
            {"id": "o2", "text": RIGHT.format(n=n)},
        ]
        options += [{"id": f"o{i}", "text": WRONG.format(n=n, k=i - 1)} for i in (3, 4)]
        body = {
            "stem": f"Invented question number {n}: pick the right marker.",
            "options": options,
            "correct": "o2",  # deliberately not the first option
            "hint": HINT.format(n=n) if hint else "",
            "gate": {f"o{g}": "Invented risk: this would endanger someone." for g in (gate or [])},
        }
        question = services.create_question(
            stable_id=f"M{(module or module1).number}-T{n:02d}",
            module=module or module1,
            body=body,
            tags={"pc": pc, "type": "R"},
            pool=pool,
            points=points,
        )
        if live:
            services.publish(question)
        return question

    return make


@pytest.fixture
def make_part(db, module1, make_question):
    from apps.assessments import rules
    from apps.assessments.models import AssessmentPart

    def make(
        questions=12, draw_n=5, min_per_tag=1, publish=True, selection="draw", marks=50, **extra
    ):
        pcs = ["PC1", "PC2", "PC3"]
        existing = module1.questions.count()
        for i in range(questions):
            make_question(existing + i + 1, pc=pcs[i % 3])
        part = AssessmentPart.objects.create(
            module=module1,
            name=extra.pop("name", "Part A: multiple choice"),
            marks=marks,
            selection=selection,
            draw_n=draw_n if selection == "draw" else None,
            min_per_tag=min_per_tag,
            **extra,
        )
        if publish:
            rules.publish_part(part)
        return part

    return make


@pytest.fixture
def learner(make_user, make_batch):
    return make_user(batch=make_batch())


@pytest.fixture
def learner_client(client, learner):
    client.force_login(learner)
    return client


def right_token(item):
    """Test helper: the token of the correct option (the tests may look at the key; browsers can't)."""
    body = item.question_version.body
    return next(t for t, key in item.option_map["tokens"].items() if key == body["correct"])


def wrong_token(item):
    body = item.question_version.body
    return next(t for t, key in item.option_map["tokens"].items() if key != body["correct"])
