# routes/auth.py: 認證路由（登入、註冊、登出）
# 包含暴力破解防護：連續失敗 5 次後鎖定帳號 30 分鐘
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import db, User, ActivityLog

auth_bp = Blueprint('auth', __name__)

# 最大允許的連續登入失敗次數
MAX_FAILED_ATTEMPTS = 5
# 超過失敗次數後的鎖定時間（分鐘）
LOCKOUT_MINUTES = 30


@auth_bp.route("/register", methods=["GET", "POST"], endpoint='register')
def register():
    """
    使用者註冊路由。
    GET：顯示註冊表單。
    POST：驗證表單資料後建立新帳號，成功則導向登入頁。
    驗證規則：姓名和 Email 必填、密碼至少 6 碼、Email 不可重複。
    """
    # 已登入的使用者直接導向儀表板
    if current_user.is_authenticated:
        return redirect(url_for("profile.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # 基本欄位驗證
        if not name or not email or len(password) < 6:
            flash("姓名、Email 必填，密碼至少 6 碼。", "error")
        else:
            # 檢查 Email 是否已被使用
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash("此 Email 已被註冊，請直接登入或使用其他 Email。", "error")
            else:
                # 建立新使用者，預設角色為 user
                user = User(name=name, email=email, role="user", bio="")
                user.set_password(password)
                try:
                    db.session.add(user)
                    db.session.commit()
                except IntegrityError:
                    # 處理並發情況下的 Email 重複錯誤
                    db.session.rollback()
                    flash("此 Email 已被註冊，請直接登入或使用其他 Email。", "error")
                else:
                    flash("註冊成功，請登入。", "success")
                    return redirect(url_for(".login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"], endpoint='login')
def login():
    """
    使用者登入路由。
    GET：顯示登入表單。
    POST：驗證帳密，處理各種帳號狀態，成功後記錄活動日誌並導向對應頁面。

    帳號狀態處理：
    - suspended：停權，顯示錯誤
    - banned / blocked：封禁，顯示錯誤
    - 其他非 active 狀態：無法登入

    暴力破解防護：
    - 密碼錯誤累計到 MAX_FAILED_ATTEMPTS 次後鎖定帳號
    - 鎖定期間顯示剩餘等待時間
    """
    # 已登入的使用者直接導向儀表板
    if current_user.is_authenticated:
        return redirect(url_for("profile.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user:
            account_status = (user.status or 'active').strip()

            # 帳號狀態檢查
            if account_status == 'suspended':
                flash("帳號已被停權，請聯繫管理員", "error")
                return render_template("login.html")

            if account_status in {'banned', 'blocked'}:
                flash("帳號已被封禁，無法登入", "error")
                return render_template("login.html")

            if account_status != 'active':
                flash("此帳號無法登入，請聯繫管理員。", "error")
                return render_template("login.html")

            # 檢查帳號是否在鎖定期間（暴力破解防護）
            now = datetime.utcnow()
            if user.locked_until and now < user.locked_until:
                remaining = int((user.locked_until - now).total_seconds() / 60) + 1
                flash(f"帳號已鎖定，請 {remaining} 分鐘後再試。", "error")
                return render_template("login.html")

            # 密碼驗證正確
            if user.check_password(password):
                # 清除登入失敗記錄
                user.failed_login_attempts = 0
                user.locked_until = None
                db.session.commit()

                login_user(user)
                # 記錄登入活動日誌
                try:
                    log = ActivityLog(user_id=user.id, action='login', detail='user login', ip_address=request.remote_addr)
                    db.session.add(log)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

                flash("登入成功。", "success")
                # 管理員導向後台，一般使用者導向儀表板
                if user.role in {"admin", "super_admin"}:
                    return redirect(url_for("admin.dashboard"))
                return redirect(url_for("profile.dashboard"))

            # 密碼錯誤：累計失敗次數
            else:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

                # 達到失敗上限，鎖定帳號並記錄日誌
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

        # 找不到此 Email 的帳號
        flash("Email 或密碼錯誤。", "error")

    return render_template("login.html")


@auth_bp.route("/logout", endpoint='logout')
@login_required
def logout():
    """
    使用者登出路由。
    結束 Session 並導回首頁，需已登入才可存取。
    """
    logout_user()
    flash("已登出。", "success")
    return redirect(url_for("main.index"))
