import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.migrations.loader import MigrationLoader

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_user_model_is_custom_email_user():
    assert User._meta.label == "accounts.User"
    assert User.USERNAME_FIELD == "email"
    assert not hasattr(User, "username")


def test_user_model_is_created_in_the_first_migration():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    first = loader.disk_migrations[("accounts", "0001_initial")]
    assert first.initial
    assert not first.dependencies or all(app != "accounts" for app, _ in first.dependencies)
    assert "user" in {op.name.lower() for op in first.operations if hasattr(op, "name")}


def test_create_user_defaults():
    user = User.objects.create_user("Asha@Example.com", "a-long-password-1")
    assert user.email_normalized == "asha@example.com"
    assert user.role == "learner"
    assert user.status == "active"
    assert not user.is_staff and not user.is_superuser
    assert user.check_password("a-long-password-1")


def test_create_superuser_is_admin_staff():
    user = User.objects.create_superuser("root@example.com", "a-long-password-1")
    assert user.is_staff and user.is_superuser
    assert user.role == "admin"


def test_email_is_unique_case_insensitively():
    User.objects.create_user("dup@example.com", "a-long-password-1")
    with pytest.raises(IntegrityError):
        User.objects.create_user("DUP@example.com", "a-long-password-1")


def test_email_required():
    with pytest.raises(ValueError):
        User.objects.create_user("", "a-long-password-1")
