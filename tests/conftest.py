import io
import re

import pytest
from flask import g
from PIL import Image

from edwom import create_app
from edwom.config import Config
from edwom.extensions import db
from edwom.seed import ensure_admin, seed_demo

ADMIN_EMAIL = "admin@edwom.test"
ADMIN_PASSWORD = "AdminPass123"


class TestConfig(Config):
    TESTING = True
    IS_PRODUCTION = False
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    ADMIN_EMAIL = ADMIN_EMAIL
    ADMIN_PASSWORD = ADMIN_PASSWORD


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    # Tests keep one app context open so they can query the database between requests.
    # Flask then shares `g` across requests, so clear Flask-Login's cached user each time.
    @app.before_request
    def _fresh_login_cache():
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        ensure_admin()
        seed_demo()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def admin(app):
    c = app.test_client()
    assert login(c, ADMIN_EMAIL, ADMIN_PASSWORD).status_code == 302
    return c


def make_image(width=900, height=700, color=(200, 120, 40), fmt="JPEG", name="photo.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, fmt)
    buf.seek(0)
    return (buf, name)


def temp_password_from(html: str) -> str:
    return re.search(r'class="pw">([^<]+)<', html).group(1)
