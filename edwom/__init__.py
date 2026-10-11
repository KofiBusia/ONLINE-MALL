"""Edwom Online Mall: a multi-vendor marketplace for Ghanaian small businesses."""
import logging
import os

from flask import Flask, flash, redirect, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)

    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if app.config["IS_PRODUCTION"]:
        if app.config["SECRET_KEY"] == "dev-only-not-secret":
            raise RuntimeError("Set the SECRET_KEY environment variable in production.")
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Log in to continue."
    login_manager.session_protection = "strong"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user if user and user.is_active_account else None

    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.main import bp as main_bp
    from .routes.seller import bp as seller_bp

    for bp in (main_bp, auth_bp, seller_bp, admin_bp):
        app.register_blueprint(bp)

    from .cli import register_cli
    from .filters import register_filters
    from .security import init_security

    register_filters(app)
    register_cli(app)
    init_security(app)

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(_):
        flash(f"Those photos are too large together. Upload fewer at a time "
              f"(each up to {app.config['MAX_PHOTO_MB']} MB).", "error")
        return redirect(request.path), 303

    @app.errorhandler(429)
    def too_many(_):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(_):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    return app
