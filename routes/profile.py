import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from models import db, User, Skill, Review, ActivityLog

profile_bp = Blueprint('profile', __name__)


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
        titles = request.form.getlist("portfolio_title")
        descs  = request.form.getlist("portfolio_desc")
        imgs   = request.form.getlist("portfolio_image")
        links  = request.form.getlist("portfolio_link")
        portfolio_items = []
        for t, d, i, l in zip(titles, descs, imgs, links):
            t = t.strip()
            if t:
                portfolio_items.append({"title": t, "desc": d.strip(), "image_url": i.strip(), "link_url": l.strip()})
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