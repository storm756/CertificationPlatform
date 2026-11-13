"""Stage 9: the landing page and the public pages (privacy, terms, grievance, help, 404, 500)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db
ROOT = Path(settings.BASE_DIR)
PUBLIC = ["/", "/privacy/", "/terms/", "/grievance/", "/help/"]
LANGS = ["en", "hi", "mr", "gu"]


def get(client, path, lang="en"):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
    return client.get(path)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("path", PUBLIC)
def test_public_pages_open_signed_out_in_every_language(client, path, lang):
    response = get(client, path, lang)
    assert response.status_code == 200
    html = response.content.decode()
    assert f'<html lang="{lang}"' in html
    assert 'id="main"' in html and "skip-link" in html
    assert "og:image" in html and "favicon" in html


@pytest.mark.parametrize("lang", ["hi", "mr", "gu"])
def test_landing_headline_is_translated(client, lang):
    html = get(client, "/", lang).content.decode()
    assert "Something just happened. What first?" not in html
    assert "Who runs it" not in html
    assert "Start certification" not in html


def test_landing_calls_to_action_go_to_register_and_sign_in_not_to_lessons(client):
    html = get(client, "/").content.decode()
    assert reverse("register") in html and reverse("account_login") in html
    # D34: lessons need sign-in, so no call to action in the page body links to /learn/
    # (the header's "Modules" link is the shell's own and goes through sign-in).
    body = html.split('<main id="main"', 1)[1].split("</main>", 1)[0]
    assert 'href="/learn/' not in body


def test_landing_for_a_signed_in_learner_says_continue(learner_client):
    html = learner_client.get("/").content.decode()
    assert reverse("start") in html and "Continue" in html


def test_landing_has_no_inline_script_or_style(client):
    for path in PUBLIC:
        html = get(client, path).content.decode()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), path
        assert not re.search(r"<[a-z][^>]*\sstyle=", html), path


def test_programme_name_comes_from_settings(client, settings):
    settings.PROGRAMME_SHORT = "TPN"
    html = client.get("/").content.decode()
    assert "(TPN)" in html and "(CCFR)" not in html


def test_faq_is_shared_by_landing_and_help(client):
    from apps.core.faq import FAQ

    landing = client.get("/").content.decode()
    help_page = client.get("/help/").content.decode()
    for question, _answer, on_landing in FAQ:
        assert str(question).replace("'", "&#x27;") in help_page
        assert (str(question).replace("'", "&#x27;") in landing) == on_landing


def test_legal_pages_are_marked_draft(client):
    for path in ("/privacy/", "/terms/", "/grievance/"):
        assert "Draft." in client.get(path).content.decode(), path


def test_first_response_check_does_not_reuse_exam_or_quiz_questions(make_question):
    """The landing check has its own scenarios (stage brief): none is a question in the bank."""
    from apps.questions.models import QuestionVersion

    make_question(1)
    template = (ROOT / "templates/landing.html").read_text("utf-8")
    scenarios = re.findall(r'role="tab" id="check-tab-\d"[^>]*>\{% translate "([^"]+)"', template)
    assert len(scenarios) == 4
    banked = " ".join(str(v.body) for v in QuestionVersion.objects.all())
    assert not any(s in banked for s in scenarios)
    # and the landing view never touches the question or assessment apps
    source = (ROOT / "apps/core/views.py").read_text("utf-8")
    assert "apps.questions" not in source and "apps.assessments" not in source


# --- the people ---------------------------------------------------------------------------


def test_people_placeholder_shows_until_consent_and_photos(client, tmp_path):
    html = client.get("/").content.decode()
    assert "Leadership team" in html and "people_photo" not in html and "/people/" not in html
    assert "Bhavesh" not in html and "Vineet" not in html
    assert client.get("/people/bhavesh-patel/").status_code == 404


def test_people_switch_on_only_with_consent_and_every_photo(client, tmp_path):
    for name in ("bhavesh-patel.jpg", "nilakshi-jain.jpg", "vineet-kumar.webp"):
        (tmp_path / name).write_bytes(b"fake-image")
    with override_settings(PEOPLE_PHOTO_DIR=tmp_path, PEOPLE_CONSENT_GIVEN=False):
        assert "Leadership team" in client.get("/").content.decode()
        assert client.get("/people/bhavesh-patel/").status_code == 404
    (tmp_path / "vineet-kumar.webp").unlink()
    with override_settings(PEOPLE_PHOTO_DIR=tmp_path, PEOPLE_CONSENT_GIVEN=True):
        assert "Leadership team" in client.get("/").content.decode()  # one photo missing
    (tmp_path / "vineet-kumar.webp").write_bytes(b"fake-image")
    with override_settings(PEOPLE_PHOTO_DIR=tmp_path, PEOPLE_CONSENT_GIVEN=True):
        html = client.get("/").content.decode()
        assert "Leadership team" not in html and "Dr. Bhavesh Patel" in html
        photo = client.get("/people/bhavesh-patel/")
        assert photo.status_code == 200 and photo["Content-Type"] == "image/jpeg"
        assert client.get("/people/unknown/").status_code == 404


def test_people_photos_live_outside_static_and_git():
    assert "content-data/" in (ROOT / ".gitignore").read_text("utf-8")
    assert not list((ROOT / "static").rglob("*people*")), "photos are never static files"
    assert (
        settings.PEOPLE_PHOTO_DIR.name == "people"
        and "static" not in settings.PEOPLE_PHOTO_DIR.parts
    )


# --- error pages ---------------------------------------------------------------------------


def test_404_page_is_in_the_site_style(client):
    response = client.get("/no-such-page-here/")
    assert response.status_code == 404
    html = response.content.decode()
    assert "We can't find that page" in html or "We can&#x27;t find that page" in html
    assert "site-header" in html and reverse("home") in html


def test_404_page_is_translated(client):
    html = get(client, "/no-such-page-here/", "hi").content.decode()
    assert "Page not found" not in html


def test_500_page_is_standalone_and_translated(rf):
    from django.utils import translation

    from apps.core.views import server_error

    request = rf.get("/boom/")
    with translation.override("en"):
        response = server_error(request)
    assert response.status_code == 500
    html = response.content.decode()
    assert "Something went wrong on our side" in html and "site-header" not in html
    with translation.override("gu"):
        gujarati = server_error(request).content.decode()
    assert '<html lang="gu"' in gujarati and "Something went wrong" not in gujarati


def test_guardian_waiting_user_can_still_read_public_pages(client, make_user):
    from apps.accounts.models import UserStatus

    user = make_user(status=UserStatus.PENDING_GUARDIAN)
    client.force_login(user)
    for path in ("/terms/", "/grievance/", "/help/", "/privacy/"):
        assert client.get(path).status_code == 200, path
