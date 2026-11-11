"""Uploads for content (§13.1 upload safety): size caps and real file-type sniffing.

Pictures are decoded and re-encoded by Pillow (pixel cap, EXIF and other metadata stripped). A PDF
must start with %PDF-, an MP4 must carry an ISO-BMFF `ftyp` box. The name the browser sent is
never used for the stored file.
"""

import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from .models import MediaAsset, MediaKind

LIMITS = {
    MediaKind.PDF: 20 * 1024 * 1024,
    MediaKind.IMAGE: 5 * 1024 * 1024,
    MediaKind.POSTER: 5 * 1024 * 1024,
    MediaKind.MP4: 150 * 1024 * 1024,
}
MAX_PIXELS = 25_000_000
MAX_SIDE = 1600
IMAGE_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
}


class MediaRejected(ValueError):
    pass


def _read(upload, limit):
    data = upload.read(limit + 1)
    if len(data) > limit:
        raise MediaRejected(f"The file is larger than {limit // (1024 * 1024)} MB.")
    if not data:
        raise MediaRejected("The file is empty.")
    return data


def clean_image(data: bytes) -> tuple[bytes, str, str, int, int]:
    """(bytes, extension, content type, width, height) of a fresh, metadata-free picture."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(BytesIO(data))
        fmt = (probe.format or "").upper()
        if fmt not in IMAGE_FORMATS:
            raise MediaRejected("Use a PNG, JPEG or WebP picture.")
        if probe.width * probe.height > MAX_PIXELS:
            raise MediaRejected("The picture has too many pixels.")
        probe.verify()
        image = Image.open(BytesIO(data))
        image.load()
    except MediaRejected:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise MediaRejected("That file is not a valid picture.") from exc
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    clean = Image.new(image.mode, image.size)  # a new image carries no metadata at all
    clean.paste(image)
    out = BytesIO()
    clean.save(out, format=fmt)
    ext, content_type = IMAGE_FORMATS[fmt]
    return out.getvalue(), ext, content_type, clean.width, clean.height


def store(upload, module, kind: str, *, title: str = "", language: str = "en") -> MediaAsset:
    if kind not in LIMITS:
        raise MediaRejected("That kind of file can't be uploaded here.")
    data = _read(upload, LIMITS[kind])
    width = height = None
    if kind in (MediaKind.IMAGE, MediaKind.POSTER):
        data, ext, content_type, width, height = clean_image(data)
    elif kind == MediaKind.PDF:
        if not data.startswith(b"%PDF-"):
            raise MediaRejected("That file is not a PDF.")
        ext, content_type = "pdf", "application/pdf"
    else:  # MP4
        if len(data) < 12 or data[4:8] != b"ftyp":
            raise MediaRejected("That file is not an MP4 film.")
        ext, content_type = "mp4", "video/mp4"
    digest = hashlib.sha256(data).hexdigest()
    existing = MediaAsset.objects.filter(module=module, kind=kind, sha256=digest).first()
    if existing:
        return existing
    asset = MediaAsset(
        module=module, kind=kind, language=language, title=" ".join(title.split())[:200],
        content_type=content_type, sha256=digest, size=len(data), width=width, height=height,
    )  # fmt: skip
    asset.file.save(f"{module.number}-{kind}-{digest[:24]}.{ext}", ContentFile(data), save=True)
    return asset
