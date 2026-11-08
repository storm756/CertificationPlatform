import re

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Cyber First Response" in response.content


def test_healthz_checks_database(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"


def test_signup_verify_login_logout(client):
    # signup
    response = client.post(
        reverse("account_signup"),
        {"email": "learner@example.com", "password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 1

    # cannot log in before verifying
    response = client.post(
        reverse("account_login"), {"login": "learner@example.com", "password": PASSWORD}
    )
    assert response.status_code == 302
    assert "confirm-email" in response["Location"]
    assert "_auth_user_id" not in client.session

    # verify through the emailed link (HTTP GET shows a page, POST confirms)
    link = re.search(r"http://\S+/accounts/confirm-email/\S+/", mail.outbox[0].body).group(0)
    path = link.split("testserver", 1)[-1]
    assert client.get(path).status_code == 200
    client.post(path)
    assert EmailAddress.objects.get(email="learner@example.com").verified

    # login
    response = client.post(
        reverse("account_login"), {"login": "learner@example.com", "password": PASSWORD}
    )
    assert response.status_code == 302
    assert "_auth_user_id" in client.session

    # logout (POST only)
    assert client.get(reverse("account_logout")).status_code == 200  # confirmation page
    client.post(reverse("account_logout"))
    assert "_auth_user_id" not in client.session
