"""Mentor pages (architecture 5, 7.4) and the scoping guarantee."""

import re
from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MentorResetLink, Profile, Role, User
from apps.audit.models import AuditEvent
from apps.batches.models import Batch, BatchMentor, Enrolment
from apps.batches.scoping import batches_for

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(make_batch, make_user, mentor):
    """Mentor owns B-mine; another mentor owns B-theirs."""
    other_mentor = make_user(role=Role.MENTOR)
    mine = make_batch(mentor=mentor, code="MINE", name="Mine")
    mine2 = make_batch(mentor=mentor, code="MINE2", name="Mine two")
    theirs = make_batch(mentor=other_mentor, code="THEIRS", name="Theirs")
    return {
        "mine": mine,
        "mine2": mine2,
        "theirs": theirs,
        "my_learner": make_user(batch=mine),
        "their_learner": make_user(batch=theirs),
    }


# --- scoping ----------------------------------------------------------------------------


def test_batches_for_scopes_by_role(world, mentor, make_user):
    admin = make_user(role=Role.ADMIN)
    learner = world["my_learner"]
    assert set(batches_for(mentor)) == {world["mine"], world["mine2"]}
    assert world["theirs"] in set(batches_for(admin))
    assert set(batches_for(admin)) == set(Batch.objects.all())
    assert not batches_for(learner).exists()


def test_mentor_cannot_see_another_batch(mentor_client, world):
    home = mentor_client.get(reverse("mentor_home"))
    assert b"MINE" in home.content
    assert b"THEIRS" not in home.content

    response = mentor_client.get(reverse("mentor_batch", args=[world["theirs"].pk]))
    assert response.status_code == 403
    assert AuditEvent.objects.filter(action="access.denied").exists()


def test_mentor_cannot_see_or_change_another_batchs_learner(mentor_client, world):
    learner = world["their_learner"]
    assert mentor_client.get(reverse("mentor_learner", args=[learner.pk])).status_code == 403
    for name in ("mentor_learner_move", "mentor_learner_name", "mentor_learner_reset_link"):
        response = mentor_client.post(
            reverse(name, args=[learner.pk]),
            {"batch": world["mine"].pk, "certificate_name": "Hacked"},
        )
        assert response.status_code == 403, name
    assert Enrolment.objects.get(user=learner).batch == world["theirs"]
    assert Profile.objects.get(user=learner).certificate_name != "Hacked"
    assert not MentorResetLink.objects.filter(user=learner).exists()


def test_mentor_cannot_change_settings_of_another_batch(mentor_client, world):
    response = mentor_client.post(
        reverse("mentor_batch_settings", args=[world["theirs"].pk]),
        {"accepting": "on", "seat_limit": 5},
    )
    assert response.status_code == 403
    world["theirs"].refresh_from_db()
    assert world["theirs"].accepting is True  # make_batch default; untouched
    assert world["theirs"].seat_limit == 40


def test_mentor_cannot_move_a_learner_into_a_batch_they_dont_mentor(mentor_client, world):
    learner = world["my_learner"]
    response = mentor_client.post(
        reverse("mentor_learner_move", args=[learner.pk]), {"batch": world["theirs"].pk}
    )
    assert response.status_code == 403
    assert Enrolment.objects.get(user=learner).batch == world["mine"]


def test_learners_cannot_open_mentor_pages(client, world):
    client.force_login(world["my_learner"])
    assert client.get(reverse("mentor_home")).status_code == 403


def test_anonymous_is_sent_to_login(client):
    response = client.get(reverse("mentor_home"))
    assert response.status_code == 302
    assert "login" in response["Location"]


# --- actions ----------------------------------------------------------------------------


def test_my_batches_page(mentor_client, world):
    html = mentor_client.get(reverse("mentor_home")).content.decode()
    assert "MINE2" in html and "Registration open" in html


def test_create_a_batch_assigns_the_mentor_and_starts_closed(mentor_client, mentor):
    response = mentor_client.post(
        reverse("mentor_batch_new"),
        {"name": "Spring cohort", "centre": "SAKEC", "seat_limit": 30},
    )
    assert response.status_code == 302
    batch = Batch.objects.get(name="Spring cohort")
    assert batch.accepting is False
    assert batch.seat_limit == 30
    assert BatchMentor.objects.filter(batch=batch, mentor=mentor).exists()
    assert batch in batches_for(mentor)
    event = AuditEvent.objects.get(action="batch.created")
    assert event.actor_id == mentor.pk and event.target_id == str(batch.pk)


def test_open_and_close_registration_with_a_window(mentor_client, world):
    url = reverse("mentor_batch_settings", args=[world["mine"].pk])
    opens = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    mentor_client.post(url, {"accepting": "on", "opens_at": opens, "seat_limit": 12})
    batch = world["mine"]
    batch.refresh_from_db()
    assert batch.accepting and batch.seat_limit == 12 and batch.opens_at is not None
    from apps.batches.rules import is_accepting

    assert not is_accepting(batch, timezone.now())  # window hasn't started
    mentor_client.post(url, {"seat_limit": 12})
    batch.refresh_from_db()
    assert batch.accepting is False
    assert AuditEvent.objects.filter(action="batch.registration_updated").count() == 2


def test_a_window_that_closes_before_it_opens_is_rejected(mentor_client, world):
    response = mentor_client.post(
        reverse("mentor_batch_settings", args=[world["mine"].pk]),
        {
            "accepting": "on",
            "opens_at": "2030-01-02T10:00",
            "closes_at": "2030-01-01T10:00",
            "seat_limit": 10,
        },
    )
    assert response.status_code == 400


def test_a_mentor_cannot_open_the_catch_all_pool(mentor_client, mentor):
    pool = Batch.objects.get(is_open_pool=True)
    BatchMentor.objects.create(batch=pool, mentor=mentor)
    response = mentor_client.post(
        reverse("mentor_batch_settings", args=[pool.pk]), {"accepting": "on", "seat_limit": 40}
    )
    assert response.status_code == 403
    pool.refresh_from_db()
    assert pool.accepting is False


def test_move_a_learner_between_own_batches(mentor_client, world):
    learner = world["my_learner"]
    response = mentor_client.post(
        reverse("mentor_learner_move", args=[learner.pk]), {"batch": world["mine2"].pk}
    )
    assert response.status_code == 302
    assert Enrolment.objects.get(user=learner).batch == world["mine2"]
    event = AuditEvent.objects.get(action="learner.moved")
    assert event.data == {"from_batch": world["mine"].pk, "to_batch": world["mine2"].pk}


def test_roster_shows_new_signups_and_unverified_flags(mentor_client, world, make_user):
    make_user(batch=world["mine"], verified=False)
    html = mentor_client.get(reverse("mentor_batch", args=[world["mine"].pk])).content.decode()
    assert "New sign-ups" in html
    assert "email not verified" in html


def test_change_certificate_name_is_logged(mentor_client, world):
    learner = world["my_learner"]
    mentor_client.post(
        reverse("mentor_learner_name", args=[learner.pk]), {"certificate_name": "  Asha  Rao "}
    )
    assert Profile.objects.get(user=learner).certificate_name == "Asha Rao"
    event = AuditEvent.objects.get(action="learner.certificate_name_changed")
    assert "Asha" not in str(event.data)  # IDs, not names


def test_admin_can_work_across_batches(client, make_user, world):
    admin = make_user(role=Role.ADMIN)
    from allauth.mfa.models import Authenticator

    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    learner = world["their_learner"]
    assert client.get(reverse("mentor_learner", args=[learner.pk])).status_code == 200
    response = client.post(
        reverse("mentor_learner_move", args=[learner.pk]), {"batch": world["mine"].pk}
    )
    assert response.status_code == 302


# --- one-time reset link (7.4) ------------------------------------------------------------


def _issue_link(mentor_client, learner):
    response = mentor_client.post(reverse("mentor_learner_reset_link", args=[learner.pk]))
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    return re.search(r"/reset/([\w-]+)/", response.content.decode()).group(0)


def test_reset_link_changes_the_password_once(mentor_client, world, client):
    learner = world["my_learner"]
    path = _issue_link(mentor_client, learner)
    stored = MentorResetLink.objects.get(user=learner)
    assert path.split("/")[2] not in stored.token_hash  # only a hash is stored
    assert stored.expires_at - timezone.now() <= timedelta(hours=1)

    learner_browser = client.__class__()
    learner_browser.force_login(learner)
    assert learner_browser.get("/start/").status_code == 200

    new_password = "an-entirely-new-passw0rd"
    response = learner_browser.post(
        path, {"new_password1": new_password, "new_password2": new_password}
    )
    assert response.status_code == 302
    learner.refresh_from_db()
    assert learner.check_password(new_password)

    # every session of the learner is gone, so the old browser is signed out
    assert learner_browser.get("/start/").status_code == 302
    assert not any(
        s.get_decoded().get("_auth_user_id") == str(learner.pk) for s in Session.objects.all()
    )

    # single use
    assert learner_browser.get(path).status_code == 404
    assert AuditEvent.objects.filter(action="password.mentor_reset_used").exists()


def test_reset_link_expires_after_an_hour(mentor_client, world, client):
    learner = world["my_learner"]
    path = _issue_link(mentor_client, learner)
    MentorResetLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert client.get(path).status_code == 404


def test_after_a_mentor_reset_a_banner_shows_and_email_change_is_blocked(
    mentor_client, world, client
):
    learner = world["my_learner"]
    path = _issue_link(mentor_client, learner)
    browser = client.__class__()
    password = "an-entirely-new-passw0rd"
    browser.post(path, {"new_password1": password, "new_password2": password})

    browser.post(reverse("account_login"), {"login": learner.email, "password": password})
    page = browser.get("/start/")
    assert b"reset by your mentor" in page.content
    browser.post(reverse("dismiss_reset_notice"))
    assert b"reset by your mentor" not in browser.get("/start/").content

    # email change blocked for 7 days
    response = browser.post(
        reverse("account_email"), {"action_add": "", "email": "new@example.com"}
    )
    assert response.status_code == 302
    assert not learner.emailaddress_set.filter(email="new@example.com").exists()

    Profile.objects.filter(user=learner).update(mentor_reset_at=timezone.now() - timedelta(days=8))
    browser.post(reverse("account_email"), {"action_add": "", "email": "new@example.com"})
    assert learner.emailaddress_set.filter(email="new@example.com").exists()


def test_user_model_password_helper_sanity(world):
    assert User.objects.get(pk=world["my_learner"].pk).check_password(PASSWORD)


# --- move learner responses ---------------------------------------------------------------


@pytest.mark.parametrize("data", [{}, {"batch": ""}])
def test_move_with_no_batch_chosen_shows_form_again_with_400(mentor_client, world, data):
    learner = world["my_learner"]
    response = mentor_client.post(reverse("mentor_learner_move", args=[learner.pk]), data)
    assert response.status_code == 400
    assert "Pick a batch." in response.content.decode()
    assert Enrolment.objects.get(user=learner).batch == world["mine"]
    assert not AuditEvent.objects.filter(action="learner.moved").exists()
    assert not AuditEvent.objects.filter(action="access.denied").exists()


def test_move_to_unknown_or_foreign_batch_gives_the_same_403_and_audits(mentor_client, world):
    learner = world["my_learner"]
    url = reverse("mentor_learner_move", args=[learner.pk])
    foreign = mentor_client.post(url, {"batch": world["theirs"].pk})
    unknown = mentor_client.post(url, {"batch": 999999})
    garbage = mentor_client.post(url, {"batch": "not-a-number"})
    assert foreign.status_code == unknown.status_code == garbage.status_code == 403
    assert foreign.content == unknown.content == garbage.content
    assert AuditEvent.objects.filter(action="access.denied").count() == 3
    assert Enrolment.objects.get(user=learner).batch == world["mine"]
