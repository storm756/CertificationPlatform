"""Stage 1.5: the shared shell, components, language wiring and the staff-only styleguide."""

import re
from pathlib import Path

import pytest
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.templatetags.ccfr import as_input

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db
ROOT = Path(settings.BASE_DIR)


def staff_client(client, make_user):
    admin = make_user(role=Role.ADMIN, is_staff=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    return client


# --- the shell ----------------------------------------------------------------------------


def test_header_shows_both_partner_logos_and_the_emblem_slot(client):
    html = client.get("/").content.decode()
    assert "shah-anchor-logo.png" in html and "cyberpeace-logo.png" in html
    assert 'class="brand-emblem"' in html and ">CCFR<" in html


def test_programme_name_comes_from_settings_not_templates(client, settings):
    settings.PROGRAMME_NAME = "Test Programme Name"
    settings.PROGRAMME_SHORT = "TPN"
    html = client.get(reverse("account_login")).content.decode()
    assert "Test Programme Name" in html and ">TPN<" in html
    assert "Community Cyber First Responder" not in html


def test_programme_name_is_ccfr_everywhere_users_look(client):
    assert settings.PROGRAMME_SHORT == "CCFR"
    assert settings.PROGRAMME_NAME == "Community Cyber First Responder"
    for url in ("/", reverse("account_login"), reverse("privacy")):
        assert "CSFR" not in client.get(url).content.decode()


def test_there_is_no_night_mode(client):
    html = client.get("/").content.decode()
    assert "theme-toggle" not in html and "data-theme" not in html
    for css in (ROOT / "static" / "css").glob("*.css"):
        assert "data-theme" not in css.read_text(encoding="utf-8"), css.name


PAGES = ["/", "/accounts/login/", "/privacy/", "/accounts/password/reset/", "/guardian/nope/"]


@pytest.mark.parametrize("url", PAGES)
def test_pages_have_no_inline_scripts_styles_or_handlers(client, url):
    """The CSP set by Caddy forbids them (Stage 1.5 done-when)."""
    html = client.get(url).content.decode()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline <script>"
    assert not re.search(r"<style", html), "inline <style>"
    assert not re.search(r"\sstyle=", html), "style attribute"
    assert not re.search(r"\son[a-z]+=", html), "inline event handler"


def test_register_and_mentor_pages_have_no_inline_scripts_or_styles(
    client, mentor_client, make_batch
):
    make_batch()
    html = client.get(reverse("register")).content.decode()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and not re.search(r"\sstyle=", html)
    html = mentor_client.get(reverse("mentor_home")).content.decode()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and not re.search(r"\sstyle=", html)


def test_templates_never_use_safe_or_innerhtml():
    ours = [p for p in (ROOT / "static" / "js").glob("*.js") if not p.name.endswith(".min.js")]
    for path in list((ROOT / "templates").rglob("*.html")) + ours:  # vendored htmx is skipped
        text = path.read_text(encoding="utf-8")
        assert "|safe" not in text and "mark_safe" not in text, path
        assert "innerHTML" not in text.replace("never innerHTML", ""), path


def test_every_icon_used_in_templates_exists_in_the_sprite():
    sprite = (ROOT / "static" / "img" / "icons.svg").read_text(encoding="utf-8")
    used = set()
    for path in (ROOT / "templates").rglob("*.html"):
        used |= set(re.findall(r'\{% icon "([a-z-]+)"', path.read_text(encoding="utf-8")))
        used |= set(re.findall(r'icon="([a-z-]+)"', path.read_text(encoding="utf-8")))
    assert used, "no icons found, the scan is broken"
    missing = {name for name in used if f'id="i-{name}"' not in sprite}
    assert not missing, missing


# --- fonts ---------------------------------------------------------------------------------


def test_fonts_are_self_hosted_with_gujarati_and_licences():
    fonts = ROOT / "static" / "fonts"
    css = (ROOT / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
    for family in ("Baloo 2", "Hind", "Baloo Bhai 2", "Hind Vadodara"):
        assert f'font-family: "{family}"' in css, family
    assert "U+0A80-0AFF" in css  # the Gujarati block
    assert "font-display: swap" in css and "unicode-range" in css
    for name in re.findall(r"fonts/([\w.-]+\.woff2)", css):
        assert (fonts / name).stat().st_size > 1000, name
    for licence in ("Baloo2", "Hind", "BalooBhai2", "HindVadodara"):
        assert (fonts / f"OFL-{licence}.txt").exists()
    assert not list(fonts.glob("epilogue*")), "the unused Epilogue font was dropped"
    assert "http" not in css.replace("http://www.w3.org", ""), "no external font URLs"


# --- language wiring -----------------------------------------------------------------------


def test_guest_language_choice_sets_a_cookie_and_the_page_language(client):
    response = client.post(reverse("set_language"), {"language": "gu", "next": "/privacy/"})
    assert response.status_code == 302 and response["Location"] == "/privacy/"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "gu"
    assert '<html lang="gu">' in client.get("/privacy/").content.decode()


def test_django_can_activate_all_four_languages():
    """Django ships no Gujarati catalogue; locale/gu makes it usable (else "gu" is ignored)."""
    from django.utils.translation import check_for_language

    for code, _name in settings.LANGUAGES:
        assert check_for_language(code), code


def test_unknown_language_is_ignored(client):
    client.post(reverse("set_language"), {"language": "xx", "next": "/"})
    assert '<html lang="en">' in client.get("/").content.decode()


def test_signed_in_language_choice_is_saved_on_the_profile(client, make_user, make_batch):
    learner = make_user(batch=make_batch())
    client.force_login(learner)
    client.post(reverse("set_language"), {"language": "mr", "next": "/"})
    learner.profile.refresh_from_db()
    assert learner.profile.preferred_language == "mr"


def test_saved_language_applies_on_a_new_device(client, make_user, make_batch):
    learner = make_user(batch=make_batch())
    learner.profile.preferred_language = "hi"
    learner.profile.save()
    client.force_login(learner)  # no language cookie yet, like a new phone
    response = client.get("/")
    assert '<html lang="hi">' in response.content.decode()
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "hi"


def test_set_language_only_accepts_post(client):
    assert client.get(reverse("set_language")).status_code == 405


def test_header_language_select_lists_all_four_languages(client):
    html = client.get("/").content.decode()
    for code in ("en", "hi", "mr", "gu"):
        assert f'<option value="{code}"' in html


# --- sign in keeps the real behaviour ------------------------------------------------------


def test_sign_in_page_is_the_real_allauth_form(client):
    response = client.get(reverse("account_login"))
    html = response.content.decode()
    assert 'name="login"' in html and 'name="password"' in html and "csrfmiddlewaretoken" in html
    assert "Frontend preview" not in html and "Preview as" not in html
    assert reverse("account_reset_password") in html and reverse("register") in html


def test_wrong_password_shows_the_real_error(client, make_user):
    user = make_user()
    response = client.post(reverse("account_login"), {"login": user.email, "password": "nope"})
    assert response.status_code == 200
    html = response.content.decode()
    assert "not correct" in html and 'role="alert"' in html
    assert not client.session.get("_auth_user_id")


def test_right_password_signs_in(client, make_user):
    user = make_user()
    response = client.post(reverse("account_login"), {"login": user.email, "password": PASSWORD})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_sign_in_post_without_csrf_token_is_refused(make_user):
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    user = make_user()
    response = strict.post(reverse("account_login"), {"login": user.email, "password": PASSWORD})
    assert response.status_code == 403


# --- components ----------------------------------------------------------------------------


def test_as_input_adds_classes_and_accessibility_attributes():
    from apps.accounts.forms import RegistrationForm

    form = RegistrationForm({"email": "bad", "certificate_name": ""})
    form.is_valid()
    email = as_input(form["email"])
    assert 'class="input"' in email and 'aria-invalid="true"' in email
    assert f'aria-describedby="{form["email"].auto_id}-err"' in email
    language = as_input(form["preferred_language"])
    assert 'class="select"' in language
    name = as_input(form["certificate_name"])
    assert "aria-describedby" in name and "-hint" in name


def test_field_component_shows_errors_with_an_icon_and_password_reveal(client):
    html = client.post(reverse("account_login"), {"login": "", "password": ""}).content.decode()
    assert 'class="field-error"' in html and "data-reveal-pw" in html


# --- the staff-only styleguide -------------------------------------------------------------


def test_styleguide_needs_a_signed_in_staff_member(mentor_client):
    from django.test import Client

    assert Client().get(reverse("styleguide")).status_code == 302  # anonymous goes to sign in
    assert mentor_client.get(reverse("styleguide")).status_code == 403  # mentors are not staff


def test_learners_cannot_open_the_styleguide(client, make_user, make_batch):
    client.force_login(make_user(batch=make_batch()))
    assert client.get(reverse("styleguide")).status_code == 403


def test_styleguide_shows_every_component_and_all_four_languages(client, make_user):
    staff_client(client, make_user)
    response = client.get(reverse("styleguide"))
    assert response.status_code == 200
    html = response.content.decode()
    for marker in (
        "btn-primary", "btn-outline", "btn-ghost", "btn-danger", "badge--teal", "badge--danger",
        "card--edge", 'class="ring"', 'class="bar"', "mod-card", "stage-track", "field-error",
        "notice--danger", "state-panel", "save-pill", 'data-state="saving"', 'data-state="offline"',
        "palette__grid", "is-flagged", "is-answered", "timer", "confirm-dialog", "toast-region",
    ):  # fmt: skip
        assert marker in html, marker
    # Sample strings are written into the template on purpose (and only there).
    assert "साझा करने से पहले रिपोर्ट करें" in html  # Hindi
    assert "शेअर करण्यापूर्वी तक्रार करा" in html  # Marathi
    assert "શેર કરતાં પહેલાં ફરિયાદ કરો" in html  # Gujarati
    for lang in ("hi", "mr", "gu"):
        assert f'lang="{lang}"' in html


def test_question_map_legend_distinguishes_answered_from_marked_by_shape(client, make_user):
    staff_client(client, make_user)
    html = client.get(reverse("styleguide")).content.decode()
    legend = html.split("palette__legend")[1]
    assert '<i class="a">' in legend and '<i class="d">' in legend and '<i class="f">' in legend
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "is-flagged { border-style: dashed" in css


def test_translated_sample_text_lives_only_in_the_styleguide_template():
    """Stage 8 owns real translations; Devanagari/Gujarati elsewhere would be a hidden copy."""
    for path in (ROOT / "templates").rglob("*.html"):
        if path.name in ("styleguide.html", "login.html", "header.html"):
            continue  # login's language ticks and the header language names are labels, not copy
        assert not re.search("[ऀ-ॿ઀-૿]", path.read_text(encoding="utf-8")), path


def test_stage_one_pages_still_render_in_every_language(client, make_batch, settings):
    make_batch()
    for code in ("en", "hi", "mr", "gu"):
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = code
        for url in (reverse("register"), reverse("account_login"), reverse("privacy")):
            response = client.get(url)
            assert response.status_code == 200, (code, url)
            assert f'<html lang="{code}">' in response.content.decode()
