"""Render a sample certificate with invented details, for the landing page (Stage 9 follow-up).

    python manage.py certificate_sample --out static/img/certificate-sample.png

It uses the real certificate template and renderer (apps/certificates/pdf.py), so the landing page
always shows the design learners actually get. Run it again whenever the template changes (for
example when the final design, the emblem or the signature images arrive) and commit the new image.

Never use real signature images here: the output is committed to a public repo (D22). Signature
files are switched off for the sample, so the names print over blank lines.

`--out` ending in .pdf writes the PDF; ending in .png rasterises page 1 with pypdfium2 (a
development dependency, requirements-dev.txt).
"""

from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings
from django.utils import timezone

from apps.certificates import pdf
from apps.certificates.services import NSQF_PENDING

SAMPLE_NAME = "Your Name Here"
SAMPLE_NUMBER = f"{settings.CERTIFICATE_PREFIX}-2026-SAKEC-000000"
SAMPLE_CODE = "0000000000"  # a valid-looking code that matches no certificate
PUBLIC_DOMAIN = "cyberfirstresponse.io"


def sample_snapshot() -> dict:
    today = timezone.localdate().isoformat()
    return {
        "certificate_name": SAMPLE_NAME,
        "qualification": settings.CERTIFICATE_QUALIFICATION,
        "programme": settings.PROGRAMME_NAME,
        "programme_short": settings.PROGRAMME_SHORT,
        "batch": {"id": 0, "code": "SAMPLE", "name": "Sample batch"},
        "centre_code": "SAKEC",
        "completed_on": today,
        "issued_on": today,
        "grade": "A",
        "nsqf": {"approved": False, "level": "", "credits": "", "line": NSQF_PENDING},
    }


class Command(BaseCommand):
    help = "Render a sample certificate (invented name) to PDF or PNG for the landing page."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Output path ending in .pdf or .png")
        parser.add_argument("--width", type=int, default=1600, help="PNG width in pixels")

    def handle(self, *args, out, width, **options):
        path = Path(out)
        if path.suffix.lower() not in (".pdf", ".png"):
            raise CommandError("--out must end in .pdf or .png")
        # The sample is public: never load a real signature image into it. Its QR code and verify
        # line show the public domain (D19), not the developer's localhost.
        with (
            mock.patch.object(pdf, "signature_file", lambda signatory: None),
            override_settings(SITE_DOMAIN=PUBLIC_DOMAIN, DEBUG=False),
        ):
            data, _fetcher = pdf.render(
                sample_snapshot(), certificate_no=SAMPLE_NUMBER, verify_code=SAMPLE_CODE
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".pdf":
            path.write_bytes(data)
        else:
            path.write_bytes(_png(data, width))
        self.stdout.write(f"Wrote {path}")


def _png(pdf_bytes: bytes, width: int) -> bytes:
    import io

    try:
        import pypdfium2
    except ImportError as exc:  # pragma: no cover - dev tool only
        raise CommandError(
            "PNG output needs pypdfium2: pip install -r requirements-dev.txt"
        ) from exc
    page = pypdfium2.PdfDocument(pdf_bytes)[0]
    scale = width / page.get_width()
    image = page.render(scale=scale).to_pil().convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
