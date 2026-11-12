import io
import re

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


def normalize_png_phone(raw: str) -> str:
    """
    Normalise PNG numbers so duplicates match:
      '+675 7907 0847', '67579070847', '7907 0847' -> '79070847'
    Non-PNG or malformed input is returned digits-only.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("675") and len(digits) == 11:
        digits = digits[3:]
    return digits


def normalize_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip()).title()


def normalize_nid(raw: str) -> str:
    return re.sub(r"[\s-]", "", (raw or "")).upper()


class PhotoError(ValueError):
    pass


def clean_member_photo(upload, *, max_bytes: int, size_px: int) -> ContentFile:
    """
    Never trust the client image. Re-encode it server-side:
      - rejects non-images / oversized uploads
      - applies EXIF rotation, then strips ALL metadata (incl. GPS location)
      - centre-crops to a square and resizes to size_px
      - always stores a baseline JPEG (WeasyPrint/print-friendly)
    """
    if upload.size > max_bytes:
        raise PhotoError(f"Photo too large ({upload.size // 1024} KB)")
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoError("File is not a valid image")

    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (size_px, size_px), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return ContentFile(buf.getvalue(), name="photo.jpg")
