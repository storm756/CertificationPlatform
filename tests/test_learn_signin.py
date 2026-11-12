"""D34: everything under /learn/ needs a signed-in user; the public pages stay public. D35: media
goes to Caddy through X-Accel-Redirect when it runs behind Caddy. Invented content only."""

from urllib.parse import quote

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.content import media, services
from apps.content.models import MediaKind, Module, Unit, UnitType, VersionSource

pytestmark = pytest.mark.django_db


@pytest.fixture
def course(db):
    """Module 1 with a reading, a handout (with a PDF), a film (with an MP4) and a check unit."""
    module, _ = Module.objects.get_or_create(number=1, defaults={"slug": "module-1", "title_key": "x"})  # fmt: skip
    module.title = "Invented module"
    module.save()
    Module.objects.get_or_create(number=10, defaults={"slug": "module-10", "title_key": "x", "kind": "capstone"})  # fmt: skip
    pdf = media.store(SimpleUploadedFile("h.pdf", b"%PDF-1.4 invented"), module, MediaKind.PDF)
    mp4 = media.store(SimpleUploadedFile("f.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 20), module, MediaKind.MP4)  # fmt: skip
    units = {
        "t1": (UnitType.READING, [{"type": "reveal", "prompt": "P?", "answer": "A."}]),
        "handout": (UnitType.HANDOUT, [{"type": "attachment", "asset": pdf.pk, "label": "PDF"}]),
        "film": (UnitType.VIDEO, [{"type": "video", "mp4": mp4.pk}]),
        "check": (
            UnitType.CHECK,
            [{"type": "mythfact", "statement": "S.", "is_fact": True, "why": "W."}],
        ),  # fmt: skip
    }
    for order, (slug, (kind, blocks)) in enumerate(units.items(), start=1):
        unit = Unit.objects.create(module=module, slug=slug, type=kind, order=order, nominal_minutes=5)  # fmt: skip
        version = services.add_version(unit, f"Title {slug}", blocks, source=VersionSource.EDITOR)
        services.publish(version, None, system=True)
    return {"pdf": pdf, "mp4": mp4}


def pages(course):
    return [
        reverse("learn_catalogue"),
        reverse("learn_module", args=[1]),
        reverse("learn_module", args=[10]),  # the capstone page
        reverse("learn_unit", args=[1, "t1"]),
        reverse("learn_unit", args=[1, "handout"]),
        reverse("learn_unit", args=[1, "film"]),
        reverse("learn_unit", args=[1, "check"]),
        reverse("learn_media", args=[course["pdf"].pk]),
        reverse("learn_media", args=[course["mp4"].pk]),
    ]


def endpoints():
    return [
        (reverse("learn_check"), {"m": 1, "u": "check", "question": "x", "choice": "y"}),
        (reverse("learn_heartbeat"), {"m": 1, "u": "t1"}),
        (reverse("learn_complete", args=[1, "t1"]), {"how": "end"}),
        (reverse("learn_block", args=[1, "t1", 0]), {}),
        (reverse("learn_block", args=[1, "check", 0]), {"pick": "fact"}),
    ]


def test_every_learn_page_sends_a_signed_out_visitor_to_sign_in_and_back(client, course):
    login = reverse("account_login")
    for url in pages(course):
        response = client.get(url)
        assert response.status_code == 302, url
        assert response["Location"] == f"{login}?next={quote(url)}", url


def test_every_learn_endpoint_refuses_a_signed_out_post(client, course):
    for url, data in endpoints():
        response = client.post(url, data)
        assert response.status_code == 403, url
        assert b"A." not in response.content and b"W." not in response.content


def test_every_learn_page_and_endpoint_works_when_signed_in(learner_client, course):
    for url in pages(course):
        assert learner_client.get(url).status_code == 200, url
    statuses = {url: learner_client.post(url, data).status_code for url, data in endpoints()}
    # the check endpoint refuses a made-up question (400): it was reached, not blocked
    assert statuses.pop(reverse("learn_check")) == 400
    assert set(statuses.values()) == {200}, statuses


def test_sign_in_brings_the_visitor_back_to_the_page_they_asked_for(client, course, learner):
    from .conftest import PASSWORD

    url = reverse("learn_unit", args=[1, "t1"])
    login = client.get(url)["Location"]
    response = client.post(login, {"login": learner.email, "password": PASSWORD})
    assert response.status_code == 302 and response["Location"] == url


def test_the_public_pages_stay_public(client):
    for name in ("home", "register", "account_login", "privacy"):
        assert client.get(reverse(name)).status_code == 200, name


def test_media_is_private_and_handed_to_caddy_when_behind_it(learner_client, course, settings):
    url = reverse("learn_media", args=[course["mp4"].pk])
    direct = learner_client.get(url)
    assert direct["Cache-Control"] == "private, max-age=3600"
    assert b"".join(direct.streaming_content).startswith(b"\x00\x00\x00\x18ftyp")
    settings.MEDIA_ACCEL_REDIRECT = True
    handed = learner_client.get(url)
    assert handed.status_code == 200 and handed.content == b""
    assert handed["X-Accel-Redirect"] == "/" + course["mp4"].file.name
    assert handed["Content-Type"] == "video/mp4" and handed["Cache-Control"].startswith("private")
    pdf = learner_client.get(reverse("learn_media", args=[course["pdf"].pk]))
    assert pdf["Content-Disposition"] == 'inline; filename="module-1-handout.pdf"'


def test_handout_pdfs_are_not_static_files():
    from django.conf import settings
    from django.contrib.staticfiles import finders

    assert finders.find("handouts/m1.pdf") is None
    assert (settings.BASE_DIR / "apps/content/data/handouts/m1.pdf").exists()
