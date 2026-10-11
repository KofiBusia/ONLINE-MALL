"""Accounts: sign up, log in, change password, log out."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import User, utcnow
from ..services import audit
from ..utils import clean_phone, safe_next, valid_email, valid_password, valid_phone

bp = Blueprint("auth", __name__)


def _home_for(user: User) -> str:
    if user.is_admin:
        return url_for("admin.index")
    if user.shop:
        return url_for("seller.dashboard")
    return url_for("main.index")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    error, email = None, ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password") or ""):
            if not user.is_active_account:
                error = "This account is disabled. Contact Edwom support."
            else:
                login_user(user, remember=bool(request.form.get("remember")))
                user.last_login_at = utcnow()
                db.session.commit()
                if user.must_change_password:
                    flash("Welcome. Please choose your own password to continue.", "ok")
                    return redirect(url_for("auth.change_password"))
                return redirect(safe_next(request.args.get("next")) or _home_for(user))
        else:
            error = "That email and password don't match. Try again."
    return render_template("auth/login.html", error=error, email=email)


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    errors, data = {}, {"name": "", "email": "", "phone": ""}
    if request.method == "POST":
        data = {"name": (request.form.get("name") or "").strip()[:120],
                "email": (request.form.get("email") or "").strip().lower(),
                "phone": clean_phone(request.form.get("phone"))}
        password = request.form.get("password") or ""
        if len(data["name"]) < 3:
            errors["name"] = "Enter your full name."
        if not valid_email(data["email"]):
            errors["email"] = "Enter a valid email address."
        elif User.query.filter_by(email=data["email"]).first():
            errors["email"] = "An account with this email already exists. Log in instead."
        if data["phone"] and not valid_phone(data["phone"]):
            errors["phone"] = "Enter a 10-digit Ghana number."
        if msg := valid_password(password):
            errors["password"] = msg
        if not errors:
            user = User(name=data["name"], email=data["email"], phone=data["phone"] or None)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            flash("Welcome to Edwom.", "ok")
            return redirect(safe_next(request.args.get("next")) or url_for("main.index"))
    return render_template("auth/signup.html", errors=errors, data=data)


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    errors = {}
    if request.method == "POST":
        current = request.form.get("current") or ""
        new = request.form.get("new") or ""
        if not current_user.check_password(current):
            errors["current"] = "That isn't your current password."
        if msg := valid_password(new):
            errors["new"] = msg
        elif new == current:
            errors["new"] = "Choose a different password from the current one."
        if new != (request.form.get("confirm") or ""):
            errors["confirm"] = "The two new passwords don't match."
        if not errors:
            current_user.set_password(new)
            current_user.must_change_password = False
            audit("account.password_changed", current_user.email)
            db.session.commit()
            flash("Password updated.", "ok")
            return redirect(_home_for(current_user))
    return render_template("auth/change_password.html", errors=errors)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You're logged out.", "ok")
    return redirect(url_for("main.index"))
