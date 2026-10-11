"""Dynamic 1200x630 social-preview ('Open Graph') cards for shops and products.

Rendered on request (cheap: a handful of draw calls, cached hard by the browser/
scraper via Cache-Control) rather than stored, so a card always reflects the
shop or product's current name, photo and stats with no extra DB writes.
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .extensions import db
from .models import Media

W, H = 1200, 630

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
TOP = (10, 58, 46)        # brand green, dark
BOTTOM = (19, 92, 68)      # brand green, lighter
AMBER = (255, 182, 72)
WHITE = (255, 255, 255)
CREAM = (222, 240, 230)
INK = (10, 58, 46)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


F_BOLD = "Poppins-Bold.ttf"
F_SEMI = "Poppins-SemiBold.ttf"
F_MED = "Poppins-Medium.ttf"
F_REG = "Poppins-Regular.ttf"


def _gradient_bg() -> Image.Image:
    base = Image.new("RGB", (W, H), TOP)
    px = base.load()
    for y in range(H):
        for x in range(0, W, 4):
            t = x / W * 0.4 + y / H * 0.6
            r = int(TOP[0] + (BOTTOM[0] - TOP[0]) * t)
            g = int(TOP[1] + (BOTTOM[1] - TOP[1]) * t)
            b = int(TOP[2] + (BOTTOM[2] - TOP[2]) * t)
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = (r, g, b)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse([820, -180, 1420, 420], fill=(255, 255, 255, 14))
    od.ellipse([950, 60, 1260, 370], fill=(255, 182, 72, 22))
    od.ellipse([-150, 380, 260, 790], fill=(255, 255, 255, 10))
    overlay = overlay.filter(ImageFilter.GaussianBlur(2))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    src_ratio, dst_ratio = img.width / img.height, w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = round(h * src_ratio)
    else:
        new_w = w
        new_h = round(w / src_ratio)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _bottom_scrim(img: Image.Image, strength: int = 215) -> Image.Image:
    overlay = Image.new("L", (1, H), color=0)
    for y in range(H):
        t = max(0, (y - H * 0.25) / (H * 0.75))
        overlay.putpixel((0, y), int(strength * (t ** 1.4)))
    overlay = overlay.resize((W, H))
    black = Image.new("RGBA", (W, H), (6, 20, 15, 255))
    black.putalpha(overlay)
    return Image.alpha_composite(img.convert("RGBA"), black).convert("RGB")


def _load_media(key: str | None) -> Image.Image | None:
    if not key:
        return None
    data = db.session.query(Media.full).filter(Media.key == key).scalar()
    if not data:
        return None
    try:
        return Image.open(io.BytesIO(data))
    except Exception:  # noqa: BLE001
        return None


def _wordmark(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle([x, y + 10, x + 34, y + 44], radius=7, fill=AMBER)
    draw.arc([x + 7, y, x + 27, y + 24], start=180, end=360, fill=(20, 70, 55), width=4)
    draw.text((x + 44, y - 2), "edwom", font=_font(F_BOLD, 24), fill=WHITE)


def _checkmark(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color) -> None:
    draw.line([(x, y + size * 0.5), (x + size * 0.35, y + size * 0.85), (x + size, y + size * 0.1)],
              fill=color, width=max(2, size // 7), joint="curve")


def _chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font,
          fg=INK, bg=(255, 255, 255), check: bool = False) -> int:
    tw = draw.textlength(text, font=font)
    pad_x, h = 22, 48
    icon_w = 26 if check else 0
    draw.rounded_rectangle([x, y, x + tw + icon_w + pad_x * 2, y + h], radius=24, fill=bg)
    text_x = x + pad_x
    if check:
        _checkmark(draw, x + pad_x, y + 15, 18, fg)
        text_x += icon_w
    draw.text((text_x, y + 11), text, font=font, fill=fg)
    return x + tw + icon_w + pad_x * 2 + 14


def _wrap(draw, text, font, max_width) -> list:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _price_text(pesewas) -> str:
    # "GHS" rather than the ₵ symbol: Poppins has no glyph for it, so it would
    # render as a tofu box in the rasterized image (the HTML site uses the
    # symbol fine via `cedi()`, since browsers fall back to a system font).
    return f"GHS {(pesewas or 0) / 100:,.2f}"


def render_shop_card(shop, count: int) -> bytes:
    banner = _load_media(shop.banner_key)
    f_chip = _font(F_SEMI, 21)
    f_sub = _font(F_REG, 25)

    if banner is not None:
        img = _cover_fit(banner, W, H)
        img = _bottom_scrim(img)
        text_fg, chip_bg, chip_fg = WHITE, WHITE, INK
    else:
        img = _gradient_bg()
        text_fg, chip_bg, chip_fg = WHITE, WHITE, INK

    draw = ImageDraw.Draw(img)
    _wordmark(draw, 80, 56)

    f_head = _font(F_BOLD, 56)
    lines = _wrap(draw, shop.name, f_head, W - 160)[:2]
    y = H - 300 if banner is not None else 230
    for line in lines:
        draw.text((80, y), line, font=f_head, fill=text_fg)
        y += 68

    draw.text((80, y + 6), f"{shop.town}, {shop.region}", font=f_sub,
               fill=CREAM if banner is None else (235, 240, 237))

    cy = H - 96
    cx = 80
    badge = "Verified business" if shop.verified else "Verification in progress"
    cx = _chip(draw, cx, cy, badge, f_chip, bg=(AMBER if shop.verified else chip_bg), fg=INK,
               check=shop.verified)
    cx = _chip(draw, cx, cy, f"On Edwom since {shop.since}", f_chip, bg=chip_bg, fg=chip_fg)
    cx = _chip(draw, cx, cy, f"{count} product{'' if count == 1 else 's'}", f_chip, bg=chip_bg, fg=chip_fg)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def render_product_card(product) -> bytes:
    cover = _load_media(product.cover_key)
    f_chip = _font(F_SEMI, 21)
    f_price = _font(F_BOLD, 44)

    if cover is not None:
        img = _cover_fit(cover, W, H)
        img = _bottom_scrim(img)
    else:
        img = _gradient_bg()

    draw = ImageDraw.Draw(img)
    _wordmark(draw, 80, 56)

    f_head = _font(F_BOLD, 50)
    lines = _wrap(draw, product.name, f_head, W - 160)[:2]
    y = H - 300 if cover is not None else 220
    for line in lines:
        draw.text((80, y), line, font=f_head, fill=WHITE)
        y += 62

    price_text = _price_text(product.price)
    draw.text((80, y + 8), price_text, font=f_price, fill=AMBER)
    if product.discount_pct:
        old_price = _price_text(product.compare_at)
        px = 80 + draw.textlength(price_text, font=f_price) + 20
        draw.text((px, y + 22), old_price, font=_font(F_REG, 24), fill=(220, 220, 220))

    cy = H - 96
    cx = 80
    cx = _chip(draw, cx, cy, f"Sold by {product.shop.name}", f_chip, bg=WHITE, fg=INK)
    stock_label = "In stock" if product.stock > 0 else "Sold out"
    cx = _chip(draw, cx, cy, stock_label, f_chip, bg=WHITE, fg=INK)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
