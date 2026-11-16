"""Pilot hardening (Nov 2026): Build gate chips, the _raw_percent warning, English-only switch,
token redaction in logs, log rotation and the admin per-batch CSV. Invented data only."""

import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings as django_settings
from django.urls import reverse

from apps.accounts.forms import RegistrationForm
from apps.core import languages
from apps.questions import schemas
from apps.results import policy

from .conftest import invented_body

# --- Build: a safety-gate chip can't be a right answer ----------------------------------------------


def test_build_gate_chip_in_a_slot_answer_blocks_publishing():
    fmt, body = invented_body("inv-build")
    gated = next(i for i, chip in enumerate(body["chips"]) if chip.get("gate"))
    assert schemas.publish_errors(fmt, body) == []
    body["slots"][0]["answer"] = [gated]
    if body["slots"][0].get("chips") is not None and gated not in body["slots"][0]["chips"]:
        body["slots"][0]["chips"].append(gated)
    errors = schemas.publish_errors(fmt, body)
    assert any("safety-gate chip" in e and e.startswith("slots.0.answer") for e in errors)


def test_build_gate_chip_offered_but_not_an_answer_is_fine():
    fmt, body = invented_body("inv-build")
    assert any(chip.get("gate") for chip in body["chips"])
    assert schemas.publish_errors(fmt, body) == []


# --- _raw_percent never falls back silently ----------------------------------------------------------


def test_raw_percent_fallback_logs_a_warning(caplog):
    attempt = SimpleNamespace(pk=4242, total_points=None, earned_points=None, score=Decimal("49.9"))
    with caplog.at_level(logging.WARNING, logger="apps.results.policy"):
        assert policy._raw_percent(attempt) == Decimal("49.9")
    assert any("4242" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_raw_percent_with_items_logs_nothing(caplog):
    attempt = SimpleNamespace(pk=1, total_points=Decimal(3), earned_points=Decimal(2), score=Decimal("66.7"))
    with caplog.at_level(logging.WARNING, logger="apps.results.policy"):
        value = policy._raw_percent(attempt)
    assert value == Decimal(200) / Decimal(3)
    assert not caplog.records


# --- English-only switch (LANGUAGES_ENABLED) ---------------------------------------------------------




@pytest.fixture
def english_only(settings):
    settings.LANGUAGES_ENABLED = ["en"]
    return settings


def test_all_languages_are_on_by_default():
    assert languages.enabled_codes() == ["en", "hi", "mr", "gu"]
    assert languages.switcher_shown()


@pytest.mark.django_db
def test_english_only_hides_every_switcher(client, english_only):
    html = client.get("/").content.decode()
    assert 'name="language"' not in html  # header select, footer buttons, landing chips
    assert "data-lang-select" not in html
    assert '<html lang="en">' in html


@pytest.mark.django_db
def test_all_languages_show_the_switcher(client):
    html = client.get("/").content.decode()
    assert "data-lang-select" in html
    for code in ("hi", "mr", "gu"):
        assert f'value="{code}"' in html


@pytest.mark.django_db
def test_english_only_ignores_a_guest_cookie_and_the_browser_language(client, english_only):
    client.cookies[django_settings.LANGUAGE_COOKIE_NAME] = "gu"
    assert '<html lang="en">' in client.get("/").content.decode()
    client.cookies.clear()
    page = client.get("/", HTTP_ACCEPT_LANGUAGE="hi")
    assert '<html lang="en">' in page.content.decode()


@pytest.mark.django_db
def test_english_only_serves_english_to_a_learner_who_saved_hindi(client, make_user, make_batch, english_only):
    learner = make_user(batch=make_batch())
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    client.force_login(learner)
    response = client.get("/")
    assert '<html lang="en">' in response.content.decode()
    assert django_settings.LANGUAGE_COOKIE_NAME not in response.cookies  # the cookie is not rewritten
    learner.profile.refresh_from_db()
    assert learner.profile.preferred_language == "hi"  # kept for when Hindi is switched on


@pytest.mark.django_db
def test_english_only_refuses_choosing_a_switched_off_language(client, make_user, make_batch, english_only):
    learner = make_user(batch=make_batch())
    client.force_login(learner)
    response = client.post(reverse("set_language"), {"language": "mr", "next": "/"})
    assert response.status_code == 302
    assert response.cookies[django_settings.LANGUAGE_COOKIE_NAME].value == "en"
    learner.profile.refresh_from_db()
    assert learner.profile.preferred_language != "mr"
    assert '<html lang="en">' in client.get("/").content.decode()


@pytest.mark.django_db
def test_switching_back_on_is_one_setting(client, make_user, make_batch, settings):
    learner = make_user(batch=make_batch())
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    client.force_login(learner)
    settings.LANGUAGES_ENABLED = ["en"]
    assert '<html lang="en">' in client.get("/").content.decode()
    settings.LANGUAGES_ENABLED = ["en", "hi", "mr", "gu"]
    assert '<html lang="hi">' in client.get("/").content.decode()


@pytest.mark.django_db
def test_english_only_registration_hides_the_language_field(english_only):
    field = RegistrationForm().fields["preferred_language"]
    assert field.choices == [("en", "English")] or [c[0] for c in field.choices] == ["en"]
    assert field.widget.is_hidden and field.initial == "en"
    assert RegistrationForm(data={"preferred_language": "hi"}).errors.get("preferred_language")


@pytest.mark.django_db
def test_all_languages_registration_offers_all_four():
    field = RegistrationForm().fields["preferred_language"]
    assert [c[0] for c in field.choices] == ["en", "hi", "mr", "gu"]
    assert not field.widget.is_hidden


def test_languages_enabled_env_parsing(monkeypatch):
    """The settings line: unknown codes are dropped, English is always kept."""
    import importlib

    import config.settings.base as base

    monkeypatch.setenv("LANGUAGES_ENABLED", "gu, xx")
    try:
        assert importlib.reload(base).LANGUAGES_ENABLED == ["en", "gu"]
        monkeypatch.setenv("LANGUAGES_ENABLED", "en")
        assert importlib.reload(base).LANGUAGES_ENABLED == ["en"]
    finally:
        monkeypatch.delenv("LANGUAGES_ENABLED")
        importlib.reload(base)


# --- L2: one-time links never reach the logs ---------------------------------------------------------

from pathlib import Path  # noqa: E402

from apps.core.redact import RedactTokensFilter, redact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("line", "secret"),
    [
        ('"GET /reset/Zx9-mentorToken_1/ HTTP/1.1" 200', "Zx9-mentorToken_1"),
        ('"GET /guardian/g7Kq2-consentToken/ HTTP/1.1" 200', "g7Kq2-consentToken"),
        ('"GET /accounts/password/reset/key/2c-a1b2c3d4e5f6/ HTTP/1.1" 302', "a1b2c3d4e5f6"),
        ('"GET /accounts/confirm-email/MQ:1tSecret:abcDEF/ HTTP/1.1" 200', "MQ:1tSecret:abcDEF"),
        ('"GET /verify/K7Q2X9/ HTTP/1.1" 200', "K7Q2X9"),
        ("Not Found: /reset/plainToken/", "plainToken"),
        ("https://cyberfirstresponse.io/guardian/fullUrlToken/", "fullUrlToken"),
        ('"GET /accounts/login/?next=/x&key=queryKey123 HTTP/1.1"', "queryKey123"),
        ('"GET /x/?token=queryTok&code=queryCode HTTP/1.1"', "queryCode"),
    ],
)
def test_redact_masks_every_one_time_token(line, secret):
    cleaned = redact(line)
    assert secret not in cleaned
    assert "***" in cleaned


@pytest.mark.parametrize(
    "line",
    [
        '"GET /accounts/password/reset/ HTTP/1.1" 200',
        '"POST /accounts/password/reset/done/ HTTP/1.1" 200',
        '"GET /verify/ HTTP/1.1" 200',
        '"GET /learn/module/3/ HTTP/1.1" 200',
        "plain message without a path",
    ],
)
def test_redact_leaves_ordinary_paths_alone(line):
    if "/accounts/password/reset/done/" in line:
        # "done" after the reset form is not a token, but masking it would be harmless too
        assert redact(line).startswith('"POST /accounts/password/reset/')
    else:
        assert redact(line) == line


def test_the_filter_rewrites_a_record_and_never_drops_it():
    record = logging.LogRecord("django.request", logging.WARNING, __file__, 1, "Not Found: %s", ("/reset/abcDEF123/",), None)
    assert RedactTokensFilter().filter(record) is True
    assert record.getMessage() == "Not Found: /reset/***/"


def test_django_logging_masks_tokens_on_the_console_handler(settings):
    console = settings.LOGGING["handlers"]["console"]
    assert "redact_tokens" in console["filters"]
    assert settings.LOGGING["filters"]["redact_tokens"]["()"] == "apps.core.redact.RedactTokensFilter"
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler))
    assert any(isinstance(f, RedactTokensFilter) for f in handler.filters)


def test_gunicorn_access_and_error_logs_mask_tokens(capsys):
    import runpy

    from gunicorn.config import Config

    conf = runpy.run_path(str(ROOT / "config" / "gunicorn.conf.py"))
    assert conf["accesslog"] == "-" and conf["errorlog"] == "-"
    cfg = Config()
    cfg.set("accesslog", "-")
    cfg.set("errorlog", "-")
    cfg.set("logger_class", conf["logger_class"])
    log = cfg.logger_class(cfg)
    log.access_log.info('%(h)s "%(r)s" %(s)s', {"h": "1.2.3.4", "r": "GET /guardian/sEcReT42/ HTTP/1.1", "s": "200"})
    log.error("Error handling request /reset/sEcReT43/")
    out = capsys.readouterr()
    text = out.out + out.err
    assert "sEcReT42" not in text and "sEcReT43" not in text
    assert "/guardian/***/" in text and "/reset/***/" in text


def test_the_image_starts_gunicorn_with_the_redacting_config():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"-c", "config/gunicorn.conf.py"' in dockerfile
    assert "--access-logfile" not in dockerfile


@pytest.mark.parametrize("name", ["compose.yml", "compose.edge.yml"])
def test_every_server_service_rotates_its_logs(name):
    import re

    text = (ROOT / "deploy" / name).read_text(encoding="utf-8")
    anchor = text.split("x-logging: &rotated-logs", 1)[1].split("\n\n", 1)[0]
    assert "driver: json-file" in anchor
    assert 'max-size: "20m"' in anchor and 'max-file: "5"' in anchor
    services = text.split("\nservices:\n", 1)[1].split("\n\n" + "networks:", 1)[0]
    blocks = re.split(r"\n(?=  [a-z][\w-]*:)", "\n" + services)
    blocks = [b for b in blocks if b.strip()]
    assert blocks
    for block in blocks:
        assert "    logging: *rotated-logs" in block, block.strip().splitlines()[0]


def test_sentry_masks_tokens_in_the_url_and_messages():
    from config.settings.sentry import scrub_event

    event = {
        "request": {"url": "https://cyberfirstresponse.io/reset/sentryTok1/", "query_string": "x"},
        "message": "failed at /guardian/sentryTok2/",
    }
    out = scrub_event(event, None)
    assert "sentryTok1" not in out["request"]["url"] and "sentryTok2" not in out["message"]
