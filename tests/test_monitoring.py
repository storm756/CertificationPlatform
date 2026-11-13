"""Stage 10 monitoring: Sentry sends no personal data and is off without a DSN; heartbeat pings are
off without a URL, say /fail when something failed, and never break the job that pings."""

import pytest
from django.core.management import call_command

from apps.core import monitoring
from config.settings import sentry


def test_sentry_is_off_without_a_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    sentry.init_sentry("", environment="prod")
    assert calls == []


def test_sentry_is_configured_without_pii(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    sentry.init_sentry("https://key@example.invalid/1", environment="staging")
    (kwargs,) = calls
    assert kwargs["send_default_pii"] is False
    assert kwargs["include_local_variables"] is False
    assert kwargs["before_send"] is sentry.scrub_event
    assert kwargs["before_breadcrumb"] is sentry.scrub_breadcrumb


def test_scrub_masks_emails_and_drops_frame_variables():
    event = {
        "request": {"headers": {"Cookie": "x"}, "query_string": "email=a@b.co", "env": {"x": 1}},
        "exception": {
            "values": [
                {
                    "value": "duplicate key: Key (email)=(asha.k+1@example.co.in) already exists",
                    "stacktrace": {"frames": [{"function": "f", "vars": {"email": "a@b.co"}}]},
                }
            ]
        },
        "logentry": {"message": "sent to ravi@example.com", "params": ["ravi@example.com"]},
        "message": "for priya@example.org",
        "breadcrumbs": {
            "values": [{"message": "login neha@example.com", "data": {"to": "n@e.in"}}]
        },
    }
    cleaned = sentry.scrub_event(event, {})
    text = repr(cleaned)
    assert "@" not in text.replace("key@", "")  # no address survives anywhere
    assert cleaned["request"]["headers"] == "[scrubbed]"
    assert cleaned["request"]["query_string"] == "[scrubbed]"
    assert cleaned["request"]["env"] == "[scrubbed]"
    assert "vars" not in cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "params" not in cleaned["logentry"]
    assert sentry.MASK in cleaned["exception"]["values"][0]["value"]


def test_scrub_breadcrumb_masks_emails():
    crumb = sentry.scrub_breadcrumb({"message": "to a@b.co", "data": {"x": "c@d.org", "n": 3}}, {})
    assert crumb == {"message": f"to {sentry.MASK}", "data": {"x": sentry.MASK, "n": 3}}


class _Opened:
    def __init__(self, sink):
        self.sink = sink

    def __call__(self, url, timeout):
        self.sink.append((url, timeout))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n):
        return b""


def test_ping_is_off_without_a_url(monkeypatch):
    sink = []
    monkeypatch.setattr(monitoring.urllib.request, "urlopen", _Opened(sink))
    assert monitoring.ping("") is False
    assert sink == []


def test_ping_ok_and_fail(monkeypatch):
    sink = []
    monkeypatch.setattr(monitoring.urllib.request, "urlopen", _Opened(sink))
    assert monitoring.ping("https://hc.example/abc/") is True
    assert monitoring.ping("https://hc.example/abc", ok=False) is True
    assert sink == [("https://hc.example/abc", 10), ("https://hc.example/abc/fail", 10)]


def test_a_failing_ping_never_raises(monkeypatch):
    def boom(url, timeout):
        raise OSError("network down")

    monkeypatch.setattr(monitoring.urllib.request, "urlopen", boom)
    assert monitoring.ping("https://hc.example/abc") is False


@pytest.mark.django_db
@pytest.mark.parametrize(("job_result", "expected"), [("ok", True), ("failed", False)])
def test_the_tasks_loop_pings_after_each_wake_up(monkeypatch, settings, job_result, expected):
    from apps.core import periodic

    settings.TASKS_PING_URL = "https://hc.example/tasks"
    pings = []
    monkeypatch.setattr(periodic, "run_due", lambda: {"job": job_result})
    monkeypatch.setattr(
        "apps.core.management.commands.run_periodic.ping",
        lambda url, ok=True: pings.append((url, ok)),
    )
    call_command("run_periodic", "--once")
    assert pings == [("https://hc.example/tasks", expected)]
