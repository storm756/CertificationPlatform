"""Security audit 2026-11, second PR: the email budget (M1), the sign-up limit key (M2), email
changes (M3) and the reset-notice redirect (L1). See docs/security-audit-2026-11.md."""

import re

import pytest
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts import email_budget
from apps.accounts.models import EmailLog
from apps.accounts.views import _rate_key

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


# --- M1: a reset for an unknown address sends nothing and uses no budget ------------------------


def test_unknown_address_reset_sends_no_email_and_uses_no_budget(client):
    client.post(reverse("account_reset_password"), {"email": "nobody@example.com"})
    assert mail.outbox == []
    assert email_budget.sent_today()["reset_guardian"] == 0
    assert EmailLog.objects.filter(kind=email_budget.RESET_UNKNOWN).count() == 1


def test_a_flood_of_unknown_resets_cannot_block_a_real_one(client, make_user, rf, settings):
    request = rf.post("/accounts/password/reset/")
    request.session = client.session
    adapter = get_adapter(request)
    for n in range(settings.EMAIL_DAILY_BUDGET["reset_guardian"] + 20):
        adapter.send_mail("account/email/unknown_account", f"x{n}@example.invalid", {})
    assert mail.outbox == []
    assert email_budget.has_room(email_budget.RESET)

    make_user(email="real@example.com")
    client.post(reverse("account_reset_password"), {"email": "real@example.com"})
    assert [m.to for m in mail.outbox] == [["real@example.com"]]


# --- M2: one sign-up allowance per batch, however the number is written --------------------------


@pytest.mark.parametrize("value", ["2", "02", "002", " 2", "2 "])
def test_rate_key_is_the_batch_number(value):
    request = RequestFactory().post("/register/", {"batch": value})
    assert _rate_key(None, request) == "batch:2"


@pytest.mark.parametrize("value", ["", "abc", "+2", "2.0", "２"])
def test_rate_key_puts_every_odd_value_in_one_bucket(value):
    request = RequestFactory().post("/register/", {"batch": value})
    assert _rate_key(None, request) == "batch:invalid"


# --- M3: one address per account; the old address hears about changes ----------------------------


def _confirm_link(message):
    return re.search(r"https?://[^/\s]+(/accounts/confirm-email/[^\s]+/)", message.body).group(1)


def test_an_email_change_replaces_the_address_and_tells_the_old_one(client, make_user):
    user = make_user(email="old@example.com")
    client.force_login(user)
    url = reverse("account_email")
    client.post(url, {"action_add": "", "email": "first-try@example.com"})
    client.post(url, {"action_add": "", "email": "new@example.com"})
    assert EmailAddress.objects.filter(user=user).count() == 2  # the old one and one pending
    assert not EmailAddress.objects.filter(email="first-try@example.com").exists()

    confirmation = next(m for m in mail.outbox if m.to == ["new@example.com"])
    mail.outbox.clear()
    client.post(_confirm_link(confirmation))

    assert list(EmailAddress.objects.filter(user=user).values_list("email", flat=True)) == [
        "new@example.com"
    ]
    notices = [m for m in mail.outbox if m.to == ["old@example.com"]]
    assert notices, "the old address must be told its email was changed"


def test_a_password_change_is_notified(client, make_user):
    user = make_user(email="pw@example.com")
    client.force_login(user)
    client.post(
        reverse("account_change_password"),
        {
            "oldpassword": PASSWORD,
            "password1": "A-new-long-pass-91",
            "password2": "A-new-long-pass-91",
        },
    )
    assert [m.to for m in mail.outbox] == [["pw@example.com"]]
    # a notice is not a reset: a real reset link can still go out the same day
    assert email_budget.can_send(email_budget.RESET, "pw@example.com")


# --- L1: the reset notice's "next" never leaves the site ----------------------------------------


@pytest.mark.parametrize(
    "target", ["https://evil.example/", "//evil.example/x", "javascript:alert(1)"]
)
def test_dismiss_notice_refuses_an_off_site_next(client, make_user, target):
    client.force_login(make_user())
    response = client.post(reverse("dismiss_reset_notice"), {"next": target})
    assert response["Location"] == reverse("start")


def test_dismiss_notice_keeps_an_on_site_next(client, make_user):
    client.force_login(make_user())
    response = client.post(reverse("dismiss_reset_notice"), {"next": "/learn/"})
    assert response["Location"] == "/learn/"
