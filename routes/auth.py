# routes/auth.py: Blueprint handling authentication (register, login, logout)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/register", methods=["GET", "POST"], endpoint='register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("姓名、Email 必填，密碼至少 6 碼。", "error")
        elif User.query.filter_by(email=email).first():
            flash("這個 Email 已被註冊。", "error")
        else:
            user = User(name=name, email=email, role="student", bio="")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash("註冊成功，請登入。", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"], endpoint='login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.status == "active":
            login_user(user)
            flash("登入成功。", "success")
            return redirect(url_for("dashboard"))

        flash("Email 或密碼錯誤。", "error")

    return render_template("login.html")


@auth_bp.route("/logout", endpoint='logout')
@login_required
def logout():
    logout_user()
    flash("已登出。", "success")
    return redirect(url_for("index"))
