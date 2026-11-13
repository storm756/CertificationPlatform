"""Architecture 18, journeys 1-4, plus the registration rules of 7.2 and 7.3."""

import re
from datetime import date, timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts import guardian
from apps.accounts.models import ConsentRecord, GuardianConsent, Profile, User, UserStatus
from apps.accounts.rules import may_track_time
from apps.audit.models import AuditEvent
from apps.batches.models import Batch, Enrolment

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def years_ago(years, extra_days=0):
    today = timezone.localdate()
    return today.replace(year=today.year - years) - timedelta(days=extra_days)


def form_data(batch, **over):
    data = {
        "certificate_name": "Asha R. Desai",
        "email": "asha@example.com",
        "password": PASSWORD,
        "preferred_language": "en",
        "date_of_birth": years_ago(25).isoformat(),
        "batch": batch.pk,
        "accept_privacy": "on",
    }
    data.update(over)
    return data


def confirm_link(message):
    link = re.search(r"https?://\S+/accounts/confirm-email/\S+/", message.body).group(0)
    return "/" + link.split("/", 3)[3]


# --- Journey 1 --------------------------------------------------------------------------


def test_journey1_nothing_open_means_no_form(client, make_batch):
    make_batch(accepting=False)
    response = client.get(reverse("register"))
    assert response.status_code == 200
    assert b"closed right now" in response.content
    assert b"<form" not in response.content.split(b"<main")[1].split(b"</main>")[0]


def test_journey1_the_open_pool_is_closed_by_default(client, db):
    pool = Batch.objects.get(is_open_pool=True)
    assert pool.accepting is False
    assert b"closed right now" in client.get(reverse("register")).content


def test_journey1_direct_post_with_nothing_open_is_refused(client, make_batch):
    batch = make_batch(accepting=False)
    response = client.post(reverse("register"), form_data(batch))
    assert response.status_code == 403
    assert not User.objects.filter(email="asha@example.com").exists()


def test_public_allauth_signup_is_closed(client, make_batch):
    make_batch()
    response = client.post(
        reverse("account_signup"),
        {"email": "x@example.com", "password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("register")
    assert not User.objects.filter(email="x@example.com").exists()


# --- Journey 2 --------------------------------------------------------------------------


def test_journey2_adult_registers_verifies_and_the_mentor_sees_them(
    client, make_batch, mentor_client, mentor
):
    batch = make_batch(mentor=mentor)
    other = client.__class__()
    response = other.post(reverse("register"), form_data(batch))
    assert response.status_code == 200
    assert b"Check your inbox" in response.content

    user = User.objects.get(email="asha@example.com")
    assert user.status == UserStatus.ACTIVE
    assert Enrolment.objects.get(user=user).batch == batch
    profile = Profile.objects.get(user=user)
    assert profile.certificate_name == "Asha R. Desai"
    assert ConsentRecord.objects.filter(user=user, purpose="privacy_notice", given=True).exists()
    assert len(mail.outbox) == 1  # the verification email only

    # cannot sign in before verifying
    login = other.post(
        reverse("account_login"), {"login": "asha@example.com", "password": PASSWORD}
    )
    assert "confirm-email" in login["Location"]

    path = confirm_link(mail.outbox[0])
    assert other.get(path).status_code == 200
    response = other.post(path, follow=True)
    assert EmailAddress.objects.get(email="asha@example.com").verified
    # lands on the welcome page with the pre-test prompt
    assert response.redirect_chain[-1][0] == reverse("start")
    assert b"pre-test" in response.content

    roster = mentor_client.get(reverse("mentor_batch", args=[batch.pk]))
    assert b"Asha R. Desai" in roster.content


def test_certificate_name_preview_is_on_the_form(client, make_batch):
    make_batch()
    html = client.get(reverse("register")).content.decode()
    assert 'id="name-preview"' in html
    assert "This exact name will be printed on your certificate" in html


def test_registering_with_an_existing_email_looks_the_same(client, make_batch, make_user):
    batch = make_batch()
    make_user(email="asha@example.com")
    response = client.post(reverse("register"), form_data(batch))
    assert b"Check your inbox" in response.content
    assert User.objects.filter(email="asha@example.com").count() == 1
    assert [m.subject for m in mail.outbox] == ["You already have an account"]
    # a second attempt inside 24 h sends nothing more to that address
    client.post(reverse("register"), form_data(batch))
    assert len(mail.outbox) == 1


def test_gmail_aliases_count_as_one_address_when_normalising(client, make_batch, settings):
    settings.EMAIL_NORMALISE_ALIASES = True
    batch = make_batch()
    client.post(reverse("register"), form_data(batch, email="a.sha@gmail.com"))
    client.post(reverse("register"), form_data(batch, email="asha+two@gmail.com"))
    assert User.objects.count() == 1
    assert User.objects.get().email_normalized == "asha@gmail.com"


def test_aliases_stay_separate_when_normalising_is_off(client, make_batch, settings):
    settings.EMAIL_NORMALISE_ALIASES = False
    batch = make_batch()
    client.post(reverse("register"), form_data(batch, email="asha+t1@gmail.com"))
    client.post(reverse("register"), form_data(batch, email="asha+t2@gmail.com"))
    assert User.objects.count() == 2


def test_under_16_is_refused_and_nothing_is_created(client, make_batch):
    batch = make_batch()
    response = client.post(
        reverse("register"), form_data(batch, date_of_birth=years_ago(15).isoformat())
    )
    assert b"You must be 16 or older to join." in response.content
    assert User.objects.count() == 0


def test_exactly_16_today_is_accepted(client, make_batch):
    batch = make_batch()
    guardian_fields = {"guardian_name": "Ravi Desai", "guardian_email": "ravi@example.com"}
    client.post(
        reverse("register"),
        form_data(batch, date_of_birth=years_ago(16).isoformat(), **guardian_fields),
    )
    assert User.objects.filter(email="asha@example.com").exists()


def test_a_full_batch_is_refused(client, make_batch, make_user):
    batch = make_batch(seat_limit=1)
    make_batch()  # another open batch keeps the form served
    make_user(batch=batch)
    response = client.post(reverse("register"), form_data(batch))
    assert b"not accepting registrations" in response.content
    assert not User.objects.filter(email="asha@example.com").exists()


# --- Journey 3 --------------------------------------------------------------------------


def test_journey3_a_17_year_old_waits_for_the_guardian(client, make_batch):
    batch = make_batch()
    data = form_data(
        batch,
        date_of_birth=years_ago(17, 30).isoformat(),
        guardian_name="Ravi Desai",
        guardian_email="ravi@example.com",
    )
    assert client.post(reverse("register"), data).status_code == 200
    user = User.objects.get(email="asha@example.com")
    assert user.status == UserStatus.PENDING_GUARDIAN
    assert not may_track_time(user, timezone.localdate())  # no heartbeat for under-18s

    verification, guardian_mail = sorted(mail.outbox, key=lambda m: m.to != ["asha@example.com"])
    assert guardian_mail.to == ["ravi@example.com"]
    token = re.search(r"/guardian/(\S+)/", guardian_mail.body).group(1)

    # verified, signed in, but only the waiting page is reachable
    client.post(confirm_link(verification))
    client.post(reverse("account_login"), {"login": "asha@example.com", "password": PASSWORD})
    for path in ("/", "/start/", "/mentor/"):
        response = client.get(path)
        assert response.status_code == 302
        assert response["Location"] == reverse("waiting_for_guardian"), path
    assert client.get(reverse("waiting_for_guardian")).status_code == 200

    # the guardian reads the notice and confirms
    page = client.get(reverse("guardian_consent", args=[token]))
    assert b"What we collect" in page.content
    bad = client.post(reverse("guardian_consent", args=[token]), {"guardian_name": "Ravi Desai"})
    assert bad.status_code == 200  # declaration missing
    user.refresh_from_db()
    assert user.status == UserStatus.PENDING_GUARDIAN
    done = client.post(
        reverse("guardian_consent", args=[token]),
        {"guardian_name": "Ravi Desai", "declaration": "on"},
    )
    assert b"consent is recorded" in done.content
    user.refresh_from_db()
    assert user.status == UserStatus.ACTIVE
    assert GuardianConsent.objects.get(user=user).confirmed_at is not None
    assert AuditEvent.objects.filter(action="guardian.confirmed").exists()
    assert not may_track_time(user, timezone.localdate())  # still under 18

    # the link works once
    again = client.get(reverse("guardian_consent", args=[token]))
    assert again.status_code == 404
    assert client.get("/start/").status_code == 200


def test_guardian_link_expires(client, make_batch, settings):
    batch = make_batch()
    client.post(
        reverse("register"),
        form_data(
            batch,
            date_of_birth=years_ago(17).isoformat(),
            guardian_name="Ravi Desai",
            guardian_email="ravi@example.com",
        ),
    )
    token = re.search(r"/guardian/(\S+)/", mail.outbox[-1].body).group(1)
    consent = guardian.find_by_token(token)
    assert consent is not None
    later = timezone.now() + timedelta(days=settings.GUARDIAN_LINK_DAYS + 1)
    assert guardian.find_by_token(token, now=later) is None


def test_guardian_fields_are_required_for_16_and_17(client, make_batch):
    batch = make_batch()
    response = client.post(
        reverse("register"), form_data(batch, date_of_birth=years_ago(17).isoformat())
    )
    assert b"A guardian is needed" in response.content
    assert User.objects.count() == 0


def test_adults_are_tracked_from_18(make_user):
    adult = make_user(dob=date(2000, 1, 1))
    teen = make_user(dob=years_ago(17))
    assert may_track_time(adult, timezone.localdate())
    assert not may_track_time(teen, timezone.localdate())


# --- Journey 4 --------------------------------------------------------------------------


def test_journey4_batch_closes_while_the_form_is_open(client, make_batch):
    batch = make_batch()
    other = make_batch(code="T99")  # something else stays open so the form is still served
    assert b"<form" in client.get(reverse("register")).content

    batch.accepting = False  # the mentor closes it while the person is typing
    batch.save()

    response = client.post(reverse("register"), form_data(batch))
    assert b"Sorry, this batch is not accepting registrations." in response.content
    html = response.content.decode()
    assert "asha@example.com" in html  # input kept
    assert "Asha R. Desai" in html
    assert f'value="{batch.pk}" selected' in html or f'value="{batch.pk}"' in html
    assert not User.objects.filter(email="asha@example.com").exists()
    assert other.accepting


def test_closing_window_in_the_past_refuses(client, make_batch):
    batch = make_batch(closes_at=timezone.now() - timedelta(minutes=1))
    make_batch(code="T98")
    response = client.post(reverse("register"), form_data(batch))
    assert b"not accepting registrations" in response.content
    assert User.objects.count() == 0


def test_unverified_seats_older_than_48_hours_are_released(make_batch, make_user):
    from apps.batches.rules import is_accepting

    batch = make_batch(seat_limit=1)
    holder = make_user(batch=batch, verified=False)
    assert not is_accepting(batch, timezone.now())
    Enrolment.objects.filter(user=holder).update(joined_at=timezone.now() - timedelta(hours=49))
    assert is_accepting(batch, timezone.now())


def test_registration_is_rate_limited_per_batch(client, make_batch, settings):
    batch = make_batch()
    other_batch = make_batch()
    # same IP, many attempts at one batch
    for _ in range(90):
        client.post(reverse("register"), form_data(batch, date_of_birth="not-a-date"))
    limited = client.post(reverse("register"), form_data(batch))
    assert limited.status_code == 429
    # another batch from the same classroom Wi-Fi is not affected
    assert client.post(reverse("register"), form_data(other_batch)).status_code == 200


def test_registration_writes_audit_without_personal_data(client, make_batch):
    batch = make_batch()
    client.post(reverse("register"), form_data(batch))
    event = AuditEvent.objects.get(action="registration.created")
    assert event.data["batch_id"] == batch.pk
    assert "asha" not in str(event.data).lower()
