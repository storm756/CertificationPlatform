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
