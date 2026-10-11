"""Super admin: create and manage shops (with photos), review applications, orders and disputes."""
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from .. import services as svc
from ..catalog import product_form_data, save_product, save_shop_images
from ..data import CAT_LABELS, REGIONS, STATUS_LABELS
from ..extensions import db
from ..models import AuditLog, Order, Product, Shop, ShopApplication, User
from ..seed import unique_slug
from ..utils import clean_phone, safe_next, temp_password, valid_email, valid_ghana_card, valid_phone

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.is_admin:
            abort(404)
        return view(*args, **kwargs)
    return wrapper


@bp.context_processor
def admin_counts():
    if not (current_user.is_authenticated and current_user.is_admin):
        return {}
    return {"nav_counts": {
        "applications": ShopApplication.query.filter_by(status="new").count(),
        "disputes": Order.query.filter_by(status="disputed").count(),
    }}


# ---------- Overview ----------

@bp.get("/")
@admin_required
def index():
    svc.auto_release()
    released = db.session.query(func.coalesce(func.sum(Order.subtotal), 0)).filter(Order.status == "released").scalar()
    held = (db.session.query(func.coalesce(func.sum(Order.subtotal), 0))
            .filter(Order.status.in_(["placed", "confirmed", "shipped", "delivered", "disputed"])).scalar())
    stats = {
        "shops": Shop.query.filter_by(suspended=False).count(),
        "products": Product.query.filter_by(active=True, published=True).count(),
        "orders": Order.query.filter(Order.status != "awaiting_payment").count(),
        "released": released, "held": held,
        "commission": round(released * current_app.config["COMMISSION_RATE"]),
        "no_photos": Product.query.filter_by(active=True).filter(~Product.images.any()).count(),
    }
    disputes = Order.query.filter_by(status="disputed").order_by(Order.updated_at.desc()).all()
    recent = Order.query.filter(Order.status != "awaiting_payment").order_by(Order.created_at.desc()).limit(10).all()
    return render_template("admin/index.html", stats=stats, disputes=disputes, recent=recent)


# ---------- Shops ----------

@bp.get("/shops")
@admin_required
def shops():
    q = (request.args.get("q") or "").strip()
    query = Shop.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Shop.name.ilike(like), Shop.town.ilike(like), Shop.region.ilike(like)))
    rows = query.order_by(Shop.suspended.asc(), Shop.name.asc()).all()
    counts = dict(db.session.query(Product.shop_id, func.count(Product.id))
                  .filter(Product.active.is_(True)).group_by(Product.shop_id).all())
    return render_template("admin/shops.html", shops=rows, counts=counts, q=q)


def _shop_fields(form, creating: bool):
    f = lambda k, n=120: (form.get(k) or "").strip()[:n]  # noqa: E731
    data = {"name": f("name", 80), "town": f("town", 60), "region": f("region"), "phone": clean_phone(f("phone")),
            "momo": clean_phone(f("momo")), "ghana_card": f("ghana_card").upper(), "reg_no": f("reg_no", 40),
            "about": f("about", 600), "verified": form.get("verified") == "1"}
    errors = {}
    if len(data["name"]) < 3:
        errors["name"] = "Enter the shop name."
    if len(data["town"]) < 2:
        errors["town"] = "Enter the town or city."
    if data["region"] not in REGIONS:
        errors["region"] = "Choose a region."
    if data["phone"] and not valid_phone(data["phone"]):
        errors["phone"] = "Enter a 10-digit Ghana number."
    if data["momo"] and not valid_phone(data["momo"]):
        errors["momo"] = "Enter a 10-digit MoMo number."
    if data["ghana_card"] and not valid_ghana_card(data["ghana_card"]):
        errors["ghana_card"] = "Use the format GHA-123456789-0."
    if creating:
        data.update(owner_name=f("owner_name"), owner_email=f("owner_email", 255).lower())
        if len(data["owner_name"]) < 3:
            errors["owner_name"] = "Enter the owner's full name."
        if not valid_email(data["owner_email"]):
            errors["owner_email"] = "Enter the owner's email. It becomes their login."
        else:
            existing = User.query.filter_by(email=data["owner_email"]).first()
            if existing and (existing.shop or existing.is_admin):
                errors["owner_email"] = "This email already manages a shop or is an admin. Use another."
    return data, errors


def _apply_shop_fields(shop: Shop, data: dict) -> None:
    shop.name, shop.town, shop.region = data["name"], data["town"], data["region"]
    shop.phone = data["phone"] or None
    shop.momo_number = data["momo"] or None
    shop.ghana_card = data["ghana_card"] or None
    shop.reg_no = data["reg_no"] or None
    shop.about = data["about"]
    shop.verified = data["verified"]


@bp.route("/shops/new", methods=["GET", "POST"])
@admin_required
def shop_new():
    app_row = db.session.get(ShopApplication, request.args.get("application", type=int) or 0)
    errors = {}
    if request.method == "POST":
        data, errors = _shop_fields(request.form, creating=True)
        if not errors:
            shop = Shop(slug=unique_slug(data["name"]), awning=Shop.query.count() % 5,
                        since_year=datetime.now().year)
            _apply_shop_fields(shop, data)
            user = User.query.filter_by(email=data["owner_email"]).first()
            password = None
            if user is None:
                password = temp_password()
                user = User(email=data["owner_email"], name=data["owner_name"], phone=data["phone"] or None,
                            role="seller", must_change_password=True)
                user.set_password(password)
                db.session.add(user)
            elif user.role == "buyer":
                user.role = "seller"
            shop.owner = user
            db.session.add(shop)
            db.session.flush()
            image_errors = save_shop_images(shop)
            if image_errors:
                db.session.rollback()
                errors = image_errors
            else:
                if app_row:
                    app_row.status, app_row.shop_id = "approved", shop.id
                svc.audit("shop.create", f"{shop.name} (owner {user.email})")
                db.session.commit()
                return render_template("admin/shop_created.html", shop=shop, user=user, password=password)
    else:
        data = {"region": "Greater Accra", "verified": False}
        if app_row:
            data.update(name=app_row.business_name, town=app_row.town, region=app_row.region, phone=app_row.phone,
                        momo=app_row.phone, ghana_card=app_row.ghana_card or "", reg_no=app_row.reg_no or "",
                        about=app_row.about or "", owner_name=app_row.owner_name, owner_email=app_row.email)
    return render_template("admin/shop_form.html", data=data, errors=errors, shop=None, application=app_row)


def _shop(sid: int) -> Shop:
    return db.session.get(Shop, sid) or abort(404)


@bp.route("/shops/<int:sid>", methods=["GET", "POST"])
@admin_required
def shop_manage(sid):
    shop = _shop(sid)
    errors = {}
    if request.method == "POST":
        data, errors = _shop_fields(request.form, creating=False)
        if not errors:
            errors = save_shop_images(shop)
        if not errors:
            _apply_shop_fields(shop, data)
            svc.audit("shop.update", shop.name)
            db.session.commit()
            flash("Shop saved.", "ok")
            return redirect(url_for("admin.shop_manage", sid=shop.id))
        db.session.rollback()
    else:
        data = {"name": shop.name, "town": shop.town, "region": shop.region, "phone": shop.phone or "",
                "momo": shop.momo_number or "", "ghana_card": shop.ghana_card or "", "reg_no": shop.reg_no or "",
                "about": shop.about or "", "verified": shop.verified}
    products = (Product.query.filter_by(shop_id=shop.id, active=True)
                .order_by(Product.published.asc(), Product.created_at.desc()).all())
    return render_template("admin/shop_manage.html", shop=shop, data=data, errors=errors, products=products,
                           s=svc.seller_summary(shop))


@bp.post("/shops/<int:sid>/toggle/<what>")
@admin_required
def shop_toggle(sid, what):
    shop = _shop(sid)
    if what == "verified":
        shop.verified = not shop.verified
        msg = "verified" if shop.verified else "verification removed"
    elif what == "suspended":
        shop.suspended = not shop.suspended
        msg = "suspended (hidden from the mall)" if shop.suspended else "restored"
        if shop.owner:
            shop.owner.is_active_account = not shop.suspended
    else:
        abort(404)
    svc.audit(f"shop.{what}", f"{shop.name}: {msg}")
    db.session.commit()
    flash(f"{shop.name}: {msg}.", "ok")
    return redirect(safe_next(request.form.get("next")) or url_for("admin.shop_manage", sid=shop.id))


@bp.post("/shops/<int:sid>/reset-password")
@admin_required
def shop_reset_password(sid):
    shop = _shop(sid)
    if not shop.owner:
        flash("This shop has no owner login yet. Add one by editing the shop.", "error")
        return redirect(url_for("admin.shop_manage", sid=sid))
    password = temp_password()
    shop.owner.set_password(password)
    shop.owner.must_change_password = True
    svc.audit("shop.reset_password", f"{shop.name} ({shop.owner.email})")
    db.session.commit()
    return render_template("admin/shop_created.html", shop=shop, user=shop.owner, password=password, reset=True)


# ---------- Products (admin can manage any shop) ----------

@bp.route("/shops/<int:sid>/products/new", methods=["GET", "POST"])
@admin_required
def product_new(sid):
    shop = _shop(sid)
    data, errors, product = product_form_data(), {}, None
    if request.method == "POST":
        product, data, errors = save_product(shop)
        if not errors:
            flash(f"{'Published' if product.published else 'Saved as draft'}: {product.name}", "ok")
            return redirect(url_for("admin.shop_manage", sid=sid) + "#products")
    return render_template("shared/product_form.html", shop=shop, product=product, data=data, errors=errors,
                           back_url=url_for("admin.shop_manage", sid=sid),
                           action_url=url_for("admin.product_new", sid=sid))


@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(pid):
    product = db.session.get(Product, pid)
    if not product or not product.active:
        abort(404)
    data, errors = product_form_data(product), {}
    if request.method == "POST":
        product, data, errors = save_product(product.shop, product)
        if not errors:
            flash(f"Saved: {product.name}", "ok")
            return redirect(url_for("admin.shop_manage", sid=product.shop_id) + "#products")
    return render_template("shared/product_form.html", shop=product.shop, product=product, data=data,
                           errors=errors, back_url=url_for("admin.shop_manage", sid=product.shop_id),
                           action_url=url_for("admin.product_edit", pid=pid))


@bp.post("/products/<int:pid>/remove")
@admin_required
def product_remove(pid):
    product = db.session.get(Product, pid) or abort(404)
    product.active = False
    svc.audit("product.remove", f"{product.shop.name}: {product.name}")
    db.session.commit()
    flash(f"Removed: {product.name}", "ok")
    return redirect(url_for("admin.shop_manage", sid=product.shop_id) + "#products")


# ---------- Applications ----------

@bp.get("/applications")
@admin_required
def applications():
    status = request.args.get("status", "new")
    rows = (ShopApplication.query.filter_by(status=status).order_by(ShopApplication.created_at.desc()).limit(200).all())
    return render_template("admin/applications.html", rows=rows, status=status, cat_labels=CAT_LABELS)


@bp.post("/applications/<int:aid>/decline")
@admin_required
def application_decline(aid):
    row = db.session.get(ShopApplication, aid) or abort(404)
    row.status = "rejected"
    svc.audit("application.decline", row.business_name)
    db.session.commit()
    flash(f"Declined: {row.business_name}.", "ok")
    return redirect(url_for("admin.applications"))


# ---------- Orders ----------

@bp.get("/orders")
@admin_required
def orders():
    svc.auto_release()
    status = request.args.get("status", "")
    query = Order.query.filter(Order.status != "awaiting_payment")
    if status in STATUS_LABELS:
        query = query.filter(Order.status == status)
    page = query.order_by(Order.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, error_out=False)
    return render_template("admin/orders.html", page=page, status=status)


@bp.post("/orders/<code>/resolve")
@admin_required
def order_resolve(code):
    order = Order.query.filter_by(code=code).first_or_404()
    action = request.form.get("action")
    if order.status == "disputed" and action in {"release", "refund"}:
        if action == "release":
            order.set_status("released")
            order.note = (order.note or "") + " | Resolved: paid to shop."
        else:
            svc.restore_stock(order)
            order.set_status("cancelled")
            order.note = (order.note or "") + " | Resolved: refund to buyer."
        svc.audit(f"order.{action}", order.code)
        db.session.commit()
        flash(f"Order {order.code} resolved.", "ok")
    return redirect(safe_next(request.form.get("next")) or url_for("admin.index"))


# ---------- Activity ----------

@bp.get("/activity")
@admin_required
def activity():
    page = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=100, error_out=False)
    return render_template("admin/activity.html", page=page)
