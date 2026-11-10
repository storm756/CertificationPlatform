"""The daily-job runner (D27) and the purge_unverified job."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import guardian
from apps.accounts.models import GuardianConsent, User, UserStatus
from apps.audit.models import AuditEvent
from apps.core import periodic
from apps.core.models import PeriodicRun

pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


# --- scheduling ---------------------------------------------------------------------------


def test_a_due_job_runs_and_records_success():
    calls = []
    result = periodic.run_due(at(10, 3, 5), {"j": lambda: calls.append(1)})
    assert result == {"j": "ok"} and calls == [1]
    assert PeriodicRun.objects.get(job="j").last_success_at == at(10, 3, 5)


def test_a_job_is_not_due_before_0300_ist():
    calls = []
    result = periodic.run_due(at(10, 2, 59), {"j": lambda: calls.append(1)})
    assert result == {"j": "skipped"} and calls == []


def test_a_job_does_not_run_twice_in_one_day():
    calls = []
    jobs = {"j": lambda: calls.append(1)}
    periodic.run_due(at(10, 3, 5), jobs)
    assert periodic.run_due(at(10, 3, 15), jobs) == {"j": "skipped"}
    assert periodic.run_due(at(10, 23, 50), jobs) == {"j": "skipped"}
    assert len(calls) == 1
    # ... and runs again the next day.
    assert periodic.run_due(at(11, 3, 1), jobs) == {"j": "ok"}
    assert len(calls) == 2


def test_missed_runs_catch_up_once_after_a_restart():
    calls = []
    jobs = {"j": lambda: calls.append(1)}
    PeriodicRun.objects.create(job="j", last_success_at=at(5, 3, 1))
    # The loop was down for days; the first wake-up at 14:00 runs it once, not once per missed day.
    assert periodic.run_due(at(10, 14, 0), jobs) == {"j": "ok"}
    assert periodic.run_due(at(10, 14, 10), jobs) == {"j": "skipped"}
    assert len(calls) == 1


def test_a_failing_job_is_logged_retried_and_does_not_stop_the_others(caplog):
    calls = []

    def boom():
        raise RuntimeError("database hiccup")

    jobs = {"bad": boom, "good": lambda: calls.append(1)}
    result = periodic.run_due(at(10, 3, 5), jobs)
    assert result == {"bad": "failed", "good": "ok"}
    assert calls == [1]
    assert "periodic job bad failed" in caplog.text
    assert not PeriodicRun.objects.filter(job="bad").exists()  # failure is not a success
    assert periodic.run_due(at(10, 3, 15), jobs)["bad"] == "failed"  # retried next wake-up


@pytest.fixture
def keep_test_connection(monkeypatch):
    # The command closes stale connections between wake-ups; that would close the test's own.
    monkeypatch.setattr(
        "apps.core.management.commands.run_periodic.close_old_connections", lambda: None
    )


def test_run_periodic_once_runs_the_registered_job(monkeypatch, keep_test_connection):
    calls = []
    monkeypatch.setattr(periodic, "JOBS", {"j": lambda: calls.append(1)})
    monkeypatch.setattr(timezone, "now", lambda: at(10, 4, 0))
    call_command("run_periodic", "--once")
    assert calls == [1]


def test_run_periodic_loop_survives_a_failed_wake_up(monkeypatch, keep_test_connection):
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("db down")
        raise KeyboardInterrupt  # stop the endless loop once we've seen it carry on

    monkeypatch.setattr(periodic, "run_due", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(KeyboardInterrupt):
        call_command("run_periodic")
    assert len(attempts) == 2


# --- the purge job ------------------------------------------------------------------------


def age(user, days):
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=days))


def test_purge_removes_only_learners_unverified_after_seven_days(make_user):
    stale = make_user(verified=False)
    fresh = make_user(verified=False)
    verified_old = make_user(verified=True)
    mentor_old = make_user(role="mentor", verified=False)
    for u in (stale, verified_old, mentor_old):
        age(u, 8)
    call_command("purge_unverified")
    remaining = set(User.objects.values_list("pk", flat=True))
    assert stale.pk not in remaining
    assert {fresh.pk, verified_old.pk, mentor_old.pk} <= remaining


def make_pending_minor(make_user, link_sent_days_ago):
    user = make_user(status=UserStatus.PENDING_GUARDIAN)
    GuardianConsent.objects.create(
        user=user,
        guardian_name="Guardian",
        guardian_email="g@example.com",
        token_hash=f"hash-{user.pk}",
        sent_at=timezone.now() - timedelta(days=link_sent_days_ago),
    )
    return user


def test_purge_removes_guardian_waiters_seven_days_after_their_link_expired(make_user):
    # Link lasts 14 days, then 7 more: gone after 21 days.
    waiting_long = make_pending_minor(make_user, 22)
    in_grace = make_pending_minor(make_user, 20)  # link expired 6 days ago
    live_link = make_pending_minor(make_user, 3)
    call_command("purge_unverified")
    remaining = set(User.objects.values_list("pk", flat=True))
    assert waiting_long.pk not in remaining
    assert {in_grace.pk, live_link.pk} <= remaining


def test_purge_keeps_a_learner_whose_guardian_confirmed(make_user):
    user = make_pending_minor(make_user, 30)
    guardian.confirm(user.guardian_consent, "Guardian")
    call_command("purge_unverified")
    assert User.objects.filter(pk=user.pk).exists()


def test_purge_sends_no_email_and_audits_only_counts(make_user, mailoutbox):
    stale = make_user(verified=False, email="secret.person@example.com")
    age(stale, 9)
    waiting = make_pending_minor(make_user, 25)
    del waiting
    call_command("purge_unverified")
    assert mailoutbox == []
    event = AuditEvent.objects.get(action="system.purge_unverified")
    assert event.data == {"count": 2, "unverified": 1, "guardian_expired": 1}
    assert event.target_id == "" and event.actor_id is None
    assert "secret.person" not in str(event.data)


def test_the_periodic_job_registry_runs_the_purge(make_user):
    stale = make_user(verified=False)
    age(stale, 9)
    assert periodic.run_due(at(10, 3, 30)) == {
        "purge_unverified": "ok",
        "auto_submit_stale_attempts": "ok",
    }
    assert not User.objects.filter(pk=stale.pk).exists()
