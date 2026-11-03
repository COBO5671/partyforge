from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import HostUser
from .security import admin_required, current_host

bp = Blueprint("auth", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        user = (
            HostUser.query.filter_by(username=username, active=True).first()
            if username
            else HostUser.query.filter_by(is_owner=True, active=True).first()
        )
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session.clear()
            session["is_admin"] = True
            session["host_user_id"] = user.id
            flash("Welcome back.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("That password is not correct.", "error")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@admin_required
def account():
    user = current_host()
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if not check_password_hash(user.password_hash, current_password):
            flash("The current password was not correct.", "error")
        elif len(new_password) < 10:
            flash("Use at least 10 characters for the new password.", "error")
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("auth.account"))
    return render_template("account.html", user=user)
