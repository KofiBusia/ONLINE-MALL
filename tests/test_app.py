"""End-to-end tests for buyers, shop owners and the super admin."""
import re

from conftest import ADMIN_EMAIL, login, make_image, temp_password_from

from edwom.extensions import db
from edwom.models import AuditLog, Checkout, Media, Order, Product, Shop, ShopApplication, User


def new_shop(admin, email="owner@shop.gh", name="Ama's Beads", **extra):
    data = {"name": name, "town": "Accra", "region": "Greater Accra", "phone": "0241112222",
            "momo": "0241112222", "ghana_card": "GHA-123456789-0", "owner_name": "Ama Owusu",
            "owner_email": email, "verified": "1"}
    data.update(extra)
    resp = admin.post("/admin/shops/new", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.data[:400]
    html = resp.data.decode()
    assert "Temporary password" in html
    return Shop.query.filter_by(name=name).one(), temp_password_from(html)


def owner_client(app, email, temp):
    c = app.test_client()
    assert login(c, email, temp).headers["Location"].endswith("/account/password")
    # blocked everywhere until the password is changed
    assert c.get("/sell/dashboard").headers["Location"].endswith("/account/password")
    r = c.post("/account/password", data={"current": temp, "new": "MyOwnPass2026", "confirm": "MyOwnPass2026"})
    assert r.status_code == 302
    return c


# ---------- Public mall ----------

def test_mall_pages(client):
    html = client.get("/").data.decode()
    assert "Shops in the mall" in html and "edwom<small>online mall</small>" in html
    assert "Northern Gold" in client.get("/?q=Tamale").data.decode()
    assert client.get("/?cat=beauty&sort=low").status_code == 200
    assert client.get("/shops/adwoa-s-kente-house").status_code == 200
    assert client.get("/p/1").status_code == 200
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/healthz").json == {"status": "ok"}
    assert client.get("/missing").status_code == 404


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# ---------- Super admin sets up a shop, owner uploads photos ----------

def test_admin_creates_shop_and_owner_uploads_photos(app, admin):
    shop, temp = new_shop(admin, logo=make_image(400, 400, name="logo.png", fmt="PNG"))
    assert shop.logo_key and shop.owner.must_change_password
    assert admin.get(f"/media/{shop.logo_key}/thumb.webp").headers["Content-Type"] == "image/webp"

    owner = owner_client(app, "owner@shop.gh", temp)
    assert owner.get("/sell/dashboard").status_code == 200
    assert owner.get("/admin/").status_code == 404  # owners are not admins

    # Publishing without photos is refused
    r = owner.post("/sell/products/new", data={"name": "Waist beads", "price": "85.50", "stock": "5",
                                                "category": "fashion", "published": "1"})
    assert "Add at least one photo" in r.data.decode()

    # Upload three photos, choose the second new one as the cover
    r = owner.post("/sell/products/new", content_type="multipart/form-data", data={
        "name": "Waist beads", "price": "85.50", "compare_at": "100", "stock": "5", "category": "fashion",
        "description": "Hand strung in Accra.", "specs": "Material: Glass\nLength: 90 cm", "published": "1",
        "cover": "new-1",
        "photos": [make_image(color=(255, 0, 0)), make_image(color=(0, 255, 0), name="b.png", fmt="PNG"),
                   make_image(color=(0, 0, 255), name="c.webp", fmt="WEBP")]})
    assert r.status_code == 302, r.data[:500]
    p = Product.query.filter_by(name="Waist beads").one()
    assert p.price == 8550 and p.discount_pct == 14 and len(p.images) == 3
    green = p.images[0]
    assert db.session.get(Media, green.id).position == 0
    page = owner.get(f"/p/{p.id}").data.decode()
    assert "Material" in page and "−14%" in page and "thumbs" in page

    # Edit: remove one photo, keep two
    r = owner.post(f"/sell/products/{p.id}/edit", content_type="multipart/form-data", data={
        "name": "Waist beads", "price": "85.50", "stock": "4", "category": "fashion", "published": "1",
        "remove_photo": [p.images[2].key], "cover": p.images[1].key})
    assert r.status_code == 302
    db.session.refresh(p)
    assert len(p.images) == 2 and p.stock == 4

    # The shop and photo show in the mall
    home = app.test_client().get("/").data.decode()
    assert "Ama&#39;s Beads" in home and f"/media/{p.cover_key}/thumb.webp" in home

    # Logo and banner from shop settings
    r = owner.post("/sell/settings", content_type="multipart/form-data", data={
        "about": "Beads", "momo": "0201234567", "banner": make_image(1800, 600, name="banner.jpg")})
    assert r.status_code == 302
    db.session.refresh(shop)
    assert shop.banner_key and shop.momo_number == "0201234567"
    assert AuditLog.query.filter(AuditLog.action == "product.create").count() == 1


def test_bad_uploads_are_rejected(app, admin):
    shop, _ = new_shop(admin)
    base = {"name": "Thing", "price": "10", "stock": "1", "category": "home", "published": "1"}
    r = admin.post(f"/admin/shops/{shop.id}/products/new", content_type="multipart/form-data",
                   data={**base, "photos": [(__import__("io").BytesIO(b"not an image"), "x.jpg")]})
    assert "isn&#39;t a photo we can read" in r.data.decode()
    r = admin.post(f"/admin/shops/{shop.id}/products/new", content_type="multipart/form-data",
                   data={**base, "photos": [make_image(100, 100)]})
    assert "too small" in r.data.decode()
    r = admin.post(f"/admin/shops/{shop.id}/products/new", content_type="multipart/form-data",
                   data={**base, "photos": [make_image() for _ in range(9)]})
    assert "up to 8 photos" in r.data.decode()
    assert Product.query.filter_by(name="Thing").count() == 0


def test_admin_manages_any_shop(app, admin):
    demo = Shop.query.filter_by(name="Circle Gadgets").one()
    p = demo.products[0]
    r = admin.post(f"/admin/products/{p.id}/edit", content_type="multipart/form-data", data={
        "name": p.name, "price": "199.99", "stock": "50", "category": "elec", "published": "1",
        "photos": [make_image()]})
    assert r.status_code == 302
    db.session.refresh(p)
    assert p.price == 19999 and p.cover_key
    assert admin.post(f"/admin/shops/{demo.id}/toggle/suspended").status_code == 302
    assert "Circle Gadgets" not in app.test_client().get("/").data.decode()
    assert app.test_client().get(f"/shops/{demo.slug}").status_code == 404


def test_application_to_shop(app, admin, client):
    r = client.post("/sell/", data={"business_name": "Kofi Crafts", "owner_name": "Kofi Mensah",
                                    "email": "kofi@crafts.gh", "phone": "0551234567", "town": "Ho", "region": "Volta",
                                    "category": "home", "ghana_card": "GHA-987654321-1", "agree": "1"})
    assert "Application received" in r.data.decode()
    a = ShopApplication.query.one()
    form = admin.get(f"/admin/shops/new?application={a.id}").data.decode()
    assert "Kofi Crafts" in form and "kofi@crafts.gh" in form
    resp = admin.post(f"/admin/shops/new?application={a.id}", data={
        "name": "Kofi Crafts", "town": "Ho", "region": "Volta", "momo": "0551234567",
        "owner_name": "Kofi Mensah", "owner_email": "kofi@crafts.gh"})
    assert resp.status_code == 200
    db.session.refresh(a)
    assert a.status == "approved" and a.shop_id


def test_password_reset_and_suspension_blocks_login(app, admin):
    shop, temp = new_shop(admin, email="esi@shop.gh", name="Esi Shop")
    html = admin.post(f"/admin/shops/{shop.id}/reset-password").data.decode()
    new_temp = temp_password_from(html)
    assert new_temp != temp
    assert login(app.test_client(), "esi@shop.gh", temp).status_code == 200  # old one fails
    admin.post(f"/admin/shops/{shop.id}/toggle/suspended")
    r = login(app.test_client(), "esi@shop.gh", new_temp)
    assert "disabled" in r.data.decode()


def test_owners_cannot_touch_other_shops(app, admin):
    _, t1 = new_shop(admin, email="a@shop.gh", name="Shop A")
    shop_b, _ = new_shop(admin, email="b@shop.gh", name="Shop B")
    owner_a = owner_client(app, "a@shop.gh", t1)
    other = Product(shop_id=shop_b.id, name="B item", price=1000, category="home", stock=3)
    db.session.add(other)
    db.session.commit()
    assert owner_a.get(f"/sell/products/{other.id}/edit").status_code == 404
    assert owner_a.post(f"/sell/products/{other.id}/remove").status_code == 404
    assert owner_a.get(f"/admin/products/{other.id}/edit").status_code == 404


def test_drafts_are_hidden(app, admin):
    shop, _ = new_shop(admin)
    admin.post(f"/admin/shops/{shop.id}/products/new", data={
        "name": "Secret item", "price": "50", "stock": "2", "category": "home", "published": "0"})
    p = Product.query.filter_by(name="Secret item").one()
    assert not p.published
    assert app.test_client().get(f"/p/{p.id}").status_code == 404
    assert admin.get(f"/p/{p.id}").status_code == 200  # admin can preview
    assert app.test_client().post(f"/cart/add/{p.id}").status_code == 404


# ---------- Buying ----------

def test_checkout_escrow_flow(app, admin, client):
    shop, temp = new_shop(admin)
    owner = owner_client(app, "owner@shop.gh", temp)
    owner.post("/sell/products/new", content_type="multipart/form-data", data={
        "name": "Beads", "price": "100", "stock": "3", "category": "fashion", "published": "1",
        "photos": [make_image()]})
    p = Product.query.filter_by(name="Beads").one()

    client.post("/region", data={"region": "Ashanti"})
    client.post(f"/cart/add/{p.id}", data={"qty": 2})
    client.post("/cart/add/1", data={"qty": 1})  # kente stole, GH₵350, Ashanti shop
    cart = client.get("/cart").data.decode()
    # 200 + 350 + delivery 45 (Accra->Ashanti) + 25 (Ashanti->Ashanti)
    assert "GH₵620.00" in cart

    r = client.post("/checkout", data={"name": "Ab", "phone": "123", "gps": "x", "region": "Ashanti", "pay": "momo"})
    assert "GhanaPostGPS" in r.data.decode()
    r = client.post("/checkout", data={"name": "Kwame Mensah", "phone": "+233 24 123 4567", "gps": "ak-039-5028",
                                       "region": "Ashanti", "pay": "momo"})
    pay_url = r.headers["Location"]
    assert "MTN MoMo" in client.get(pay_url).data.decode()
    done = client.post(pay_url).headers["Location"]
    code = done.split("/")[2]
    co = Checkout.query.filter_by(code=code).one()
    assert co.pay_status == "paid" and len(co.orders) == 2
    db.session.refresh(p)
    assert p.stock == 1 and p.sold == 2
    order = next(o for o in co.orders if o.shop_id == shop.id)
    assert order.items[0].image_key == p.cover_key

    for _ in range(3):
        owner.post(f"/sell/orders/{order.code}/advance")
    db.session.refresh(order)
    assert order.status == "delivered"
    client.post(f"/orders/item/{order.code}/received")
    db.session.refresh(order)
    assert order.status == "released"
    dash = owner.get("/sell/dashboard").data.decode()
    assert "GH₵184.00" in dash and "GH₵16.00" in dash  # payout and 8% commission on GH₵200

    # Another device needs the order number and phone
    stranger = app.test_client()
    assert stranger.get(f"/orders/{code}").status_code == 404
    stranger.post("/track", data={"code": code.lower(), "phone": "0241234567"})
    assert stranger.get(f"/orders/{code}").status_code == 200

    # Dispute and admin refund on the other order
    other = next(o for o in co.orders if o.shop_id != shop.id)
    client.post(f"/orders/item/{other.code}/problem", data={"note": "Wrong colour"})
    assert "Wrong colour" in admin.get("/admin/").data.decode()
    admin.post(f"/admin/orders/{other.code}/resolve", data={"action": "refund"})
    db.session.refresh(other)
    assert other.status == "cancelled"


def test_pay_on_delivery(client):
    client.post("/cart/add/3", data={"qty": 2})
    r = client.post("/checkout", data={"name": "Efua Boateng", "phone": "0201234567", "gps": "GA-183-8164",
                                       "region": "Greater Accra", "pay": "cod"})
    assert "/done" in r.headers["Location"]
    assert Order.query.one().status == "placed"


def test_admin_pages_render(admin):
    for url in ["/admin/", "/admin/shops", "/admin/shops?q=Accra", "/admin/shops/new", "/admin/applications",
                "/admin/applications?status=approved", "/admin/orders", "/admin/orders?status=disputed",
                "/admin/activity", "/admin/shops/1", "/admin/shops/1/products/new", "/admin/products/1/edit"]:
        assert admin.get(url).status_code == 200, url


def test_signup_password_rules(client):
    r = client.post("/signup", data={"name": "Yaw Darko", "email": "yaw@test.gh", "password": "short"})
    assert "at least 10" in r.data.decode()
    r = client.post("/signup", data={"name": "Yaw Darko", "email": "yaw@test.gh", "password": "GoodPass2026"})
    assert r.status_code == 302
    assert User.query.filter_by(email="yaw@test.gh").one().role == "buyer"
