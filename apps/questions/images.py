"""Hotspot pictures: accept only a real raster image, re-encode it, strip metadata (§13.1 safety).

The uploaded bytes are never stored or served as they arrived. Pillow decodes them, a size cap
and a pixel cap apply, and a fresh PNG/JPEG/WebP is written without EXIF or any other metadata.
SVG is not accepted at all (it can carry script).
"""

import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from .models import QuestionImage

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_SIDE = 2000
EXTENSIONS = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}


class ImageRejected(ValueError):
    pass


def store_image(upload) -> QuestionImage:
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageRejected("The picture is larger than 5 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(BytesIO(data))
        fmt = (probe.format or "").upper()
        if fmt not in EXTENSIONS:
            raise ImageRejected("Use a PNG, JPEG or WebP picture.")
        if probe.width * probe.height > MAX_PIXELS:
            raise ImageRejected("The picture has too many pixels.")
        probe.verify()
        image = Image.open(BytesIO(data))
        image.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise ImageRejected("That file is not a valid picture.") from exc
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    clean = Image.new(image.mode, image.size)  # a new image carries no metadata at all
    clean.paste(image)
    out = BytesIO()
    clean.save(out, format=fmt)
    payload = out.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    existing = QuestionImage.objects.filter(sha256=digest).first()
    if existing:
        return existing
    record = QuestionImage(
        sha256=digest, format=EXTENSIONS[fmt], width=clean.width, height=clean.height
    )
    record.file.save(f"{digest[:32]}.{EXTENSIONS[fmt]}", ContentFile(payload), save=True)
    return record
