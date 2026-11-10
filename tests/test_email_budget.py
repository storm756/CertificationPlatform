import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts import email_budget
from apps.accounts.models import EmailLog, Role

pytestmark = pytest.mark.django_db


def test_daily_pools_are_enforced(settings):
    settings.EMAIL_DAILY_BUDGET = {"registration": 2, "reset_guardian": 1, "reserve": 1}
    for _ in range(2):
        assert email_budget.can_send(email_budget.REGISTRATION, "a@example.com")
        email_budget.record(email_budget.REGISTRATION, "a@example.com")
    assert not email_budget.can_send(email_budget.REGISTRATION, "b@example.com")
    # the other pool is untouched
    assert email_budget.can_send(email_budget.GUARDIAN, "g@example.com")


def test_reset_and_duplicate_are_limited_to_one_per_address_per_day():
    assert email_budget.can_send(email_budget.RESET, "a@example.com")
    email_budget.record(email_budget.RESET, "a@example.com")
    assert not email_budget.can_send(email_budget.RESET, "A@example.com ")
    assert email_budget.can_send(email_budget.RESET, "b@example.com")


def test_password_reset_email_is_limited_per_address(client, make_user):
    make_user(email="a@example.com")
    for _ in range(3):
        client.post(reverse("account_reset_password"), {"email": "a@example.com"})
    assert len(mail.outbox) == 1
    assert EmailLog.objects.filter(kind=email_budget.RESET).count() == 1


def test_registration_is_paused_when_the_pool_is_used_up(client, make_batch, settings):
    settings.EMAIL_DAILY_BUDGET = {"registration": 0, "reset_guardian": 100, "reserve": 50}
    batch = make_batch()
    from .test_registration import form_data

    response = client.post(reverse("register"), form_data(batch))
    assert b"very busy today" in response.content
    from apps.accounts.models import User

    assert not User.objects.filter(email="asha@example.com").exists()


def test_sent_today_counts_by_pool():
    email_budget.record(email_budget.REGISTRATION, "a@example.com")
    email_budget.record(email_budget.RESET, "b@example.com")
    email_budget.record(email_budget.GUARDIAN, "c@example.com")
    counts = email_budget.sent_today()
    assert counts["registration"] == 1 and counts["reset_guardian"] == 2
    assert counts["total"] == 3


def test_admins_are_alerted_once_when_the_total_reaches_the_threshold(settings, make_user):
    settings.EMAIL_ALERT_AT = 3
    make_user(role=Role.ADMIN, email="boss@example.com")
    for i in range(5):
        email_budget.record(email_budget.REGISTRATION, f"u{i}@example.com")
    alerts = [m for m in mail.outbox if m.to == ["boss@example.com"]]
    assert len(alerts) == 1


def test_dashboard_shows_the_sent_today_counter(client, make_user):
    from allauth.account.models import EmailAddress
    from allauth.mfa.models import Authenticator

    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True, email="root@example.com")
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    EmailAddress.objects.filter(user=admin).update(verified=True)
    email_budget.record(email_budget.REGISTRATION, "a@example.com")
    client.force_login(admin)
    html = client.get("/admin/").content.decode()
    assert "Emails sent today" in html
    assert "<strong>1</strong> of 300" in html


def test_purge_unverified_removes_only_stale_unverified_learners(make_user):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from apps.accounts.models import User

    stale = make_user(verified=False)
    fresh = make_user(verified=False)
    verified = make_user(verified=True)
    User.objects.filter(pk__in=[stale.pk, verified.pk]).update(
        created_at=timezone.now() - timedelta(days=8)
    )
    call_command("purge_unverified")
    assert set(User.objects.values_list("pk", flat=True)) == {fresh.pk, verified.pk}
