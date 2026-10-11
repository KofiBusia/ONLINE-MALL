"""Database models. Money is stored in whole pesewas (GH₵1.00 = 100)."""
import secrets
from datetime import datetime, timezone

from flask import url_for
from flask_login import UserMixin
from sqlalchemy.orm import deferred
from werkzeug.security import check_password_hash, generate_password_hash

from .data import STATUS_FLOW
from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), nullable=False, default="buyer")  # buyer | seller | admin
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    shop = db.relationship("Shop", back_populates="owner", uselist=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:  # Flask-Login refuses inactive accounts
        return self.is_active_account

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def first_name(self) -> str:
        return (self.name or "").split(" ")[0]


class Shop(db.Model):
    __tablename__ = "shops"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False, index=True)
    about = db.Column(db.String(600), default="")
    town = db.Column(db.String(60), nullable=False)
    region = db.Column(db.String(40), nullable=False)
    phone = db.Column(db.String(15))
    ghana_card = db.Column(db.String(20))
    reg_no = db.Column(db.String(40))
    momo_number = db.Column(db.String(15))
    logo_key = db.Column(db.String(32))
    banner_key = db.Column(db.String(32))
    verified = db.Column(db.Boolean, nullable=False, default=False)
    suspended = db.Column(db.Boolean, nullable=False, default=False)
    awning = db.Column(db.Integer, nullable=False, default=0)
    since_year = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User", back_populates="shop")
    products = db.relationship("Product", back_populates="shop", order_by="Product.id")

    @property
    def since(self) -> int:
        return self.since_year or self.created_at.year


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False, index=True)
    name = db.Column(db.String(90), nullable=False)
    description = db.Column(db.Text, default="")
    specs = db.Column(db.Text, default="")       # "Material: Cotton" one per line
    sku = db.Column(db.String(40))
    price = db.Column(db.Integer, nullable=False)  # pesewas
    compare_at = db.Column(db.Integer)             # old price, shows a discount
    category = db.Column(db.String(20), nullable=False, index=True)
    icon = db.Column(db.String(16), nullable=False, default="🛍️")
    stock = db.Column(db.Integer, nullable=False, default=0)
    sold = db.Column(db.Integer, nullable=False, default=0)
    rating = db.Column(db.Float, nullable=False, default=0.0)
    active = db.Column(db.Boolean, nullable=False, default=True)   # False = removed
    published = db.Column(db.Boolean, nullable=False, default=True)  # False = draft
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    shop = db.relationship("Shop", back_populates="products")
    images = db.relationship("Media", order_by="Media.position", lazy="selectin",
                             primaryjoin="and_(Media.product_id == Product.id, Media.kind == 'product')",
                             viewonly=True)

    @property
    def cover_key(self):
        return self.images[0].key if self.images else None

    @property
    def discount_pct(self) -> int:
        if self.compare_at and self.compare_at > self.price:
            return round((self.compare_at - self.price) * 100 / self.compare_at)
        return 0

    @property
    def spec_rows(self):
        rows = []
        for line in (self.specs or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip() and v.strip():
                    rows.append((k.strip(), v.strip()))
        return rows


class Media(db.Model):
    """Uploaded image, stored in the database so it survives restarts on Render."""
    __tablename__ = "media"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: secrets.token_hex(16))
    kind = db.Column(db.String(10), nullable=False)  # product | logo | banner
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    size_bytes = db.Column(db.Integer)
    full = deferred(db.Column(db.LargeBinary, nullable=False))
    thumb = deferred(db.Column(db.LargeBinary, nullable=False))
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def url(self) -> str:
        return url_for("main.media", key=self.key, size="full")

    @property
    def thumb_url(self) -> str:
        return url_for("main.media", key=self.key, size="thumb")


class ShopApplication(db.Model):
    __tablename__ = "shop_applications"

    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(80), nullable=False)
    owner_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    town = db.Column(db.String(60), nullable=False)
    region = db.Column(db.String(40), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    ghana_card = db.Column(db.String(20))
    reg_no = db.Column(db.String(40))
    about = db.Column(db.String(600), default="")
    status = db.Column(db.String(10), nullable=False, default="new", index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User")


class Checkout(db.Model):
    """One buyer payment, split into one Order per shop."""
    __tablename__ = "checkouts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(255))
    gps = db.Column(db.String(20), nullable=False)
    region = db.Column(db.String(40), nullable=False)
    landmark = db.Column(db.String(200), default="")
    pay_method = db.Column(db.String(10), nullable=False)    # momo | card | cod
    pay_status = db.Column(db.String(12), nullable=False)    # pending | paid | cod
    reference = db.Column(db.String(40), unique=True)
    total = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    orders = db.relationship("Order", back_populates="checkout", order_by="Order.id")


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(24), unique=True, nullable=False, index=True)
    checkout_id = db.Column(db.Integer, db.ForeignKey("checkouts.id"), nullable=False, index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False, index=True)
    subtotal = db.Column(db.Integer, nullable=False)
    delivery = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="awaiting_payment", index=True)
    note = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    checkout = db.relationship("Checkout", back_populates="orders")
    shop = db.relationship("Shop")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def total(self) -> int:
        return self.subtotal + self.delivery

    @property
    def step(self) -> int:
        return STATUS_FLOW.index(self.status) if self.status in STATUS_FLOW else -1

    def set_status(self, status: str) -> None:
        self.status = status
        self.updated_at = utcnow()


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    name = db.Column(db.String(90), nullable=False)
    icon = db.Column(db.String(16), nullable=False)
    image_key = db.Column(db.String(32))
    category = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)

    order = db.relationship("Order", back_populates="items")

    @property
    def line_total(self) -> int:
        return self.price * self.qty
