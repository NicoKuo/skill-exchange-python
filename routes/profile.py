# routes/profile.py: Blueprint for user profile and dashboard routes
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, Skill, Review, Match
from utils import user_completed_matches, user_average_rating, user_points

profile_bp = Blueprint('profile', __name__)


def get_user_stats(user_id):
    """計算用戶技能統計數據"""
    completed = user_completed_matches(user_id)
    avg_rating = user_average_rating(user_id)
    points = user_points(user_id)

    skills_offered = Skill.query.filter_by(user_id=user_id, type="offer", status="open").count()
    skills_wanted = Skill.query.filter_by(user_id=user_id, type="request", status="open").count()
    total_reviews = Review.query.filter_by(reviewee_id=user_id).count()

    # 送出的媒合邀請
    sent_matches = Match.query.filter_by(requester_id=user_id).count()
    # 收到的媒合邀請
    received_matches = Match.query.filter_by(receiver_id=user_id).count()

    return {
        "completed_matches": completed,
        "avg_rating": round(avg_rating, 1) if avg_rating else 0,
        "points": points,
        "skills_offered": skills_offered,
        "skills_wanted": skills_wanted,
        "total_reviews": total_reviews,
        "sent_matches": sent_matches,
        "received_matches": received_matches,
    }


def get_user_badges(stats):
    """根據統計數據產生成就徽章清單"""
    badges = []

    # ── 媒合相關 ──────────────────────────────────────────────
    if stats["completed_matches"] >= 1:
        badges.append({
            "id": "first_match",
            "icon": "🤝",
            "name": "初次交換",
            "desc": "完成第一次技能媒合",
            "tier": "bronze",
        })
    if stats["completed_matches"] >= 5:
        badges.append({
            "id": "match_5",
            "icon": "🔗",
            "name": "技能橋梁",
            "desc": "完成 5 次媒合",
            "tier": "silver",
        })
    if stats["completed_matches"] >= 20:
        badges.append({
            "id": "match_20",
            "icon": "🌐",
            "name": "交換大師",
            "desc": "完成 20 次媒合",
            "tier": "gold",
        })

    # ── 評分相關 ──────────────────────────────────────────────
    if stats["avg_rating"] >= 4.0 and stats["total_reviews"] >= 3:
        badges.append({
            "id": "good_rating",
            "icon": "⭐",
            "name": "好評如潮",
            "desc": "平均評分 4.0 以上",
            "tier": "silver",
        })
    if stats["avg_rating"] >= 4.8 and stats["total_reviews"] >= 5:
        badges.append({
            "id": "perfect_rating",
            "icon": "🌟",
            "name": "完美評價",
            "desc": "平均評分 4.8 以上且有 5 則評價",
            "tier": "gold",
        })

    # ── 技能分享 ──────────────────────────────────────────────
    if stats["skills_offered"] >= 1:
        badges.append({
            "id": "first_skill",
            "icon": "🎯",
            "name": "技能先鋒",
            "desc": "上架第一個技能",
            "tier": "bronze",
        })
    if stats["skills_offered"] >= 5:
        badges.append({
            "id": "skill_5",
            "icon": "🎨",
            "name": "多才多藝",
            "desc": "上架 5 個以上的技能",
            "tier": "silver",
        })

    # ── 積分相關 ──────────────────────────────────────────────
    if stats["points"] >= 100:
        badges.append({
            "id": "points_100",
            "icon": "💎",
            "name": "積分達人",
            "desc": "累積 100 點積分",
            "tier": "gold",
        })

    # ── 社群參與 ──────────────────────────────────────────────
    if stats["total_reviews"] >= 10:
        badges.append({
            "id": "reviewer",
            "icon": "✍️",
            "name": "熱心評價者",
            "desc": "收到 10 則評價",
            "tier": "silver",
        })

    return badges


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

        new_password = request.form.get("new_password", "").strip()

        if not current_user.name:
            flash("姓名不能空白。", "error")
        elif new_password and len(new_password) < 6:
            flash("新密碼至少 6 碼。", "error")
        else:
            if new_password:
                current_user.set_password(new_password)
            db.session.commit()
            flash("個人資料已更新。", "success")
            return redirect(url_for(".profile"))

    reviews = Review.query.filter_by(reviewee_id=current_user.id).order_by(Review.created_at.desc()).all()

    # ── 新增：統計與徽章 ──────────────────────────────────────
    stats = get_user_stats(current_user.id)
    badges = get_user_badges(stats)

    return render_template(
        "profile.html",
        reviews=reviews,
        stats=stats,
        badges=badges,
    )