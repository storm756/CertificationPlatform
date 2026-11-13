"""The landing page's sample certificate (Stage 9 follow-up).

It must be rendered from the real certificate template, with an invented name, the public domain
and no real signature image, and the landing page must show it instead of the old prototype image.
"""

import io
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from pypdf import PdfReader

from apps.certificates import pdf
from apps.certificates.management.commands import certificate_sample


def _text(path: Path) -> str:
    return " ".join(page.extract_text() for page in PdfReader(io.BytesIO(path.read_bytes())).pages)


def test_sample_pdf_uses_the_real_template_and_invented_details(tmp_path):
    out = tmp_path / "sample.pdf"
    call_command("certificate_sample", "--out", str(out))
    text = _text(out)
    assert certificate_sample.SAMPLE_NAME in text
    assert settings.PROGRAMME_NAME in text
    assert certificate_sample.SAMPLE_NUMBER in text
    assert "cyberfirstresponse.io/verify/" in text
    assert "localhost" not in text
    # the old prototype wording must not come back
    assert "Incident First Response" not in text
    assert "AICTE" not in text


def test_sample_never_loads_a_signature_image(tmp_path, monkeypatch):
    real = tmp_path / "signature.png"
    real.write_bytes(b"not used")
    monkeypatch.setattr(pdf, "signature_file", lambda signatory: real)
    seen = []
    original = pdf.build_fetcher

    def spy(code):
        fetcher, signatories = original(code)
        seen.extend(s["asset"] for s in signatories)
        return fetcher, signatories

    monkeypatch.setattr(pdf, "build_fetcher", spy)
    call_command("certificate_sample", "--out", str(tmp_path / "s.pdf"))
    assert seen and all(asset == "" for asset in seen)


def test_sample_rejects_other_extensions(tmp_path):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("certificate_sample", "--out", str(tmp_path / "s.jpg"))


@pytest.mark.django_db
def test_landing_shows_the_sample_not_the_old_prototype_image(client):
    html = client.get("/").content.decode()
    assert "img/certificate-sample.png" in html
    assert "cert-front" not in html
    assert (Path(settings.BASE_DIR) / "static/img/certificate-sample.png").is_file()
    assert not (Path(settings.BASE_DIR) / "static/img/cert-front.jpg").exists()
