import pytest


@pytest.fixture(autouse=True)
def _fast_hashing(settings):
    # Argon2 is deliberately slow; tests don't need that.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _locmem_email(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
