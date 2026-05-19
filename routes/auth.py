# routes/auth.py: 認證路由（登入、註冊、登出）
# 包含暴力破解防護：連續失敗 5 次後鎖定帳號 30 分鐘
from datetime import datetime, timedelta
import os
import random
import resend

from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from models import db, User, ActivityLog, Skill, EmailVerification

auth_bp = Blueprint('auth', __name__)

# 最大允許的連續登入失敗次數
MAX_FAILED_ATTEMPTS = 5
# 超過失敗次數後的鎖定時間（分鐘）
LOCKOUT_MINUTES = 30
# 註冊驗證碼有效時間（分鐘）
REGISTRATION_CODE_TTL_MINUTES = 10
# 驗證碼錯誤上限
REGISTRATION_CODE_MAX_ATTEMPTS = 5


def create_verification_code(email, purpose='register'):
    return str(random.randint(100000, 999999))


def store_verification_code(email, code, purpose='register'):
    try:
        EmailVerification.query.filter_by(
            email=email, purpose=purpose, is_used=False
        ).update({'is_used': True})
        record = EmailVerification(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(minutes=REGISTRATION_CODE_TTL_MINUTES)
        )
        db.session.add(record)
        db.session.commit()
        return code
    except Exception:
        db.session.rollback()
        raise


def verify_code(email, code, purpose='register'):
    record = EmailVerification.query.filter_by(
        email=email, purpose=purpose, is_used=False
    ).order_by(EmailVerification.created_at.desc()).first()
    if not record:
        return False, '驗證碼不存在或已使用'
    if datetime.utcnow() > record.expires_at:
        return False, '驗證碼已過期，請重新寄送'
    if record.attempts >= 5:
        return False, '錯誤次數過多，請重新寄送'
    if record.code != code:
        record.attempts += 1
        db.session.commit()
        return False, f'驗證碼錯誤，剩餘 {5 - record.attempts} 次'
    record.is_used = True
    db.session.commit()
    return True, 'ok'


def _clear_registration_verification():
    session.pop('register_verification', None)


def _get_registration_verification():
    return session.get('register_verification')


def _is_registration_debug_mode():
    return current_app.debug or os.getenv('FLASK_ENV') == 'development'


def _remove_registration_verification(email, purpose='register'):
    record = EmailVerification.query.filter_by(
        email=email, purpose=purpose, is_used=False
    ).order_by(EmailVerification.created_at.desc()).first()
    if record:
        db.session.delete(record)
        db.session.commit()


def _send_registration_verification_email(email, name, code):
    """寄送註冊驗證碼；若未設定 RESEND_API_KEY，則只寫入 log。"""
    api_key = current_app.config.get('RESEND_API_KEY') or os.getenv('RESEND_API_KEY')
    mail_from = (
        current_app.config.get('RESEND_FROM')
        or os.getenv('RESEND_FROM')
        or current_app.config.get('MAIL_FROM')
        or os.getenv('MAIL_FROM')
        or 'onboarding@resend.dev'
    )

    if not api_key:
        current_app.logger.warning(
            'RESEND_API_KEY 未設定，驗證碼未實際寄送：%s -> %s', email, code
        )
        return False

    resend.api_key = api_key
    response = resend.Emails.send({
        'from': mail_from,
        'to': [email],
        'subject': 'SkillSwap 註冊驗證碼',
        'text': (
            f'{name} 您好,\n\n'
            f'您的 SkillSwap 註冊驗證碼是：{code}\n\n'
            f'此驗證碼將於 {REGISTRATION_CODE_TTL_MINUTES} 分鐘後失效。\n'
            f'若這不是您本人操作，請忽略此郵件。'
        ),
    })

    if response:
        return True

    current_app.logger.error('Resend 寄信失敗：%s', response)
    return False


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

    pending_verification = _get_registration_verification()

    if request.method == "POST":
        action = request.form.get('action', 'send_code')

        if action == 'verify_code':
            if not pending_verification:
                flash('請先完成註冊驗證碼寄送。', 'error')
                return render_template('register.html', pending_verification=None)

            verification_code = request.form.get('verification_code', '').strip()
            if not verification_code:
                flash('請輸入驗證碼。', 'error')
                return render_template('register.html', pending_verification=pending_verification)

            email = pending_verification.get('email', '').strip().lower()
            is_valid, message = verify_code(email, verification_code)
            if not is_valid:
                flash(message, 'error')
                return render_template('register.html', pending_verification=pending_verification)

            name = pending_verification.get('name', '').strip()
            password_hash = pending_verification.get('password_hash', '')

            if not email or not name or not password_hash:
                _clear_registration_verification()
                flash('註冊資料已失效，請重新註冊。', 'error')
                return render_template('register.html', pending_verification=None)

            if User.query.filter_by(email=email).first():
                _clear_registration_verification()
                flash('此 Email 已被註冊，請直接登入或使用其他 Email。', 'error')
                return render_template('register.html', pending_verification=None)

            user = User(name=name, email=email, role='user', bio='')
            user.password_hash = password_hash

            try:
                db.session.add(user)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('此 Email 已被註冊，請直接登入或使用其他 Email。', 'error')
                return render_template('register.html', pending_verification=None)

            _clear_registration_verification()
            flash('Email 驗證成功，帳號已建立，請登入。', 'success')
            return redirect(url_for('.login'))

        if action == 'resend_code':
            if not pending_verification:
                flash('請先完成註冊資料填寫。', 'error')
                return render_template('register.html', pending_verification=None)

            api_key = current_app.config.get('RESEND_API_KEY') or os.getenv('RESEND_API_KEY')
            verification_code = create_verification_code(
                pending_verification['email'],
                purpose='register'
            )

            try:
                sent = _send_registration_verification_email(
                    pending_verification['email'],
                    pending_verification['name'],
                    verification_code,
                )
                if sent:
                    try:
                        store_verification_code(pending_verification['email'], verification_code, purpose='register')
                        flash('新的驗證碼已重新寄出。', 'success')
                    except Exception:
                        current_app.logger.exception('儲存重新寄送的驗證碼失敗')
                        flash('驗證碼已寄出，但儲存失敗，請重新寄送。', 'error')
                else:
                    if _is_registration_debug_mode() and not api_key:
                        try:
                            store_verification_code(pending_verification['email'], verification_code, purpose='register')
                            flash(f'Resend 未設定，開發驗證碼為：{verification_code}', 'warning')
                        except Exception:
                            current_app.logger.exception('儲存開發模式驗證碼失敗')
                            flash('開發驗證碼儲存失敗，請稍後再試。', 'error')
                    else:
                        flash('Resend 寄信失敗，請稍後再試。', 'error')
            except Exception:
                current_app.logger.exception('重新寄送註冊驗證碼失敗')
                db.session.rollback()
                if _is_registration_debug_mode() and not api_key:
                    try:
                        store_verification_code(pending_verification['email'], verification_code, purpose='register')
                        flash(f'Resend 未設定，開發驗證碼為：{verification_code}', 'warning')
                    except Exception:
                        current_app.logger.exception('儲存開發模式驗證碼失敗')
                        flash('開發驗證碼儲存失敗，請稍後再試。', 'error')
                else:
                    flash('驗證碼寄送失敗，請稍後再試。', 'error')

            return render_template('register.html', pending_verification=pending_verification)

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
                api_key = current_app.config.get('RESEND_API_KEY') or os.getenv('RESEND_API_KEY')
                verification_code = create_verification_code(email, purpose='register')
                pending_verification = {
                    'name': name,
                    'email': email,
                    'password_hash': generate_password_hash(password),
                }
                session['register_verification'] = pending_verification
                try:
                    sent = _send_registration_verification_email(email, name, verification_code)
                    if sent:
                        try:
                            store_verification_code(email, verification_code, purpose='register')
                            flash('驗證碼已寄到 {email}，請輸入完成驗證。', 'success')
                        except Exception:
                            current_app.logger.exception('儲存註冊驗證碼失敗')
                            _clear_registration_verification()
                            flash('驗證碼已寄出，但儲存失敗，請重新註冊。', 'error')
                    else:
                        if _is_registration_debug_mode() and not api_key:
                            try:
                                store_verification_code(email, verification_code, purpose='register')
                                flash(f'Resend 未設定，開發驗證碼為：{verification_code}', 'warning')
                            except Exception:
                                current_app.logger.exception('儲存開發模式驗證碼失敗')
                                _clear_registration_verification()
                                flash('開發驗證碼儲存失敗，請稍後再試。', 'error')
                        else:
                            _clear_registration_verification()
                            flash('Resend 寄信失敗，請稍後再試。', 'error')
                except Exception:
                    current_app.logger.exception('寄送註冊驗證碼失敗')
                    db.session.rollback()
                    if _is_registration_debug_mode() and not api_key:
                        try:
                            store_verification_code(email, verification_code, purpose='register')
                            flash(f'Resend 未設定，開發驗證碼為：{verification_code}', 'warning')
                        except Exception:
                            current_app.logger.exception('儲存開發模式驗證碼失敗')
                            _clear_registration_verification()
                            flash('開發驗證碼儲存失敗，請稍後再試。', 'error')
                    else:
                        _clear_registration_verification()
                        flash('驗證碼寄送失敗，請稍後再試。', 'error')

    return render_template("register.html", pending_verification=_get_registration_verification())


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

                # 檢查使用者是否有已上架的技能
                has_active_skills = Skill.query.filter_by(
                    user_id=user.id, 
                    is_active=True,
                    status='open'
                ).first() is not None
                
                # 如果沒有已上架的技能，設置 session 標記以顯示公告
                if not has_active_skills:
                    session['show_skill_announcement'] = True
                else:
                    session['show_skill_announcement'] = False

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
