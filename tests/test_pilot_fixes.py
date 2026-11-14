"""Pilot fixes: staff and assessments, the staff catalogue and header, the reset message,
SUPPORT_EMAIL, email naming, test-learner removal and the import report."""

import io
import re

import pytest
from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


def staff_client(client, make_user, role, **extra):
    user = make_user(role=role, **extra)
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(user)
    return client


@pytest.fixture
def admin_client(client, make_user):
    return staff_client(client, make_user, Role.ADMIN, is_staff=True, is_superuser=True)


@pytest.fixture
def mentor_c(client, make_user):
    return staff_client(client, make_user, Role.MENTOR)


# --- 403 page ---------------------------------------------------------------------------------


def test_a_403_uses_the_site_layout_and_links_home(mentor_c, make_part):
    part = make_part()
    response = mentor_c.post(reverse("assess_start", args=[part.pk]))
    html = response.content.decode()
    assert response.status_code == 403
    assert (
        "site-header" in html
        and "You can&#x27;t open this page" in html
        or "You can't open" in html
    )
    assert f'href="{reverse("home")}"' in html


# --- admin preview ----------------------------------------------------------------------------


def snapshot_counts():
    from apps.assessments.models import (
        Attempt,
        AttemptItem,
        ExamSet,
        LearnerExamSet,
        ProgrammeAssessment,
    )
    from apps.certificates.models import Certificate

    models = (Attempt, AttemptItem, LearnerExamSet, ExamSet, ProgrammeAssessment, Certificate)
    return [m.objects.count() for m in models]


def test_admin_opening_a_part_gets_a_preview_banner_and_no_answers(admin_client, make_part):
    part = make_part()
    before = snapshot_counts()
    audits = AuditEvent.objects.count()
    response = admin_client.get(reverse("assess_intro", args=[part.pk]), follow=True)
    html = response.content.decode()
    assert response.status_code == 200
    assert "Preview: nothing is saved or scored." in html
    assert "Invented question number" in html
    # every option is listed with no mark, so the key is not visible; no key field is rendered
    assert "WRONG-1-1-xq" in html and "RIGHT-1-xq" in html
    assert "checked" not in html and "data-correct" not in html
    assert snapshot_counts() == before and AuditEvent.objects.count() == audits


def test_the_preview_never_writes_rows(admin_client, make_part):
    part = make_part()
    url = reverse("preview_part", args=[part.pk])
    admin_client.get(url)  # warm up (session, etc.)
    with CaptureQueriesContext(connection) as queries:
        assert admin_client.get(url).status_code == 200
    writes = [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert all("django_session" in w for w in writes), writes


def test_admin_preview_of_pretest_and_final_makes_no_programme_rows(admin_client):
    before = snapshot_counts()
    for kind in ("pretest", "final"):
        response = admin_client.get(reverse("programme_intro", args=[kind]), follow=True)
        assert response.status_code == 200
        assert "Preview: nothing is saved or scored." in response.content.decode()
    assert snapshot_counts() == before
    assert admin_client.get("/exam/nonsense/", follow=True).status_code == 404


def test_a_mentor_gets_a_friendly_page_not_the_exam(mentor_c, make_part):
    part = make_part()
    for url in (
        reverse("assess_intro", args=[part.pk]),
        reverse("programme_intro", args=["final"]),
    ):
        response = mentor_c.get(url)
        html = response.content.decode()
        assert response.status_code == 403
        assert "Assessments are taken by learners" in html
        assert "mentor dashboard" in html.lower() and "Invented question" not in html
    assert mentor_c.get(reverse("preview_part", args=[part.pk])).status_code == 403
    assert mentor_c.get(reverse("preview_exam", args=["final"])).status_code == 403


def test_a_learner_still_sees_the_normal_intro(learner_client, make_part):
    part = make_part()
    response = learner_client.get(reverse("assess_intro", args=[part.pk]))
    assert response.status_code == 200
    assert "Preview: nothing is saved" not in response.content.decode()


def test_signed_out_goes_to_sign_in(client, make_part):
    part = make_part()
    assert client.get(reverse("preview_part", args=[part.pk])).status_code == 302


# --- staff catalogue and header ---------------------------------------------------------------


def test_catalogue_tells_staff_what_learners_see_and_gives_admins_a_preview_link(admin_client):
    text = "Learners see the pre-test and final once their batch has a released exam set."
    html = admin_client.get(reverse("learn_catalogue")).content.decode()
    assert text in html and "Coming soon. See what you know" not in html
    assert reverse("preview_exam", args=["final"]) in html


def test_catalogue_for_a_mentor_has_the_note_but_no_preview_link(mentor_c):
    html = mentor_c.get(reverse("learn_catalogue")).content.decode()
    assert "Learners see the pre-test and final" in html
    assert "/preview/exam/" not in html


def test_catalogue_for_a_learner_keeps_coming_soon(learner_client):
    html = learner_client.get(reverse("learn_catalogue")).content.decode()
    assert "Coming soon. See what you know before you start." in html
    assert "Learners see the pre-test" not in html


def test_admin_header_has_the_admin_dashboard_link_and_staff_menu(admin_client):
    html = admin_client.get(reverse("learn_catalogue")).content.decode()
    assert 'href="/admin/"' in html and "Staff tools" in html


def test_a_mentor_who_is_also_staff_gets_both_a_mentor_and_an_admin_link(client, make_user):
    c = staff_client(client, make_user, Role.MENTOR, is_staff=True)
    html = c.get(reverse("learn_catalogue")).content.decode()
    assert 'href="/admin/"' in html and reverse("mentor_home") in html


def test_a_plain_mentor_and_a_learner_get_no_admin_link(mentor_c, learner_client):
    assert 'href="/admin/"' not in mentor_c.get(reverse("learn_catalogue")).content.decode()
    assert 'href="/admin/"' not in learner_client.get(reverse("learn_catalogue")).content.decode()


def test_the_admin_dashboard_links_back_to_the_site(admin_client):
    response = admin_client.get("/admin/")
    assert response.status_code == 200 and 'id="back-to-site"' in response.content.decode()


# --- password reset, second request ------------------------------------------------------------

LIMITED = "we already sent a reset link today"


def reset_twice(client, address):
    url = reverse("account_reset_password")
    first = client.post(url, {"email": address}, follow=True).content.decode()
    second = client.post(url, {"email": address}, follow=True).content.decode()
    return first, second


def strip(html):
    html = re.sub(r"csrfmiddlewaretoken\" value=\"[^\"]+", "", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_second_reset_request_says_a_link_was_already_sent(client, make_user):
    make_user(email="known@example.com")
    first, second = reset_twice(client, "known@example.com")
    assert LIMITED not in first and LIMITED in second
    assert len(mail.outbox) == 1
    third = client.get(reverse("account_reset_password_done")).content.decode()
    assert LIMITED not in third  # shown once


def test_reset_response_is_identical_for_unknown_addresses(client, make_user):
    make_user(email="known@example.com")
    known = reset_twice(client, "known@example.com")
    unknown = reset_twice(client, "nobody@example.com")
    assert [strip(p) for p in known] == [strip(p) for p in unknown]
    assert LIMITED in unknown[1]


# --- SUPPORT_EMAIL and email naming ------------------------------------------------------------


def test_support_email_comes_from_settings(client, settings):
    assert settings.SUPPORT_EMAIL == "support@cyberfirstresponse.io"
    settings.SUPPORT_EMAIL = "help@example.org"
    html = client.get(reverse("grievance")).content.decode()
    assert "help@example.org" in html and "support@cyberfirstresponse.io" not in html


def test_emails_use_the_programme_short_name(client, make_user, settings):
    from django.contrib.sites.models import Site

    from apps.core.apps import sync_site

    sync_site(sender=None)
    make_user(email="named@example.com")
    client.post(reverse("account_reset_password"), {"email": "named@example.com"})
    message = mail.outbox[0]
    assert message.subject.startswith(f"[{settings.PROGRAMME_SHORT}]")
    assert message.from_email.startswith(f"{settings.PROGRAMME_SHORT} <")
    assert "Cyber First Response" not in message.subject + message.from_email
    assert Site.objects.get(pk=settings.SITE_ID).name == settings.PROGRAMME_SHORT


# --- + addresses and remove_test_learner --------------------------------------------------------


def test_registration_accepts_a_plus_address(client, make_batch, settings):
    from .test_registration import form_data

    settings.EMAIL_NORMALISE_ALIASES = True  # as on prod
    batch = make_batch()
    client.post(reverse("register"), form_data(batch, email="me+test1@gmail.com"))
    assert User.objects.filter(email="me+test1@gmail.com").exists()


def run(*args):
    out = io.StringIO()
    call_command("remove_test_learner", *args, stdout=out)
    return out.getvalue()


def test_remove_test_learner_previews_then_needs_yes(make_user, make_batch):
    user = make_user(batch=make_batch(), email="me+test1@gmail.com")
    text = run("me+test1@gmail.com")
    assert "will be deleted" in text and "Nothing deleted" in text
    assert User.objects.filter(pk=user.pk).exists()
    assert "Deleted." in run("me+test1@gmail.com", "--yes")
    assert not User.objects.filter(pk=user.pk).exists()
    assert AuditEvent.objects.filter(action="user.test_learner_removed").exists()


@pytest.mark.parametrize("role", [Role.MENTOR, Role.ADMIN])
def test_remove_test_learner_refuses_staff(make_user, role):
    user = make_user(role=role, email="staff@example.com")
    with pytest.raises(CommandError, match="not a learner"):
        run("staff@example.com", "--yes")
    assert User.objects.filter(pk=user.pk).exists()


def test_remove_test_learner_unknown_address(db):
    with pytest.raises(CommandError, match="No account"):
        run("nobody@example.com", "--yes")


def issue_certificate(user):
    from apps.certificates.models import Certificate

    return Certificate.objects.create(
        user=user, serial=999, certificate_no="CCFR-2026-T-000999", verify_code="ABCDE12345",
        snapshot={}, issued_at=timezone.now(),
    )  # fmt: skip


def test_remove_test_learner_refuses_a_certificate_holder_unless_told(make_user, make_batch):
    from apps.certificates.models import Certificate

    user = make_user(batch=make_batch(), email="holder@example.com")
    issue_certificate(user)
    with pytest.raises(CommandError, match="--include-certificate"):
        run("holder@example.com", "--yes")
    assert User.objects.filter(pk=user.pk).exists() and Certificate.objects.count() == 1
    text = run("holder@example.com", "--yes", "--include-certificate")
    assert "gap in the serial numbers" in text and "Deleted." in text
    assert not User.objects.filter(pk=user.pk).exists() and Certificate.objects.count() == 0


# --- the translation import report ---------------------------------------------------------------


def test_the_import_report_survives_an_unwritable_existing_file(tmp_path, monkeypatch):
    from pathlib import Path

    from apps.translations import drafts

    result = drafts.plan([])
    target = tmp_path / "report.csv"
    target.write_text("old")
    real_open = Path.open

    def fake_open(self, *args, **kwargs):
        if self == target and (args[:1] == ("w",) or kwargs.get("mode") == "w"):
            raise PermissionError("owned by another user")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)
    written = drafts.write_report(result, target)
    assert written != target and written.parent == tmp_path and written.exists()
    assert target.read_text() == "old"


def test_the_people_photos_are_webp_and_have_alt_text(client, tmp_path, settings):
    for name in ("bhavesh-patel.webp", "nilakshi-jain.webp", "vineet-kumar.webp"):
        (tmp_path / name).write_bytes(b"fake")
    settings.PEOPLE_PHOTO_DIR = tmp_path
    settings.PEOPLE_CONSENT_GIVEN = True
    html = client.get("/").content.decode()
    assert "Photo of Dr. Nilakshi Jain, HOD Cyber Security, SAKEC" in html
