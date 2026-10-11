"""Buyer-facing pages: mall, shops, products, cart, checkout, payment and orders."""
import secrets

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from .. import payments
from .. import services as svc
from ..data import CAT_LABELS, PAY_METHODS, REGIONS, SORTS
from ..extensions import csrf, db, limiter
from ..models import Checkout, Media, Order, Product, Shop
from ..utils import clean_phone, momo_network, redirect_back, to_int, valid_email, valid_gps, valid_phone

bp = Blueprint("main", __name__)


def _filters():
    q = (request.args.get("q") or "").strip()[:80]
    cat = request.args.get("cat", "all")
    sort = request.args.get("sort", "popular")
    return q, (cat if cat in CAT_LABELS else "all"), (sort if sort in SORTS else "popular")


def _checkout_or_404(code: str) -> Checkout:
    checkout = Checkout.query.filter_by(code=code.upper()).first_or_404()
    if not svc.can_view_checkout(checkout):
        abort(404)
    return checkout


@bp.get("/healthz")
def healthz():
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return {"status": "database unavailable"}, 503
    return {"status": "ok"}


@bp.get("/robots.txt")
def robots():
    body = "User-agent: *\nDisallow: /admin\nDisallow: /sell/dashboard\nDisallow: /checkout\nDisallow: /orders\n"
    return Response(body, mimetype="text/plain")


@bp.get("/media/<key>/<size>.webp")
def media(key, size):
    if size not in ("full", "thumb") or len(key) != 32:
        abort(404)
    if request.headers.get("If-None-Match") == f'"{key}-{size}"':
        return Response(status=304)
    column = Media.full if size == "full" else Media.thumb
    row = db.session.query(column).filter(Media.key == key).first()
    if not row:
        abort(404)
    resp = Response(row[0], mimetype="image/webp")
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["ETag"] = f'"{key}-{size}"'
    return resp


@bp.get("/")
def index():
    q, cat, sort = _filters()
    page = svc.product_search(q, cat, sort).paginate(
        page=request.args.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("index.html", q=q, cat=cat, sort=sort, shops=svc.shop_directory(q, cat), page=page)


@bp.get("/shops/<slug>")
def shop(slug):
    shop = Shop.query.filter_by(slug=slug, suspended=False).first_or_404()
    _, cat, sort = _filters()
    page = svc.product_search("", cat, sort, shop_id=shop.id).paginate(
        page=request.args.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    count = Product.query.filter_by(shop_id=shop.id, active=True, published=True).count()
    return render_template("shop.html", shop=shop, page=page, cat=cat, sort=sort, count=count)


@bp.get("/p/<int:pid>")
def product(pid):
    item = db.session.get(Product, pid)
    if not item or not item.active or item.shop.suspended:
        abort(404)
    if not item.published and not _can_preview(item):
        abort(404)
    more = (Product.query.filter(Product.shop_id == item.shop_id, Product.id != item.id,
                                 Product.active.is_(True), Product.published.is_(True))
            .order_by(Product.sold.desc()).limit(4).all())
    fee = svc.delivery_fee(item.shop.region, svc.current_region())
    return render_template("product.html", p=item, more=more, fee=fee)


def _can_preview(item: Product) -> bool:
    return current_user.is_authenticated and (current_user.is_admin or (
        current_user.shop is not None and current_user.shop.id == item.shop_id))


@bp.post("/region")
def set_region():
    region = request.form.get("region")
    if region in REGIONS:
        session["region"] = region
    return redirect_back()


# ---------- Cart ----------

@bp.post("/cart/add/<int:pid>")
def cart_add(pid):
    item = db.session.get(Product, pid)
    if not item or not item.active or not item.published or item.shop.suspended:
        abort(404)
    qty = max(1, min(99, to_int(request.form.get("qty"), 1)))
    cart = session.setdefault("cart", {})
    new_qty = min(cart.get(str(pid), 0) + qty, item.stock, 99)
    if new_qty <= 0:
        flash("Sorry, that product is sold out.", "error")
    else:
        cart[str(pid)] = new_qty
        session.modified = True
        flash(f"Added to cart: {item.name}", "ok")
    if request.form.get("go") == "cart":
        return redirect(url_for("main.cart"))
    return redirect_back()


@bp.get("/cart")
def cart():
    lines = svc.cart_lines()
    return render_template("cart.html", lines=lines, t=svc.totals(lines, svc.current_region()))


@bp.post("/cart/update")
def cart_update():
    cart = session.get("cart", {})
    remove = request.form.get("remove")
    if remove:
        cart.pop(remove, None)
    for key in list(cart):
        value = request.form.get(f"qty_{key}")
        if value is not None:
            qty = to_int(value, cart[key])
            if qty <= 0:
                cart.pop(key)
            else:
                cart[key] = min(qty, 99)
    session["cart"] = cart
    flash("Cart updated.", "ok")
    return redirect(url_for("main.cart"))


# ---------- Checkout & payment ----------

@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines = svc.cart_lines()
    if not lines:
        flash("Your cart is empty.", "error")
        return redirect(url_for("main.cart"))

    errors = {}
    if request.method == "POST":
        data = {k: (request.form.get(k) or "").strip() for k in ("name", "phone", "email", "gps", "region", "landmark", "pay")}
        data["phone"] = clean_phone(data["phone"])
        data["gps"] = data["gps"].upper()
        data["email"] = data["email"].lower()
        data["landmark"] = data["landmark"][:200]
        if len(data["name"]) < 3:
            errors["name"] = "Enter the name the rider should ask for."
        if not valid_phone(data["phone"]):
            errors["phone"] = "Enter a 10-digit Ghana number, e.g. 024 123 4567."
        if not valid_gps(data["gps"]):
            errors["gps"] = "Use the GhanaPostGPS format, e.g. GA-183-8164."
        if data["region"] not in REGIONS:
            errors["region"] = "Choose a region."
        if data["pay"] not in PAY_METHODS:
            errors["pay"] = "Choose how you'll pay."
        if data["email"] and not valid_email(data["email"]):
            errors["email"] = "Check the email address."
        elif not data["email"] and data["pay"] != "cod" and payments.enabled():
            errors["email"] = "Enter an email for your payment receipt."
        for p, q in lines:
            if q > p.stock:
                errors["cart"] = f"Only {p.stock} of {p.name} left. Update your cart."

        if not errors:
            buyer = current_user if current_user.is_authenticated else None
            co = svc.create_checkout(lines, data, buyer)
            session["cart"] = {}
            session["region"] = data["region"]
            svc.remember_checkout(co.code)
            if co.pay_method == "cod":
                svc.finalize_checkout(co)
                return redirect(url_for("main.checkout_done", code=co.code))
            return redirect(url_for("main.pay", code=co.code))
    else:
        user = current_user if current_user.is_authenticated else None
        data = {"name": user.name if user else "", "phone": (user.phone or "") if user else "",
                "email": user.email if user else "", "gps": "", "region": svc.current_region(),
                "landmark": "", "pay": "momo"}

    region = data.get("region") if data.get("region") in REGIONS else svc.current_region()
    return render_template("checkout.html", lines=lines, t=svc.totals(lines, region), data=data, errors=errors)


@bp.route("/pay/<code>", methods=["GET", "POST"])
def pay(code):
    co = _checkout_or_404(code)
    if co.pay_method == "cod" or co.pay_status == "paid":
        return redirect(url_for("main.checkout_done", code=co.code))

    if payments.enabled():
        co.reference = f"{co.code}-{secrets.token_hex(3).upper()}"
        db.session.commit()
        try:
            url = payments.initialize(
                email=co.email or f"{co.phone}@buyers.edwom.app", amount=co.total, reference=co.reference,
                callback_url=url_for("main.payment_callback", _external=True),
                metadata={"checkout": co.code, "phone": co.phone},
            )
            return redirect(url)
        except payments.PaymentError as exc:
            current_app.logger.warning("Paystack initialize failed: %s", exc)
            flash("We couldn't reach the payment provider. Your order is saved; try again shortly.", "error")
            return redirect(url_for("main.checkout_detail", code=co.code))

    # Demo mode: no payment provider configured.
    if request.method == "POST":
        svc.finalize_checkout(co)
        return redirect(url_for("main.checkout_done", code=co.code))
    return render_template("pay_demo.html", co=co, network=momo_network(co.phone))


@bp.get("/payment/callback")
def payment_callback():
    reference = request.args.get("reference") or request.args.get("trxref") or ""
    co = Checkout.query.filter_by(reference=reference).first_or_404()
    try:
        ok = payments.verify(reference, co.total)
    except payments.PaymentError:
        ok = False
    svc.remember_checkout(co.code)
    if ok:
        svc.finalize_checkout(co)
        return redirect(url_for("main.checkout_done", code=co.code))
    flash("The payment wasn't completed. Your order is saved, so you can try again.", "error")
    return redirect(url_for("main.checkout_detail", code=co.code))


@bp.post("/payment/webhook")
@csrf.exempt
def payment_webhook():
    if not payments.enabled():
        abort(404)
    if not payments.valid_signature(request.get_data(), request.headers.get("x-paystack-signature", "")):
        abort(401)
    event = request.get_json(silent=True) or {}
    if event.get("event") == "charge.success":
        reference = (event.get("data") or {}).get("reference", "")
        co = Checkout.query.filter_by(reference=reference).first()
        try:
            if co and payments.verify(reference, co.total):
                svc.finalize_checkout(co)
        except payments.PaymentError:
            return "", 503  # Paystack retries
    return "", 200


@bp.get("/checkout/<code>/done")
def checkout_done(code):
    return render_template("checkout_done.html", co=_checkout_or_404(code))


# ---------- Orders ----------

@bp.get("/orders")
def orders():
    codes = session.get("my_checkouts", [])
    query = Checkout.query
    if current_user.is_authenticated:
        query = query.filter((Checkout.buyer_id == current_user.id) | (Checkout.code.in_(codes)))
    else:
        query = query.filter(Checkout.code.in_(codes or ["-"]))
    return render_template("orders.html", checkouts=query.order_by(Checkout.created_at.desc()).limit(50).all())


@bp.post("/track")
@limiter.limit("20 per hour")
def track():
    code = (request.form.get("code") or "").strip().upper()
    phone = clean_phone(request.form.get("phone"))
    co = Checkout.query.filter_by(code=code).first()
    if not co or co.phone != phone:
        flash("No order matches that number and phone. Check both and try again.", "error")
        return redirect(url_for("main.orders"))
    svc.remember_checkout(co.code)
    return redirect(url_for("main.checkout_detail", code=co.code))


@bp.get("/orders/<code>")
def checkout_detail(code):
    svc.auto_release()
    return render_template("checkout_detail.html", co=_checkout_or_404(code))


def _buyer_order(code: str) -> Order:
    order = Order.query.filter_by(code=code).first_or_404()
    if not svc.can_view_checkout(order.checkout):
        abort(404)
    return order


@bp.post("/orders/item/<code>/received")
def order_received(code):
    order = _buyer_order(code)
    if order.status in {"shipped", "delivered"}:
        order.set_status("released")
        db.session.commit()
        flash(f"Thanks for confirming. {order.shop.name} has been paid.", "ok")
    return redirect(url_for("main.checkout_detail", code=order.checkout.code))


@bp.post("/orders/item/<code>/problem")
def order_problem(code):
    order = _buyer_order(code)
    note = (request.form.get("note") or "").strip()[:500]
    if order.status in {"placed", "confirmed", "shipped", "delivered"}:
        order.set_status("disputed")
        order.note = note or "Buyer reported a problem."
        db.session.commit()
        flash("Thanks. An Edwom agent will contact you within 24 hours. Payment stays on hold.", "ok")
    return redirect(url_for("main.checkout_detail", code=order.checkout.code))
