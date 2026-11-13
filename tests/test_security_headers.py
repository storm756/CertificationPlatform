"""Stage 10: every Django response carries a strict CSP and the other security headers (architecture §16)."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.security import STAFF_TOOLS, STRICT, YOUTUBE_SCRIPT, policy_for, render


def _csp(response) -> dict[str, list[str]]:
    return {
        part.split()[0]: part.split()[1:]
        for part in response["Content-Security-Policy"].split(";")
        if part.strip()
    }


@pytest.mark.parametrize("name", ["home", "register", "privacy", "help", "verify", "account_login"])
def test_public_pages_get_the_strict_policy(client, db, name):
    response = client.get(reverse(name))
    csp = _csp(response)
    assert csp["default-src"] == ["'self'"]
    assert csp["script-src"] == ["'self'"]
    assert csp["style-src"] == ["'self'"]
    assert csp["frame-src"] == ["https://www.youtube-nocookie.com"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert csp["object-src"] == ["'none'"]
    assert csp["form-action"] == ["'self'"]
    assert "'unsafe-inline'" not in response["Content-Security-Policy"]
    assert "'unsafe-eval'" not in response["Content-Security-Policy"]
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert "camera=()" in response["Permissions-Policy"]


def test_learner_pages_get_the_strict_policy(learner_client):
    response = learner_client.get(reverse("learn_catalogue"))
    assert response.status_code == 200
    assert response["Content-Security-Policy"] == render(STRICT)


def test_404_and_redirects_also_carry_the_policy(client, db):
    assert client.get("/no-such-page/")["Content-Security-Policy"] == render(STRICT)
    assert client.get(reverse("learn_catalogue"))["Content-Security-Policy"] == render(STRICT)


@pytest.mark.parametrize("path", ["/admin/", "/rosetta/"])
def test_staff_tools_get_their_own_policy(client, db, path):
    csp = _csp(client.get(path))
    assert csp["default-src"] == ["'self'"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert "'unsafe-inline'" in csp["script-src"]  # django-unfold needs it; staff only, behind 2FA


def test_youtube_script_only_when_the_view_asks_for_it():
    request = RequestFactory().get("/learn/1/a-film/")
    assert YOUTUBE_SCRIPT not in policy_for(request)["script-src"]
    request.csp_youtube = True
    assert policy_for(request)["script-src"] == ["'self'", YOUTUBE_SCRIPT]
    staff = RequestFactory().get("/admin/")
    staff.csp_youtube = True
    assert policy_for(staff) is STAFF_TOOLS


def test_the_caddy_default_policy_matches_django():
    """Caddy adds the strict policy to the files it serves itself; it must be the same one."""
    from pathlib import Path

    caddyfile = (Path(__file__).resolve().parents[1] / "deploy/caddy/Caddyfile").read_text()
    assert f'?Content-Security-Policy "{render(STRICT)}"' in caddyfile
    assert "script-src 'self' https://www.youtube.com" not in caddyfile


def test_hsts_in_prod_settings_and_caddy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    prod = (root / "config/settings/prod.py").read_text()
    assert "SECURE_HSTS_SECONDS = 31536000" in prod
    assert "SECURE_HSTS_INCLUDE_SUBDOMAINS = True" in prod
    caddyfile = (root / "deploy/caddy/Caddyfile").read_text()
    assert 'import common "max-age=31536000; includeSubDomains"' in caddyfile
