# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks and processing for uploaded photos and documents."""
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_IMAGE_SIDE = 2000  # pixels; larger photos are scaled down to save space


def validate_image(file):
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError(_("The photo must be smaller than 20 MB."))
    from PIL import Image, UnidentifiedImageError

    try:
        file.seek(0)
        with Image.open(file) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError(_("The file must be a JPEG or PNG image."))
    finally:
        file.seek(0)


def validate_pdf(file):
    if file.size > MAX_PDF_BYTES:
        raise ValidationError(_("The document must be smaller than 25 MB."))
    file.seek(0)
    header = file.read(5)
    file.seek(0)
    if header != b"%PDF-":
        raise ValidationError(_("The file must be a PDF."))


def process_image(file):
    """Rotate to the camera orientation, scale down, and re-save as JPEG without EXIF data.

    Removing EXIF data strips GPS location and camera details from photos taken on phones.
    """
    from PIL import Image, ImageOps

    file.seek(0)
    with Image.open(file) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.convert("RGBA").split()[-1])
            img = background
        out = BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    return ContentFile(out.getvalue(), name="photo.jpg")
