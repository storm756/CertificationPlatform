"""The certificate PDF (§12): WeasyPrint with an allowlist-only URL fetcher, and a segno QR code.

Nothing in the PDF comes from the network or from an arbitrary file. The template asks for its
fonts, logos, signature images and QR code by `ccfr-asset:<name>` and the fetcher answers only
those names, from files fixed here or in settings. Any other URL (http, file, data, a relative path)
is refused, so text typed by a learner or an author can never make the renderer read anything.
The learner's name and every other value are inserted by the Django template with autoescaping,
never into the <style> block.
"""

import io
import logging
from datetime import date
from pathlib import Path

import segno
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

logger = logging.getLogger(__name__)

SCHEME = "ccfr-asset:"
TEMPLATE = "certificates/pdf/certificate.html"
STATIC = Path(settings.BASE_DIR) / "static"
FONTS = [
    "baloo2-latin.woff2",
    "hind-latin-400.woff2",
    "hind-latin-600.woff2",
]
LOGOS = {"sakec": "shah-anchor-logo.png", "cyberpeace": "cyberpeace-logo.png"}
MIME = {".woff2": "font/woff2", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
SIGNATURE_SUFFIXES = (".png", ".jpg", ".jpeg")


def signature_dir() -> Path:
    return Path(settings.CERTIFICATE_PRIVATE_ROOT) / "signatures"


def signature_file(signatory: dict) -> Path | None:
    """The signatory's image if it is in place, else None (the name prints over a blank line).

    Only a plain file name with a picture suffix is accepted, so a setting can never point the
    renderer outside the signatures folder."""
    name = signatory.get("image") or ""
    if not name or Path(name).name != name or Path(name).suffix.lower() not in SIGNATURE_SUFFIXES:
        return None
    path = signature_dir() / name
    return path if path.is_file() else None


def missing_signatures() -> list[str]:
    """Names of signatories whose signature image is not in place (guard A, D36)."""
    return [s["name"] for s in settings.CERTIFICATE_SIGNATORIES if signature_file(s) is None]


class AllowlistFetcher(URLFetcher):
    """Answers exactly the assets named at construction; refuses every other URL."""

    def __init__(self, files: dict[str, Path], blobs: dict[str, tuple[bytes, str]]):
        super().__init__(allowed_protocols=(), allow_redirects=False, fail_on_errors=False)
        self._files = files
        self._blobs = blobs
        self.requested: list[str] = []
        self.refused: list[str] = []

    def fetch(self, url, headers=None):
        self.requested.append(url)
        name = url[len(SCHEME) :] if url.startswith(SCHEME) else None
        if name in self._blobs:
            body, mime = self._blobs[name]
        elif name in self._files:
            path = self._files[name]
            body, mime = path.read_bytes(), MIME[path.suffix.lower()]
        else:
            self.refused.append(url)
            logger.warning("certificate PDF: refused a resource that is not on the allowlist")
            raise ValueError("Resource not on the certificate allowlist")
        return URLFetcherResponse(url, body, {"Content-Type": mime})


def long_date(iso: str) -> str:
    """'2026-11-13' -> '13 November 2026' (English, no leading zero)."""
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%B %Y}"


def verify_url(code: str) -> str:
    scheme = "http" if settings.DEBUG else "https"
    return f"{scheme}://{settings.SITE_DOMAIN}/verify/{code}/"


def qr_png(url: str) -> bytes:
    out = io.BytesIO()
    segno.make(url, error="m", micro=False).save(out, kind="png", scale=8, border=0, dark="#071a3d")
    return out.getvalue()


def build_fetcher(code: str) -> tuple[AllowlistFetcher, list[dict]]:
    """The fetcher for one certificate, and the signatories with their image asset names."""
    files = {f"font/{name}": STATIC / "fonts" / name for name in FONTS}
    files |= {f"img/{key}": STATIC / "img" / name for key, name in LOGOS.items()}
    signatories = []
    for i, signatory in enumerate(settings.CERTIFICATE_SIGNATORIES, start=1):
        path = signature_file(signatory)
        asset = f"signature/{i}" if path else ""
        if path:
            files[asset] = path
        signatories.append({**signatory, "asset": asset})
    blobs = {"qr": (qr_png(verify_url(code)), "image/png")}
    return AllowlistFetcher(files, blobs), signatories


def render(
    snapshot: dict, *, certificate_no: str, verify_code: str
) -> tuple[bytes, AllowlistFetcher]:
    """(PDF bytes, the fetcher used) for a certificate. Pure: reads only the allowlisted assets."""
    fetcher, signatories = build_fetcher(verify_code)
    with translation.override("en"):  # certificates are English only (D10)
        html = render_to_string(
            TEMPLATE,
            {
                "s": snapshot,
                "certificate_no": certificate_no,
                "completed_on": long_date(snapshot["completed_on"]),
                "verify_text": verify_url(verify_code).split("://", 1)[1].rstrip("/"),
                "signatories": signatories,
                "asset": SCHEME,
            },
        )
    pdf = HTML(string=html, base_url=None, url_fetcher=fetcher).write_pdf()
    return pdf, fetcher
