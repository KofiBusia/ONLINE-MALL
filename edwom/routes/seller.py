"""Shop owners: apply to sell, manage products and photos, fulfil orders, see earnings.

Shops are created by the super admin. Owners receive a login and manage their own shop here.
"""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import services as svc
from ..catalog import product_form_data, save_product, save_shop_images
from ..data import CAT_LABELS, REGIONS, SELLER_ACTION_LABELS, SELLER_NEXT
from ..extensions import db, limiter
from ..models import Order, Product, ShopApplication
from ..utils import clean_phone, valid_email, valid_ghana_card, valid_phone

bp = Blueprint("seller", __name__, url_prefix="/sell")


def seller_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.shop:
            flash("Your account isn't linked to a shop yet. Apply below and the Edwom team will set it up.", "error")
            return redirect(url_for("seller.apply"))
        return view(*args, **kwargs)
    return wrapper


@bp.route("/", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def apply():
    if current_user.is_authenticated and current_user.shop:
        return redirect(url_for("seller.dashboard"))
    errors, done = {}, False
    data = {"region": "Greater Accra", "category": "fashion"}
    if current_user.is_authenticated:
        data.update(owner_name=current_user.name, email=current_user.email, phone=current_user.phone or "")
    if request.method == "POST":
        f = lambda k, n=120: (request.form.get(k) or "").strip()[:n]  # noqa: E731
        data = {"business_name": f("business_name", 80), "owner_name": f("owner_name"), "email": f("email").lower(),
                "phone": clean_phone(f("phone")), "town": f("town", 60), "region": f("region"),
                "category": f("category"), "ghana_card": f("ghana_card").upper(), "reg_no": f("reg_no", 40),
                "about": f("about", 600)}
        if len(data["business_name"]) < 3:
            errors["business_name"] = "Enter your business name."
        if len(data["owner_name"]) < 3:
            errors["owner_name"] = "Enter the owner's full name."
        if not valid_email(data["email"]):
            errors["email"] = "Enter a valid email address."
        if not valid_phone(data["phone"]):
            errors["phone"] = "Enter a 10-digit Ghana number."
        if len(data["town"]) < 2:
            errors["town"] = "Enter your town or city."
        if data["region"] not in REGIONS:
            errors["region"] = "Choose a region."
        if data["category"] not in CAT_LABELS:
            errors["category"] = "Choose what you mainly sell."
        if not valid_ghana_card(data["ghana_card"]):
            errors["ghana_card"] = "Use the format GHA-123456789-0."
        if not request.form.get("agree"):
            errors["agree"] = "Accept the seller terms to continue."
        if not errors:
            db.session.add(ShopApplication(**{k: v or None if k == "reg_no" else v for k, v in data.items()}))
            db.session.commit()
            done = True
    return render_template("seller/apply.html", errors=errors, data=data, done=done)


@bp.get("/dashboard")
@seller_required
def dashboard():
    svc.auto_release()
    shop = current_user.shop
    products = (Product.query.filter_by(shop_id=shop.id, active=True)
                .order_by(Product.published.asc(), Product.created_at.desc()).all())
    return render_template("seller/dashboard.html", shop=shop, products=products, s=svc.seller_summary(shop),
                           next_status=SELLER_NEXT, action_labels=SELLER_ACTION_LABELS)


@bp.route("/products/new", methods=["GET", "POST"])
@seller_required
def product_new():
    shop = current_user.shop
    data, errors, product = product_form_data(), {}, None
    if request.method == "POST":
        product, data, errors = save_product(shop)
        if not errors:
            flash(f"{'Published' if product.published else 'Saved as draft'}: {product.name}", "ok")
            return redirect(url_for("seller.dashboard") + "#products")
    return render_template("shared/product_form.html", shop=shop, product=product, data=data, errors=errors,
                           back_url=url_for("seller.dashboard"), action_url=url_for("seller.product_new"))


def _own_product(pid: int) -> Product:
    product = db.session.get(Product, pid)
    if not product or product.shop_id != current_user.shop.id or not product.active:
        abort(404)
    return product


@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@seller_required
def product_edit(pid):
    product = _own_product(pid)
    data, errors = product_form_data(product), {}
    if request.method == "POST":
        product, data, errors = save_product(current_user.shop, product)
        if not errors:
            flash(f"Saved: {product.name}", "ok")
            return redirect(url_for("seller.dashboard") + "#products")
    return render_template("shared/product_form.html", shop=current_user.shop, product=product, data=data,
                           errors=errors, back_url=url_for("seller.dashboard"),
                           action_url=url_for("seller.product_edit", pid=pid))


@bp.post("/products/<int:pid>/remove")
@seller_required
def product_remove(pid):
    product = _own_product(pid)
    product.active = False
    svc.audit("product.remove", f"{product.shop.name}: {product.name}")
    db.session.commit()
    flash(f"Removed from the mall: {product.name}", "ok")
    return redirect(url_for("seller.dashboard") + "#products")


def _shop_order(code: str) -> Order:
    order = Order.query.filter_by(code=code).first_or_404()
    if order.shop_id != current_user.shop.id:
        abort(404)
    return order


@bp.post("/orders/<code>/advance")
@seller_required
def order_advance(code):
    order = _shop_order(code)
    nxt = SELLER_NEXT.get(order.status)
    if nxt:
        order.set_status(nxt)
        db.session.commit()
        flash(f"Order {order.code} updated.", "ok")
    return redirect(url_for("seller.dashboard") + "#orders")


@bp.post("/orders/<code>/cancel")
@seller_required
def order_cancel(code):
    order = _shop_order(code)
    if order.status == "placed":
        svc.restore_stock(order)
        order.set_status("cancelled")
        order.note = "Cancelled by the shop."
        svc.audit("order.cancel", order.code)
        db.session.commit()
        flash("Order cancelled." + (" Edwom will refund the buyer." if order.checkout.pay_status == "paid" else ""), "ok")
    return redirect(url_for("seller.dashboard") + "#orders")


@bp.route("/settings", methods=["GET", "POST"])
@seller_required
def settings():
    shop = current_user.shop
    errors = {}
    if request.method == "POST":
        about = (request.form.get("about") or "").strip()[:600]
        phone = clean_phone(request.form.get("phone"))
        momo = clean_phone(request.form.get("momo"))
        if phone and not valid_phone(phone):
            errors["phone"] = "Enter a 10-digit Ghana number."
        if not valid_phone(momo):
            errors["momo"] = "Enter the 10-digit MoMo number for payouts."
        if not errors:
            errors = save_shop_images(shop)
        if not errors:
            shop.about, shop.phone, shop.momo_number = about, phone or None, momo
            svc.audit("shop.update", shop.name)
            db.session.commit()
            flash("Shop details saved.", "ok")
            return redirect(url_for("seller.dashboard"))
        db.session.rollback()
    return render_template("seller/settings.html", shop=shop, errors=errors)
