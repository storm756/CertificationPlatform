"""Prod/staging settings must import cleanly and be hardened."""

import importlib
import sys

import pytest

ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "DJANGO_ALLOWED_HOSTS": "cyberfirstresponse.io",
    "DB_PASSWORD": "pw",
}


@pytest.mark.parametrize("module", ["prod", "staging"])
def test_hosted_settings_are_hardened(monkeypatch, module):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    for name in [m for m in sys.modules if m.startswith("config.settings")]:
        monkeypatch.delitem(sys.modules, name)
    settings = importlib.import_module(f"config.settings.{module}")
    assert settings.DEBUG is False
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert settings.SECURE_HSTS_SECONDS > 0
    assert settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
    assert settings.ALLOWED_HOSTS == ["cyberfirstresponse.io"]


def test_missing_secret_key_refuses_to_start(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "pw")
    for name in [m for m in sys.modules if m.startswith("config.settings")]:
        monkeypatch.delitem(sys.modules, name)
    with pytest.raises(RuntimeError):
        importlib.import_module("config.settings.base")


def test_sentry_scrubber_removes_request_data_and_user():
    from config.settings.sentry import scrub_event

    event = {
        "request": {"data": {"password": "s"}, "cookies": "sid=1", "url": "/x"},
        "user": {"email": "a@b.c"},
    }
    cleaned = scrub_event(event, {})
    assert cleaned["request"]["data"] == "[scrubbed]"
    assert cleaned["request"]["cookies"] == "[scrubbed]"
    assert "user" not in cleaned
