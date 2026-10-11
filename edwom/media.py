"""Image uploads: validate, auto-rotate, strip metadata, resize and convert to WebP.

Images are stored in the database (Media table). That keeps them safe on Render, whose
disk is wiped on every deploy, with no extra service to set up. To move to a CDN later
(Cloudinary, S3), only this module and the /media route need to change.
"""
import io
import secrets

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from .extensions import db
from .models import Media

Image.MAX_IMAGE_PIXELS = 50_000_000  # guards against decompression bombs
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO", "BMP"}
SIZES = {
    "product": {"full": 1600, "thumb": 640},
    "logo": {"full": 512, "thumb": 160},
    "banner": {"full": 2400, "thumb": 960},
}


class ImageError(ValueError):
    pass


def _encode(img: Image.Image, max_side: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    copy.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()


def process(file_storage, kind: str = "product") -> dict:
    """Return {'full': bytes, 'thumb': bytes, 'width', 'height', 'size'} or raise ImageError."""
    name = getattr(file_storage, "filename", "") or "photo"
    data = file_storage.read()
    if not data:
        raise ImageError(f"{name} is empty.")
    limit_mb = current_app.config["MAX_PHOTO_MB"]
    if len(data) > limit_mb * 1024 * 1024:
        raise ImageError(f"{name} is larger than {limit_mb} MB.")
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise ImageError(f"{name} isn't a photo we can read. Use JPG, PNG or WebP.")
    if fmt not in ALLOWED_FORMATS:
        raise ImageError(f"{name}: {fmt} isn't supported. Use JPG, PNG or WebP.")
    if min(img.size) < 200 and kind != "logo":
        raise ImageError(f"{name} is too small. Use a photo at least 600 pixels wide.")
    img = ImageOps.exif_transpose(img)  # fixes sideways phone photos, drops EXIF/GPS data
    if img.mode in ("P", "LA"):
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    sizes = SIZES[kind]
    full = _encode(img, sizes["full"])
    thumb = _encode(img, sizes["thumb"])
    width, height = img.size
    scale = min(1, sizes["full"] / max(width, height))
    return {"full": full, "thumb": thumb, "width": round(width * scale), "height": round(height * scale),
            "size": len(full)}


def store(processed: dict, kind: str, shop_id: int, user_id=None, product_id=None, position: int = 0) -> Media:
    media = Media(key=secrets.token_hex(16), kind=kind, shop_id=shop_id, product_id=product_id, position=position,
                  width=processed["width"], height=processed["height"], size_bytes=processed["size"],
                  full=processed["full"], thumb=processed["thumb"], uploaded_by=user_id)
    db.session.add(media)
    return media


def real_files(files) -> list:
    return [f for f in files if f and getattr(f, "filename", "")]
