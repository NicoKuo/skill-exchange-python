# routes/profile.py: 個人資料與儀表板路由
import json
import os
import uuid
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import db, User, Skill, Review, ActivityLog

profile_bp = Blueprint('profile', __name__)

SUPABASE_URL = "https://ksyivufbznpmziyehjpo.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzeWl2dWZiem5wbXppeWVoanBvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzM3Mjk3MSwiZXhwIjoyMDkyOTQ4OTcxfQ.ddbXzrRTrdQqSEitox2RGekly-3MdTtNs-x0A2PRCfg")
BUCKET = "portfolio"


def upload_pdf_to_supabase(file, user_id):
    """上傳 PDF 到 Supabase Storage，回傳公開 URL 或 None"""
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
        current_user.avatar = request.form.get("avatar", "").strip() or None
        current_user.department = request.form.get("department", "").strip() or None
        current_user.grade = request.form.get("grade", "").strip() or None
        current_user.offered_skills_intro = request.form.get("offered_skills_intro", "").strip() or None
        current_user.wanted_skills_intro = request.form.get("wanted_skills_intro", "").strip() or None

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