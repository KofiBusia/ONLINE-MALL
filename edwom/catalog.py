"""Creating and editing products and shop images. Shared by shop owners and the super admin."""
from flask import current_app, request
from flask_login import current_user

from . import media as media_lib
from .data import CAT_LABELS, CATEGORY_ICON
from .extensions import db
from .models import Media, Product, Shop
from .services import audit
from .utils import to_int, to_pesewas

PRODUCT_FIELDS = ("name", "price", "compare_at", "stock", "sku", "category", "description", "specs")


def product_form_data(product=None) -> dict:
    if product is None:
        return {"name": "", "price": "", "compare_at": "", "stock": 10, "sku": "", "category": "fashion",
                "description": "", "specs": "", "published": True}
    return {"name": product.name, "price": f"{product.price / 100:.2f}",
            "compare_at": f"{product.compare_at / 100:.2f}" if product.compare_at else "",
            "stock": product.stock, "sku": product.sku or "", "category": product.category,
            "description": product.description or "", "specs": product.specs or "",
            "published": product.published}


def save_product(shop: Shop, product=None):
    """Validate the posted form and photos; create or update the product.

    Returns (product, data, errors). Nothing is saved when there are errors.
    """
    form = request.form
    data = {k: (form.get(k) or "").strip() for k in PRODUCT_FIELDS}
    data["published"] = form.get("published") == "1"
    errors = {}

    price = to_pesewas(data["price"])
    compare_at = to_pesewas(data["compare_at"]) if data["compare_at"] else None
    stock = to_int(data["stock"], -1)
    if len(data["name"]) < 3:
        errors["name"] = "Enter a product name (at least 3 characters)."
    if price is None:
        errors["price"] = "Enter a price in cedis, e.g. 120 or 85.50."
    if data["compare_at"] and (compare_at is None or (price and compare_at <= price)):
        errors["compare_at"] = "The old price must be higher than the selling price, or leave it empty."
    if stock < 0 or stock > 1_000_000:
        errors["stock"] = "Enter how many you have in stock."
    if data["category"] not in CAT_LABELS:
        errors["category"] = "Choose a category."

    # Photos: existing ones to keep, plus new uploads
    existing = list(product.images) if product else []
    remove_keys = set(form.getlist("remove_photo"))
    kept = [m for m in existing if m.key not in remove_keys]
    uploads = media_lib.real_files(request.files.getlist("photos"))
    limit = current_app.config["MAX_PHOTOS_PER_PRODUCT"]
    if len(kept) + len(uploads) > limit:
        errors["photos"] = f"A product can have up to {limit} photos. Remove some first."
    processed = []
    if "photos" not in errors:
        for f in uploads:
            try:
                processed.append(media_lib.process(f, "product"))
            except media_lib.ImageError as exc:
                errors["photos"] = str(exc)
                break
    if data["published"] and not kept and not processed and not errors:
        errors["photos"] = "Add at least one photo before publishing, or save it as a draft."

    if errors:
        return product, data, errors

    creating = product is None
    if creating:
        product = Product(shop_id=shop.id)
        db.session.add(product)
    product.name = data["name"][:90]
    product.price = price
    product.compare_at = compare_at
    product.stock = stock
    product.sku = data["sku"][:40] or None
    product.category = data["category"]
    product.icon = CATEGORY_ICON.get(data["category"], "🛍️")
    product.description = data["description"][:4000]
    product.specs = data["specs"][:2000]
    product.published = data["published"]
    db.session.flush()

    for m in existing:
        if m.key in remove_keys:
            db.session.delete(m)
    new_media = [media_lib.store(p, "product", shop.id, current_user.id, product.id) for p in processed]
    ordered = kept + new_media
    cover = form.get("cover") or ""
    if cover.startswith("new-") and cover[4:].isdigit() and int(cover[4:]) < len(new_media):
        cover = new_media[int(cover[4:])].key
    ordered.sort(key=lambda m: 0 if m.key == cover else 1)  # stable: keeps the rest in order
    for i, m in enumerate(ordered):
        m.position = i
    audit("product.create" if creating else "product.update", f"{shop.name}: {product.name}")
    db.session.commit()
    db.session.refresh(product)
    return product, data, {}


def save_shop_images(shop: Shop) -> dict:
    """Handle optional logo/banner uploads and removals. Returns errors (nothing saved on error)."""
    errors, ready = {}, {}
    for kind in ("logo", "banner"):
        upload = request.files.get(kind)
        if upload and upload.filename:
            try:
                ready[kind] = media_lib.process(upload, kind)
            except media_lib.ImageError as exc:
                errors[kind] = str(exc)
    if errors:
        return errors
    for kind in ("logo", "banner"):
        attr = f"{kind}_key"
        if kind in ready or request.form.get(f"remove_{kind}"):
            old = getattr(shop, attr)
            if old:
                Media.query.filter_by(key=old, shop_id=shop.id).delete()
            setattr(shop, attr, None)
        if kind in ready:
            m = media_lib.store(ready[kind], kind, shop.id, current_user.id)
            db.session.flush()
            setattr(shop, attr, m.key)
    return {}
