# 認證 - 登入、註冊、登出
# routes/auth.py: Blueprint handling authentication (register, login, logout)
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from models import db, User, ActivityLog

auth_bp = Blueprint('auth', __name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


@auth_bp.route("/register", methods=["GET", "POST"], endpoint='register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for("profile.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("姓名、Email 必填，密碼至少 6 碼。", "error")
        elif User.query.filter_by(email=email).first():
            flash("這個 Email 已被註冊。", "error")
        else:
            user = User(name=name, email=email, role="user", bio="")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash("註冊成功，請登入。", "success")
            return redirect(url_for(".login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"], endpoint='login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for("profile.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user:
            # 帳號已被停權（非鎖定）
            if user.status != 'active':
                flash("此帳號已被停權，請聯絡管理員。", "error")
                return render_template("login.html")

            # 檢查是否在鎖定期間
            now = datetime.utcnow()
            if user.locked_until and now < user.locked_until:
                remaining = int((user.locked_until - now).total_seconds() / 60) + 1
                flash(f"帳號已鎖定，請 {remaining} 分鐘後再試。", "error")
                return render_template("login.html")

            # 密碼正確
            if user.check_password(password):
                # 清除失敗計數
                user.failed_login_attempts = 0
                user.locked_until = None
                db.session.commit()

                login_user(user)
                try:
                    log = ActivityLog(user_id=user.id, action='login', detail='user login', ip_address=request.remote_addr)
                    db.session.add(log)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

                flash("登入成功。", "success")
                if user.role in {"admin", "super_admin"}:
                    return redirect(url_for("admin.dashboard"))
                return redirect(url_for("profile.dashboard"))

            # 密碼錯誤：累計次數
            else:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

                if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                    db.session.commit()
                    try:
                        log = ActivityLog(user_id=user.id, action='account_locked', detail=f'locked after {MAX_FAILED_ATTEMPTS} failed attempts', ip_address=request.remote_addr)
                        db.session.add(log)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    flash(f"密碼錯誤次數過多，帳號已鎖定 {LOCKOUT_MINUTES} 分鐘。", "error")
                else:
                    db.session.commit()
                    remaining_attempts = MAX_FAILED_ATTEMPTS - user.failed_login_attempts
                    flash(f"Email 或密碼錯誤，還剩 {remaining_attempts} 次機會。", "error")

                return render_template("login.html")

        flash("Email 或密碼錯誤。", "error")

    return render_template("login.html")


@auth_bp.route("/logout", endpoint='logout')
@login_required
def logout():
    logout_user()
    flash("已登出。", "success")
    return redirect(url_for("main.index"))