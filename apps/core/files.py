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


MAX_PLAN_BYTES = 50 * 1024 * 1024
PLAN_EXTENSIONS = ("pdf", "dwg", "dxf")


def validate_plan(file):
    """Floor plans and drawings: PDF, or AutoCAD drawings (DWG or DXF)."""
    name = (getattr(file, "name", "") or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in PLAN_EXTENSIONS:
        raise ValidationError(_("The plan must be a PDF or an AutoCAD drawing (.dwg or .dxf)."))
    if file.size > MAX_PLAN_BYTES:
        raise ValidationError(_("The plan must be smaller than 50 MB."))
    file.seek(0)
    head = file.read(1024)
    file.seek(0)
    if ext == "pdf":
        ok = head.startswith(b"%PDF-")
    elif ext == "dwg":
        ok = head.startswith(b"AC10")  # every DWG version since AutoCAD R10 starts AC10xx
    else:  # DXF is text starting with a section marker, or the binary form with its own sentinel
        ok = head.startswith(b"AutoCAD Binary DXF") or (b"SECTION" in head and b"\x00" not in head)
    if not ok:
        raise ValidationError(_("The file's contents do not match its type."))


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


MAX_FILES_AT_ONCE = 20


def title_from_filename(name, limit=200):
    """A readable title for a file that was dropped in without one: "Ground_floor-plan.pdf" -> "Ground floor plan"."""
    stem = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    return " ".join(stem.replace("_", " ").replace("-", " ").split())[:limit] or "Untitled"


def file_each(uploads, file_one):
    """File several uploads one at a time. file_one(upload) returns None, or what was wrong with it.

    Returns (how many were filed, [problems as "name: reason"]). Files beyond the limit are not filed."""
    from django.core.exceptions import ValidationError

    filed, problems = 0, []
    for upload in uploads[:MAX_FILES_AT_ONCE]:
        try:
            problem = file_one(upload)
        except ValidationError as exc:
            problem = exc.messages[0]
        if problem:
            problems.append(f"{upload.name}: {problem}")
        else:
            filed += 1
    if len(uploads) > MAX_FILES_AT_ONCE:
        problems.append(str(_("Only the first %(n)s files were filed. Add the rest in another go.")
                            % {"n": MAX_FILES_AT_ONCE}))
    return filed, problems
