"""Review fixes: purge vs verification, a failed guardian resend, the saved language, auto-submit."""

import smtplib
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.accounts import guardian, purge
from apps.accounts.models import EmailLog, GuardianConsent, User, UserStatus
from apps.assessments import services
from apps.assessments.models import Attempt, AttemptStatus

from .conftest import right_token

pytestmark = pytest.mark.django_db


# --- the purge job must not delete a learner who verifies while it is running --------------------


def age(user, days):
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=days))


def pending_minor(make_user, link_sent_days_ago):
    user = make_user(status=UserStatus.PENDING_GUARDIAN, verified=True)
    raw = guardian.create_pending(user, "Guardian", "g@example.com")
    GuardianConsent.objects.filter(user=user).update(
        sent_at=timezone.now() - timedelta(days=link_sent_days_ago)
    )
    return user, raw


def test_a_learner_who_verifies_after_the_purge_chose_candidates_is_kept(make_user, monkeypatch):
    victim = make_user(verified=False)
    bystander = make_user(verified=False)
    age(victim, 8)
    age(bystander, 8)
    real = purge._lock_verification_rows

    def verify_just_before_the_locks(user_ids):
        # the verification email link is clicked after the first look and before the rows are locked
        EmailAddress.objects.filter(user=victim).update(verified=True)
        real(user_ids)

    monkeypatch.setattr(purge, "_lock_verification_rows", verify_just_before_the_locks)
    counts = purge.purge_stale_accounts()
    remaining = set(User.objects.values_list("pk", flat=True))
    assert victim.pk in remaining  # kept: they verified in time
    assert bystander.pk not in remaining  # still unverified, still purged
    assert counts["unverified"] == 1 and counts["count"] == 1


def test_a_guardian_who_confirms_after_the_purge_chose_candidates_keeps_the_learner(
    make_user, monkeypatch
):
    user, _raw = pending_minor(make_user, link_sent_days_ago=30)
    real = purge._lock_verification_rows

    def confirm_just_before_the_locks(user_ids):
        GuardianConsent.objects.filter(user=user).update(confirmed_at=timezone.now())
        User.objects.filter(pk=user.pk).update(status=UserStatus.ACTIVE)
        real(user_ids)

    monkeypatch.setattr(purge, "_lock_verification_rows", confirm_just_before_the_locks)
    counts = purge.purge_stale_accounts()
    assert User.objects.filter(pk=user.pk).exists()
    assert counts["guardian_expired"] == 0


def test_the_purge_locks_the_rows_a_verification_writes_to(make_user):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    victim = make_user(verified=False)
    age(victim, 8)
    with CaptureQueriesContext(connection) as queries:
        purge.purge_stale_accounts()
    locking = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
    assert any("account_emailaddress" in sql for sql in locking)
    assert any("guardianconsent" in sql.replace("_", "") for sql in locking)


def test_the_purge_command_still_removes_the_stale_and_keeps_the_rest(make_user):
    stale, fresh = make_user(verified=False), make_user(verified=False)
    age(stale, 9)
    call_command("purge_unverified")
    assert not User.objects.filter(pk=stale.pk).exists()
    assert User.objects.filter(pk=fresh.pk).exists()


# --- a failed guardian resend keeps the old link -----------------------------------------------


def test_a_resend_that_cannot_send_keeps_the_old_link_working(make_user, monkeypatch):
    user, old = pending_minor(make_user, link_sent_days_ago=1)
    before = GuardianConsent.objects.get(user=user)
    monkeypatch.setattr(guardian.email_budget, "can_send", lambda kind, address, now=None: False)
    assert guardian.resend(user) is False
    assert guardian.find_by_token(old) is not None
    after = GuardianConsent.objects.get(user=user)
    assert after.token_hash == before.token_hash and after.sent_at == before.sent_at


def test_a_resend_that_fails_in_the_mail_server_keeps_the_old_link_working(make_user, monkeypatch):
    user, old = pending_minor(make_user, link_sent_days_ago=1)
    before = GuardianConsent.objects.get(user=user)

    def broken(*args, **kwargs):
        raise smtplib.SMTPException("mail server down")

    monkeypatch.setattr(guardian, "send_mail", broken)
    assert guardian.resend(user) is False
    assert guardian.find_by_token(old) is not None
    assert GuardianConsent.objects.get(user=user).token_hash == before.token_hash
    assert EmailLog.objects.count() == 0  # nothing was sent, so nothing counts against the budget


def test_the_waiting_page_tells_the_learner_when_a_resend_failed(client, make_user, monkeypatch):
    user, old = pending_minor(make_user, link_sent_days_ago=1)
    monkeypatch.setattr(guardian, "send_mail", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    client.force_login(user)
    response = client.post(reverse("resend_guardian"), follow=True)
    assert "could not send" in response.content.decode()
    assert guardian.find_by_token(old) is not None


def test_a_resend_that_sends_replaces_the_old_link(make_user, mailoutbox):
    user, old = pending_minor(make_user, link_sent_days_ago=1)
    assert guardian.resend(user) is True
    assert guardian.find_by_token(old) is None  # the old link stops working once the new one is out
    assert len(mailoutbox) == 1
    new = mailoutbox[0].body.split("/guardian/")[1].split("/")[0]
    assert guardian.find_by_token(new) is not None


# --- a signed-in learner's saved language wins ------------------------------------------------


def learner_with(make_user, make_batch, language):
    learner = make_user(batch=make_batch())
    learner.profile.preferred_language = language
    learner.profile.save()
    return learner


def test_the_saved_language_beats_a_stale_language_cookie(client, make_user, make_batch):
    learner = learner_with(make_user, make_batch, "hi")
    client.force_login(learner)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "gu"  # left by a guest visit or another account
    response = client.get("/")
    assert '<html lang="hi">' in response.content.decode()
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "hi"


def test_a_matching_cookie_is_not_set_again(client, make_user, make_batch):
    learner = learner_with(make_user, make_batch, "mr")
    client.force_login(learner)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "mr"
    response = client.get("/")
    assert '<html lang="mr">' in response.content.decode()
    assert settings.LANGUAGE_COOKIE_NAME not in response.cookies


def test_choosing_a_language_while_signed_in_sticks_on_the_next_request(
    client, make_user, make_batch
):
    learner = learner_with(make_user, make_batch, "hi")
    client.force_login(learner)
    chosen = client.post(reverse("set_language"), {"language": "mr", "next": "/"})
    assert chosen.cookies[settings.LANGUAGE_COOKIE_NAME].value == "mr"  # not reset to "hi"
    learner.profile.refresh_from_db()
    assert learner.profile.preferred_language == "mr"
    page = client.get("/")
    assert '<html lang="mr">' in page.content.decode()


def test_a_guest_still_uses_the_cookie(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "gu"
    assert '<html lang="gu">' in client.get("/").content.decode()


# --- auto-submit rechecks the last save under the lock -----------------------------------------


def stale_attempt(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    Attempt.objects.filter(pk=attempt.pk).update(
        last_saved_at=timezone.now() - timedelta(days=settings.STALE_ATTEMPT_DAYS + 1)
    )
    return attempt


def test_an_attempt_saved_after_the_job_looked_is_not_auto_submitted(
    make_part, learner, monkeypatch
):
    attempt = stale_attempt(make_part, learner)
    real = services.submit

    def learner_saves_first(attempt_id, user_id, **kwargs):
        item = Attempt.objects.get(pk=attempt_id).items.first()
        services.save_answer(attempt_id, learner, item.position, choice=right_token(item))
        return real(attempt_id, user_id, **kwargs)

    monkeypatch.setattr(services, "submit", learner_saves_first)
    assert services.auto_submit_stale() == 0
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.IN_PROGRESS and attempt.submitted_at is None
    assert attempt.items.exclude(response=None).count() == 1  # their save is intact


def test_a_still_stale_attempt_is_auto_submitted_and_counted(make_part, learner):
    attempt = stale_attempt(make_part, learner)
    assert services.auto_submit_stale() == 1
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.AUTO_SUBMITTED


def test_the_recheck_never_blocks_a_manual_submit(make_part, learner):
    attempt = stale_attempt(make_part, learner)
    result = services.submit(attempt.pk, learner.pk)  # no stale_before: the learner chose to submit
    assert result.status == AttemptStatus.SUBMITTED


# --- send_mail() returning 0 is a failed send ----------------------------------------------------


def test_a_send_that_reports_zero_messages_keeps_the_old_link_and_records_nothing(
    make_user, monkeypatch
):
    user, old = pending_minor(make_user, link_sent_days_ago=1)
    before = GuardianConsent.objects.get(user=user)
    monkeypatch.setattr(guardian, "send_mail", lambda *args, **kwargs: 0)
    assert guardian.resend(user) is False
    assert guardian.find_by_token(old) is not None  # the old link still works
    after = GuardianConsent.objects.get(user=user)
    assert after.token_hash == before.token_hash and after.sent_at == before.sent_at
    assert EmailLog.objects.count() == 0  # no successful send against the budget


def test_a_zero_send_does_not_extend_the_old_links_life(make_user, monkeypatch):
    user, old = pending_minor(make_user, link_sent_days_ago=13)
    monkeypatch.setattr(guardian, "send_mail", lambda *args, **kwargs: 0)
    assert guardian.resend(user) is False
    in_two_days = timezone.now() + timedelta(days=2)
    assert guardian.find_by_token(old) is not None
    assert guardian.find_by_token(old, now=in_two_days) is None  # expires on its original date


# --- the auto-submit count only includes what this call really closed -----------------------------


def events(action):
    from apps.audit.models import AuditEvent

    return AuditEvent.objects.filter(action=action)


def test_a_normal_stale_attempt_is_submitted_counted_and_audited_once(make_part, learner):
    attempt = stale_attempt(make_part, learner)
    assert services.auto_submit_stale() == 1
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.AUTO_SUBMITTED
    assert events("attempt.auto_submitted").count() == 1
    assert events("system.auto_submit_stale").get().data == {"count": 1}
    assert services.auto_submit_stale() == 0  # nothing left to do
    assert events("system.auto_submit_stale").count() == 1


def test_a_manual_submit_that_wins_the_race_is_not_counted_as_an_auto_submit(
    make_part, learner, monkeypatch
):
    attempt = stale_attempt(make_part, learner)
    real = services.submit

    def learner_submits_first(attempt_id, user_id, **kwargs):
        real(attempt_id, user_id)  # the learner pressed Submit after the job picked the attempt
        return real(attempt_id, user_id, **kwargs)

    monkeypatch.setattr(services, "submit", learner_submits_first)
    assert services.auto_submit_stale() == 0
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.SUBMITTED  # still their manual submission
    assert events("attempt.submitted").count() == 1
    assert events("attempt.auto_submitted").count() == 0
    assert events("system.auto_submit_stale").count() == 0


def test_a_second_job_that_finds_the_attempt_already_auto_submitted_does_not_count_it(
    make_part, learner, monkeypatch
):
    attempt = stale_attempt(make_part, learner)
    real = services.submit

    def other_worker_first(attempt_id, user_id, **kwargs):
        first = real(attempt_id, user_id, **kwargs)  # another worker closes it first
        assert first.just_closed is True
        return real(attempt_id, user_id, **kwargs)  # this job's own call finds it closed

    monkeypatch.setattr(services, "submit", other_worker_first)
    assert services.auto_submit_stale() == 0
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.AUTO_SUBMITTED
    assert events("attempt.auto_submitted").count() == 1  # graded and audited once
    assert events("system.auto_submit_stale").count() == 0  # this job counted nothing


def test_submit_reports_whether_this_call_closed_the_attempt(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    first = services.submit(attempt.pk, learner.pk)
    again = services.submit(attempt.pk, learner.pk)  # a safe retry
    assert first.just_closed is True and again.just_closed is False
    assert again.status == AttemptStatus.SUBMITTED and again.score == first.score
    assert events("attempt.submitted").count() == 1
