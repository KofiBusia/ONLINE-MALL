"""Business logic: cart, delivery, checkout, payment release and search."""
from collections import OrderedDict
from datetime import datetime, timedelta

from flask import current_app, session
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from .data import CAT_LABELS, DEFAULT_REGION, HELD_STATUSES, REGIONS
from .extensions import db
from .models import AuditLog, Checkout, Order, OrderItem, Product, Shop, ShopApplication, User, utcnow
from .utils import new_code


# ---------- Region & cart (stored in the signed session cookie) ----------

def current_region() -> str:
    region = session.get("region")
    return region if region in REGIONS else DEFAULT_REGION


def cart_count() -> int:
    return sum(session.get("cart", {}).values())


def cart_lines():
    """[(product, qty)] for valid items. Drops sold-out or removed products."""
    cart = session.get("cart", {})
    if not cart:
        return []
    ids = [int(k) for k in cart if k.isdigit()]
    found = {
        p.id: p
        for p in Product.query.join(Shop)
        .options(contains_eager(Product.shop))
        .filter(Product.id.in_(ids), Product.active.is_(True), Product.published.is_(True), Shop.suspended.is_(False))
    }
    lines, changed = [], False
    for key, qty in list(cart.items()):
        product = found.get(int(key)) if key.isdigit() else None
        if not product or product.stock < 1:
            cart.pop(key, None)
            changed = True
            continue
        if qty > product.stock:
            cart[key] = qty = product.stock
            changed = True
        lines.append((product, qty))
    if changed:
        session.modified = True
    return lines


def delivery_fee(shop_region: str, buyer_region: str) -> int:
    cfg = current_app.config
    return cfg["DELIVERY_SAME_REGION"] if shop_region == buyer_region else cfg["DELIVERY_OTHER_REGION"]


def totals(lines, region: str) -> dict:
    groups = OrderedDict()
    for product, qty in lines:
        groups.setdefault(product.shop_id, []).append((product, qty))
    subtotal = sum(p.price * q for p, q in lines)
    delivery = sum(delivery_fee(items[0][0].shop.region, region) for items in groups.values())
    return {"subtotal": subtotal, "delivery": delivery, "total": subtotal + delivery,
            "groups": groups, "shops": len(groups)}


# ---------- Checkout ----------

def _unique_code(model, prefix: str) -> str:
    while True:
        code = new_code(prefix)
        if not model.query.filter_by(code=code).first():
            return code


def create_checkout(lines, data: dict, buyer=None) -> Checkout:
    region = data["region"]
    checkout = Checkout(
        code=_unique_code(Checkout, "EDW"),
        buyer_id=buyer.id if buyer else None,
        name=data["name"], phone=data["phone"], email=data.get("email") or None,
        gps=data["gps"], region=region, landmark=data.get("landmark", ""),
        pay_method=data["pay"], pay_status="cod" if data["pay"] == "cod" else "pending",
    )
    db.session.add(checkout)
    summary = totals(lines, region)
    for n, (shop_id, items) in enumerate(summary["groups"].items(), start=1):
        shop = items[0][0].shop
        order = Order(
            code=f"{checkout.code}-{n}", shop_id=shop_id,
            subtotal=sum(p.price * q for p, q in items),
            delivery=delivery_fee(shop.region, region),
            status="awaiting_payment",
        )
        for product, qty in items:
            order.items.append(OrderItem(product_id=product.id, name=product.name, icon=product.icon,
                                         image_key=product.cover_key, category=product.category,
                                         price=product.price, qty=qty))
        checkout.orders.append(order)
    checkout.total = summary["total"]
    db.session.commit()
    return checkout


def finalize_checkout(checkout: Checkout) -> None:
    """Payment received (or pay-on-delivery chosen): send orders to the shops. Safe to call twice."""
    for order in checkout.orders:
        if order.status != "awaiting_payment":
            continue
        order.set_status("placed")
        for item in order.items:
            product = db.session.get(Product, item.product_id) if item.product_id else None
            if product:
                product.stock = max(0, product.stock - item.qty)
                product.sold += item.qty
    if checkout.pay_method != "cod":
        checkout.pay_status = "paid"
    db.session.commit()


def restore_stock(order: Order) -> None:
    for item in order.items:
        product = db.session.get(Product, item.product_id) if item.product_id else None
        if product:
            product.stock += item.qty
            product.sold = max(0, product.sold - item.qty)


def auto_release() -> None:
    """Release payment for orders left in 'delivered' longer than AUTO_RELEASE_HOURS."""
    cutoff = utcnow() - timedelta(hours=current_app.config["AUTO_RELEASE_HOURS"])
    stale = Order.query.filter(Order.status == "delivered", Order.updated_at < cutoff).all()
    for order in stale:
        order.set_status("released")
    if stale:
        db.session.commit()


def remember_checkout(code: str) -> None:
    codes = session.get("my_checkouts", [])
    if code not in codes:
        session["my_checkouts"] = (codes + [code])[-20:]


def can_view_checkout(checkout: Checkout) -> bool:
    if current_user.is_authenticated and (current_user.is_admin or checkout.buyer_id == current_user.id):
        return True
    return checkout.code in session.get("my_checkouts", [])


# ---------- Browse & search ----------

def shop_directory(q: str = "", cat: str = "all"):
    shops = Shop.query.filter_by(suspended=False).options(selectinload(Shop.products)).all()
    needle = q.lower()
    directory = []
    for shop in shops:
        items = [p for p in shop.products if p.active and p.published]
        if not items:
            continue
        if cat != "all" and not any(p.category == cat for p in items):
            continue
        cats = list(dict.fromkeys(CAT_LABELS.get(p.category, p.category) for p in items))
        if needle and needle not in " ".join([shop.name, shop.town, shop.region, *cats]).lower():
            continue
        preview = sorted(items, key=lambda p: (cat != "all" and p.category != cat, -p.sold))[:3]
        directory.append({"shop": shop, "count": len(items), "cats": cats, "preview": preview,
                          "sales": sum(p.sold for p in items)})
    directory.sort(key=lambda d: (not d["shop"].verified, -d["sales"]))
    return directory


def product_search(q: str = "", cat: str = "all", sort: str = "popular", shop_id=None):
    query = (Product.query.join(Shop).options(contains_eager(Product.shop))
             .filter(Product.active.is_(True), Product.published.is_(True), Shop.suspended.is_(False)))
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)
    if cat != "all":
        query = query.filter(Product.category == cat)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.name.ilike(like), Shop.name.ilike(like),
                                 Shop.town.ilike(like), Shop.region.ilike(like)))
    order = {
        "popular": Product.sold.desc(), "rating": Product.rating.desc(),
        "low": Product.price.asc(), "high": Product.price.desc(), "new": Product.created_at.desc(),
    }.get(sort, Product.sold.desc())
    return query.order_by(order, Product.id.desc())


# ---------- Seller money ----------

def seller_summary(shop: Shop) -> dict:
    orders = (Order.query.filter(Order.shop_id == shop.id, Order.status != "awaiting_payment")
              .options(selectinload(Order.items), joinedload(Order.checkout))
              .order_by(Order.created_at.desc()).all())
    held = sum(o.subtotal for o in orders if o.status in HELD_STATUSES)
    released = sum(o.subtotal for o in orders if o.status == "released")
    commission = round(released * current_app.config["COMMISSION_RATE"])
    return {
        "orders": orders,
        "open": sum(1 for o in orders if o.status in {"placed", "confirmed", "shipped"}),
        "held": held, "released": released, "commission": commission, "payout": released - commission,
    }


# ---------- Audit trail ----------

def audit(action: str, detail: str = "") -> None:
    """Record an admin or seller action. Committed with the caller's transaction."""
    uid = current_user.id if current_user.is_authenticated else None
    db.session.add(AuditLog(user_id=uid, action=action, detail=(detail or "")[:300]))


# ---------- Paid shop applications ----------

def open_shop_from_application(app_row: ShopApplication) -> Shop:
    """The listing fee cleared: create the shop and promote the applicant to seller.

    Idempotent -- the Paystack callback and webhook can both land for the same
    payment, so a second call just returns the shop already created by the first.
    """
    if app_row.shop_id:
        return db.session.get(Shop, app_row.shop_id)
    from .seed import unique_slug  # imported lazily: seed.py doesn't need to load at app start just for this
    shop = Shop(name=app_row.business_name, slug=unique_slug(app_row.business_name), town=app_row.town,
                region=app_row.region, about=app_row.about or "", verified=False,
                since_year=datetime.now().year, awning=Shop.query.count() % 5,
                phone=app_row.phone or None, ghana_card=app_row.ghana_card or None, reg_no=app_row.reg_no or None)
    user = User.query.filter_by(email=app_row.email).first()
    if user is None:
        user = User(email=app_row.email, name=app_row.owner_name, phone=app_row.phone or None, role="seller")
    else:
        user.role = "seller"
    shop.owner = user
    db.session.add(shop)
    db.session.flush()  # assigns shop.id
    app_row.status, app_row.shop_id, app_row.fee_paid_at = "approved", shop.id, utcnow()
    audit("shop.create_paid", f"{shop.name} (owner {user.email})")
    return shop
