# routes/profile.py: 個人資料與儀表板路由
import json
import os
import uuid
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import db, User, Skill, Review, ActivityLog, Report
from datetime import datetime

profile_bp = Blueprint('profile', __name__)

SUPABASE_URL = "https://ksyivufbznpmziyehjpo.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzeWl2dWZiem5wbXppeWVoanBvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzM3Mjk3MSwiZXhwIjoyMDkyOTQ4OTcxfQ.ddbXzrRTrdQqSEitox2RGekly-3MdTtNs-x0A2PRCfg")
BUCKET = "portfolio"


def upload_pdf_to_supabase(file, user_id):
    if not file or file.filename == '':
        return None
    if not file.filename.lower().endswith('.pdf'):
        return None
    filename = f"{user_id}/{uuid.uuid4().hex}.pdf"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{filename}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }
    try:
        resp = requests.put(upload_url, data=file.read(), headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"
    except Exception as e:
        print(f"[Supabase upload error] {e}")
    return None


def upload_avatar_to_supabase(file, user_id):
    if not file or file.filename == '':
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
        return None
    filename = f"{user_id}/{uuid.uuid4().hex}.{ext}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/avatars/{filename}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": f"image/{ext}",
        "x-upsert": "true",
    }
    try:
        resp = requests.put(upload_url, data=file.read(), headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            return f"{SUPABASE_URL}/storage/v1/object/public/avatars/{filename}"
    except Exception as e:
        print(f"[Supabase avatar upload error] {e}")
    return None


@profile_bp.route("/dashboard", endpoint='dashboard')
@login_required
def dashboard():
    my_skills = Skill.query.filter_by(user_id=current_user.id).order_by(Skill.created_at.desc()).all()
    return render_template("dashboard.html", my_skills=my_skills)


@profile_bp.route("/profile", methods=["GET", "POST"], endpoint='profile')
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", "").strip()
        current_user.bio = request.form.get("bio", "").strip()
        current_user.department = request.form.get("department", "").strip() or None
        current_user.grade = request.form.get("grade", "").strip() or None
        current_user.offered_skills_intro = request.form.get("offered_skills_intro", "").strip() or None
        current_user.wanted_skills_intro = request.form.get("wanted_skills_intro", "").strip() or None

        # 頭像：優先用上傳檔案，其次用網址
        avatar_file = request.files.get("avatar_file")
        if avatar_file and avatar_file.filename:
            uploaded_avatar = upload_avatar_to_supabase(avatar_file, current_user.id)
            if uploaded_avatar:
                current_user.avatar = uploaded_avatar
        else:
            current_user.avatar = request.form.get("avatar", "").strip() or None

        # 作品集
        titles   = request.form.getlist("portfolio_title")
        descs    = request.form.getlist("portfolio_desc")
        links    = request.form.getlist("portfolio_link")
        old_pdfs = request.form.getlist("portfolio_pdf_existing")
        new_pdfs = request.files.getlist("portfolio_pdf")

        portfolio_items = []
        for i, t in enumerate(titles):
            t = t.strip()
            if not t:
                continue
            pdf_url = None
            if i < len(new_pdfs) and new_pdfs[i].filename:
                pdf_url = upload_pdf_to_supabase(new_pdfs[i], current_user.id)
            if not pdf_url and i < len(old_pdfs):
                pdf_url = old_pdfs[i].strip() or None
            portfolio_items.append({
                "title": t,
                "desc": descs[i].strip() if i < len(descs) else "",
                "pdf_url": pdf_url or "",
                "link_url": links[i].strip() if i < len(links) else "",
            })

        current_user.portfolio = json.dumps(portfolio_items, ensure_ascii=False) if portfolio_items else None

        new_password = request.form.get("new_password", "").strip()

        if not current_user.name:
            flash("姓名不能空白。", "error")
        elif new_password and len(new_password) < 6:
            flash("新密碼至少 6 碼。", "error")
        else:
            if new_password:
                current_user.set_password(new_password)
            db.session.commit()
            try:
                log = ActivityLog(user_id=current_user.id, action='update_profile', detail='profile updated', ip_address=request.remote_addr)
                db.session.add(log)
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash("個人資料已更新。", "success")
            return redirect(url_for(".profile"))

    reviews = Review.query.filter_by(reviewee_id=current_user.id).order_by(Review.created_at.desc()).all()
    portfolio = json.loads(current_user.portfolio) if current_user.portfolio else []
    return render_template("profile.html", reviews=reviews, portfolio=portfolio)


@profile_bp.route("/user/<int:user_id>", endpoint='view_user')
def view_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.status != 'active':
        abort(404)
    skills = Skill.query.filter_by(user_id=user.id, status="open", is_active=True).order_by(Skill.created_at.desc()).all()
    reviews = Review.query.filter_by(reviewee_id=user.id).order_by(Review.created_at.desc()).all()
    portfolio = json.loads(user.portfolio) if user.portfolio else []
    return render_template("user_profile.html", user=user, skills=skills, reviews=reviews, portfolio=portfolio)


@profile_bp.route("/user/<int:user_id>/report", methods=['GET', 'POST'], endpoint='report_user')
def report_user(user_id):
    """
    個人檔案檢舉路由。
    GET: 顯示檢舉表單。
    POST: 建立檢舉報告。
    """
    reported_user = User.query.get_or_404(user_id)

    # 不能檢舉自己
    if current_user.is_authenticated and reported_user.id == current_user.id:
        flash('不能檢舉自己。', 'error')
        return redirect(url_for('.view_user', user_id=user_id))

    # 檢舉原因選項
    report_reasons = [
        '不當個人介紹',
        '假資料或冒名',
        '騷擾或攻擊性內容',
        '廣告或垃圾訊息',
        '違反平台規範',
        '其他'
    ]

    if request.method == 'GET':
        if not current_user.is_authenticated:
            flash('請先登入才能檢舉。', 'error')
            return redirect(url_for('auth.login'))
        return render_template(
            'report_profile.html',
            reported_user=reported_user,
            report_reasons=report_reasons
        )

    # POST 邏輯
    if not current_user.is_authenticated:
        flash('請先登入才能檢舉。', 'error')
        return redirect(url_for('auth.login'))

    reason = request.form.get('reason', '').strip()
    description = request.form.get('description', '').strip()

    # 驗證
    if not reason:
        flash('請選擇檢舉原因。', 'error')
        return render_template(
            'report_profile.html',
            reported_user=reported_user,
            report_reasons=report_reasons
        )

    if reason == '其他' and not description:
        flash('選擇「其他」時，補充說明必填。', 'error')
        return render_template(
            'report_profile.html',
            reported_user=reported_user,
            report_reasons=report_reasons,
            description_value=description
        )

    # 檢查重複檢舉
    existing = Report.query.filter(
        Report.reporter_id == current_user.id,
        Report.reported_user_id == reported_user.id,
        Report.report_type == 'profile',
        Report.status.in_(['pending', 'reviewing'])
    ).first()

    if existing:
        flash('你已經檢舉過此個人檔案，請等待管理員處理。', 'warning')
        return redirect(url_for('.view_user', user_id=user_id))

    # 建立檢舉
    try:
        report = Report(
            reporter_id=current_user.id,
            reported_user_id=reported_user.id,
            report_type='profile',
            reason=reason,
            description=description if description else None,
            status='pending'
        )
        db.session.add(report)
        db.session.commit()
        flash('檢舉已送出，管理員會盡快處理。', 'success')
        return redirect(url_for('.view_user', user_id=user_id))
    except Exception as e:
        db.session.rollback()
        print(f'[Report Error] {str(e)}')
        import traceback
        traceback.print_exc()
        flash('送出檢舉時發生錯誤，請稍後再試。', 'error')
        return render_template(
            'report_profile.html',
            reported_user=reported_user,
            report_reasons=report_reasons,
            description_value=description
        )