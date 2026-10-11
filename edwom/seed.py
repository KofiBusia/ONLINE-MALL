"""Super admin bootstrap and the optional demo catalogue."""
from flask import current_app

from .data import DEMO_SHOPS
from .extensions import db
from .models import Product, Shop, User
from .utils import slugify


def unique_slug(name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while Shop.query.filter_by(slug=slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def ensure_admin() -> str:
    email = current_app.config["ADMIN_EMAIL"]
    password = current_app.config["ADMIN_PASSWORD"]
    if not email or not password:
        return "ADMIN_EMAIL / ADMIN_PASSWORD not set; no super admin created."
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email, name="Edwom Super Admin", role="admin")
        user.set_password(password)
        db.session.add(user)
        msg = f"Super admin created: {email}"
    else:
        user.role = "admin"
        user.is_active_account = True
        msg = f"Super admin ready: {email}"
    db.session.commit()
    return msg


def seed_demo() -> bool:
    if Shop.query.first():
        return False
    for i, s in enumerate(DEMO_SHOPS):
        shop = Shop(name=s["name"], slug=unique_slug(s["name"]), about=s["about"], town=s["town"],
                    region=s["region"], verified=s["verified"], since_year=s["since"], awning=i % 5)
        db.session.add(shop)
        for name, price, cat, icon, sold, rating, stock, desc in s["products"]:
            db.session.add(Product(shop=shop, name=name, price=int(round(price * 100)), category=cat, icon=icon,
                                   sold=sold, rating=rating, stock=stock, description=desc))
    db.session.commit()
    return True
