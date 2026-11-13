"""Stage 10 rate limits: every limit is per user, per batch or per real client IP, and the page that
stops someone says how long to wait. (Per-client keys on /learn/check, the block endpoint and the
mentor reset link are in test_ratelimit_keys.py.)"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.ratelimits import window_minutes

ROOT = Path(__file__).resolve().parents[1]
CADDY_CLIENT, OTHER_CLIENT = "198.51.100.7", "203.0.113.77"


def test_no_limit_is_keyed_on_the_proxy_address():
    for path in (ROOT / "apps").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"@ratelimit\((.*?)\)\n", source, re.S):
            args = match.group(1)
            assert 'key="ip"' not in args and "key='ip'" not in args, path
            key = re.search(r"key=([^,]+)", args).group(1)
            assert key in {'"user"', "_rate_key", "_client_key", "_verify_key"}, (path, key)


def test_allauth_reads_the_real_client_behind_caddy():
    hosted = (ROOT / "config/settings/_hosted.py").read_text(encoding="utf-8")
    assert "ALLAUTH_TRUSTED_PROXY_COUNT = 1" in hosted


@pytest.mark.parametrize(
    ("rate", "minutes"), [("90/10m", 10), ("30/h", 60), ("5/m", 1), ("20/s", 1), ("1/2h", 120)]
)
def test_window_minutes(rate, minutes):
    assert window_minutes(rate) == minutes


# --- sign-in (allauth) -------------------------------------------------------------------------


def _bad_login(client, email, ip):
    return client.post(
        reverse("account_login"),
        {"login": email, "password": "not-the-password"},
        HTTP_X_FORWARDED_FOR=ip,
    )


def test_five_wrong_passwords_lock_that_email_and_say_for_how_long(client, make_user):
    user = make_user()
    for _ in range(5):
        assert "Please wait 5 minutes" not in _bad_login(client, user.email, CADDY_CLIENT).text
    response = _bad_login(client, user.email, CADDY_CLIENT)
    assert "Too many wrong passwords. Please wait 5 minutes" in response.text


def test_failed_logins_per_network_are_per_real_client(client, settings, make_user):
    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1
    settings.ACCOUNT_RATE_LIMITS = {**settings.ACCOUNT_RATE_LIMITS, "login_failed": "3/m/ip"}
    users = [make_user() for _ in range(4)]
    for user in users[:3]:
        _bad_login(client, user.email, CADDY_CLIENT)
    blocked = _bad_login(client, users[3].email, CADDY_CLIENT)
    assert "Too many wrong passwords" in blocked.text
    # another phone network, behind the same Caddy (same REMOTE_ADDR), is not blocked
    assert "Too many wrong passwords" not in _bad_login(client, users[3].email, OTHER_CLIENT).text


def test_allauth_limits_show_the_too_many_page_with_the_wait(client, settings, db):
    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1
    settings.ACCOUNT_RATE_LIMITS = {**settings.ACCOUNT_RATE_LIMITS, "login": "2/m/ip"}
    url = reverse("account_login")
    for _ in range(2):
        client.post(
            url, {"login": "a@example.com", "password": "x"}, HTTP_X_FORWARDED_FOR="1.2.3.4"
        )
    response = client.post(
        url, {"login": "a@example.com", "password": "x"}, HTTP_X_FORWARDED_FOR="1.2.3.4"
    )
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert "Please wait 1 minute and try again" in response.text


def test_the_class_sized_defaults():
    from django.conf import settings

    assert settings.ACCOUNT_RATE_LIMITS["login"] == "90/m/ip"
    assert settings.ACCOUNT_RATE_LIMITS["login_failed"] == "30/m/ip,5/5m/key"
    assert settings.REGISTER_RATE == "90/10m"


# --- sign-up (per batch) and verify (per client IP) ----------------------------------------------


def test_register_limit_is_per_batch_and_says_when(client, settings, make_batch):
    settings.REGISTER_RATE = "2/10m"
    batch, other = make_batch(), make_batch()
    for _ in range(2):
        client.post(reverse("register"), {"batch": batch.pk})
    response = client.post(reverse("register"), {"batch": batch.pk})
    assert response.status_code == 429
    assert response["Retry-After"] == "600"
    assert "Please wait up to 10 minutes and try again" in response.text
    assert client.post(reverse("register"), {"batch": other.pk}).status_code != 429


def test_verify_limit_says_when(client, settings, db):
    settings.CERTIFICATE_VERIFY_RATE = "2/10m"
    for _ in range(2):
        client.get(reverse("verify"), HTTP_X_FORWARDED_FOR=CADDY_CLIENT)
    response = client.get(reverse("verify"), HTTP_X_FORWARDED_FOR=CADDY_CLIENT)
    assert response.status_code == 429
    assert "Please wait up to 10 minutes and scan the QR code again" in response.text
    assert client.get(reverse("verify"), HTTP_X_FORWARDED_FOR=OTHER_CLIENT).status_code == 200


# --- answer and submit (per learner) -------------------------------------------------------------


@pytest.mark.parametrize(("name", "setting"), [("attempt_answer", "ANSWER_RATE"), ("attempt_submit", "SUBMIT_RATE")])  # fmt: skip
def test_answer_and_submit_are_limited_per_learner(name, setting, client, settings, make_user, make_batch):  # fmt: skip
    setattr(settings, setting, "2/h")
    batch = make_batch()
    first, second = make_user(batch=batch), make_user(batch=batch)
    url = reverse(name, args=[999999])  # the limit counts before the attempt is looked up
    client.force_login(first)
    for _ in range(2):
        assert client.post(url).status_code == 404
    response = client.post(url)
    assert response.status_code == 429  # attempt.js keeps the answer and retries on 429
    assert response["Retry-After"] == "3600"
    assert "Please wait up to 60 minutes" in response.text

    other_browser = client.__class__()
    other_browser.force_login(second)
    assert other_browser.post(url).status_code == 404  # another learner, same address: not blocked
