# routes/profile.py: 個人資料與儀表板路由
# 功能：個人儀表板、編輯個人資料、查看他人公開資料頁
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import db, User, Skill, Review, ActivityLog

profile_bp = Blueprint('profile', __name__)


@profile_bp.route("/dashboard", endpoint='dashboard')
@login_required
def dashboard():
    """
    個人儀表板路由。
    顯示目前登入使用者上架的所有技能（包含下架的），依建立時間倒序排列。
    需登入才可存取。
    """
    my_skills = Skill.query.filter_by(user_id=current_user.id).order_by(Skill.created_at.desc()).all()
    return render_template("dashboard.html", my_skills=my_skills)


@profile_bp.route("/profile", methods=["GET", "POST"], endpoint='profile')
@login_required
def profile():
    """
    個人資料編輯路由。
    GET：顯示個人資料表單（含使用者收到的評價列表）。
    POST：更新個人資料，可修改姓名、自我介紹、頭像、系所、年級、技能簡介，
          若填寫新密碼（至少 6 碼）則一併更新密碼。
    成功儲存後記錄活動日誌並導回此頁。
    """
    if request.method == "POST":
        # 更新基本資料
        current_user.name = request.form.get("name", "").strip()
        current_user.bio = request.form.get("bio", "").strip()
        current_user.avatar = request.form.get("avatar", "").strip() or None
        # 更新學生身份欄位
        current_user.department = request.form.get("department", "").strip() or None
        current_user.grade = request.form.get("grade", "").strip() or None
        current_user.offered_skills_intro = request.form.get("offered_skills_intro", "").strip() or None
        current_user.wanted_skills_intro = request.form.get("wanted_skills_intro", "").strip() or None

        new_password = request.form.get("new_password", "").strip()

        # 表單驗證
        if not current_user.name:
            flash("姓名不能空白。", "error")
        elif new_password and len(new_password) < 6:
            flash("新密碼至少 6 碼。", "error")
        else:
            # 若使用者輸入新密碼，一併更新密碼雜湊
            if new_password:
                current_user.set_password(new_password)
            db.session.commit()
            # 記錄資料更新的活動日誌
            try:
                log = ActivityLog(user_id=current_user.id, action='update_profile', detail='profile updated', ip_address=request.remote_addr)
                db.session.add(log)
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash("個人資料已更新。", "success")
            return redirect(url_for(".profile"))

    # 取得此使用者收到的所有評價，依時間倒序顯示
    reviews = Review.query.filter_by(reviewee_id=current_user.id).order_by(Review.created_at.desc()).all()
    return render_template("profile.html", reviews=reviews)


@profile_bp.route("/user/<int:user_id>", endpoint='view_user')
def view_user(user_id):
    """
    查看他人公開個人資料頁路由。
    顯示指定使用者的技能列表與收到的評價。
    若使用者帳號非 active 狀態（停權或封禁），回傳 404 以保護被封帳號隱私。
    不需登入即可查看。
    """
    user = User.query.get_or_404(user_id)
    # 非正常狀態的帳號不公開顯示
    if user.status != 'active':
        abort(404)
    # 只顯示上架中的技能
    skills = Skill.query.filter_by(user_id=user.id, status="open", is_active=True).order_by(Skill.created_at.desc()).all()
    # 取得此使用者收到的所有評價
    reviews = Review.query.filter_by(reviewee_id=user.id).order_by(Review.created_at.desc()).all()
    return render_template("user_profile.html", user=user, skills=skills, reviews=reviews)
