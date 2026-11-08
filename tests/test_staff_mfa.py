import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db
User = get_user_model()


def _login(client, user):
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client.force_login(user)


def test_admin_login_url_goes_through_allauth(client):
    response = client.get("/admin/login/")
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("account_login"))


def test_staff_without_totp_is_forced_to_set_it_up(client):
    staff = User.objects.create_superuser("admin@example.com", "a-long-password-1")
    _login(client, staff)
    for path in ("/admin/", "/"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response["Location"] == reverse("mfa_activate_totp")


def test_mfa_setup_pages_stay_reachable_for_staff(client):
    staff = User.objects.create_superuser("admin@example.com", "a-long-password-1")
    _login(client, staff)
    # allauth asks for a recent re-login first; that page lives under /accounts/ so it is reachable
    response = client.get(reverse("mfa_activate_totp"))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("account_reauthenticate"))
    assert client.get(response["Location"]).status_code == 200


def test_staff_with_totp_reaches_the_admin(client):
    staff = User.objects.create_superuser("admin@example.com", "a-long-password-1")
    _login(client, staff)
    Authenticator.objects.create(user=staff, type=Authenticator.Type.TOTP, data={"secret": "x"})
    assert client.get("/admin/").status_code == 200


def test_learner_is_not_forced_into_mfa(client):
    learner = User.objects.create_user("learner@example.com", "a-long-password-1")
    _login(client, learner)
    assert client.get("/").status_code == 200


def test_staff_session_is_limited_to_12_hours(client, settings):
    staff = User.objects.create_superuser("admin@example.com", "a-long-password-1")
    _login(client, staff)
    client.get(reverse("mfa_activate_totp"))
    assert client.session.get_expiry_age() <= settings.STAFF_SESSION_AGE
