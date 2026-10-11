"""Security headers and request guards."""
from flask import flash, redirect, request, url_for
from flask_login import current_user

CSP = "; ".join([
    "default-src 'self'",
    "img-src 'self' data: blob:",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "script-src 'self'",
    "connect-src 'self'",
    "form-action 'self' https://checkout.paystack.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])

PASSWORD_CHANGE_ALLOWED = {"auth.change_password", "auth.logout", "static", "main.media", "main.healthz"}


def init_security(app):
    @app.after_request
    def headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if app.config["IS_PRODUCTION"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if current_user.is_authenticated and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "private, no-store"
        return resp

    @app.before_request
    def force_password_change():
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint not in PASSWORD_CHANGE_ALLOWED):
            if request.method == "GET":
                flash("Please choose your own password before continuing.", "error")
            return redirect(url_for("auth.change_password"))
