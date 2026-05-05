# 首頁 - 顯示平台概覽、熱門技能、排行榜、活躍聊天室
# routes/main.py: Blueprint for main public routes (homepage)
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user

from models import db, User, Skill, Match, Message, Review
from utils import user_completed_matches, user_average_rating, user_points

main_bp = Blueprint('main', __name__)


@main_bp.route("/", endpoint='index')
def index():
    stats = {
        "users": User.query.count(),
        "skills": Skill.query.filter_by(status="open", is_active=True).count(),
        "matches": Match.query.filter(Match.status.in_(["accepted", "completed", "pending"])).count(),
        "reviews": Review.query.count(),
    }

    popular_skills = Skill.query.filter_by(status="open", is_active=True).order_by(Skill.created_at.desc()).limit(4).all()
    all_users = User.query.all()
    leaderboard = []
    for user in all_users:
        points = user_points(user.id)
        completed_matches = user_completed_matches(user.id)
        average_rating = user_average_rating(user.id)
        leaderboard.append({
            "user": user,
            "points": points,
            "completed_matches": completed_matches,
            "average_rating": average_rating,
        })

    leaderboard.sort(
        key=lambda item: (
            item["points"],
            item["completed_matches"],
            item["average_rating"],
            -item["user"].id,
        ),
        reverse=True,
    )
    leaderboard = leaderboard[:5]

    # 取得已登入用戶的活躍聊天室（accepted 或 completed 的媒合），限制 4 個
    active_chats = []
    if current_user.is_authenticated:
        matches = Match.query.filter(
            db.or_(
                db.and_(Match.requester_id == current_user.id, Match.status.in_(["accepted", "completed"])),
                db.and_(Match.receiver_id == current_user.id, Match.status.in_(["accepted", "completed"]))
            )
        ).order_by(Match.updated_at.desc()).limit(4).all()

        for match in matches:
            # 判斷對方是誰
            if match.requester_id == current_user.id:
                other_user = match.receiver
            else:
                other_user = match.requester

            # 取得最後一則訊息
            last_message = Message.query.filter_by(match_id=match.id).order_by(Message.created_at.desc()).first()

            # 計算未讀訊息數
            unread_count = Message.query.filter_by(
                match_id=match.id,
                receiver_id=current_user.id,
                is_read=False
            ).count()

            active_chats.append({
                "match_id": match.id,
                "other_user": other_user,
                "skill": match.skill,
                "last_message": last_message,
                "unread_count": unread_count,
                "updated_at": match.updated_at
            })


    return render_template(
        "index.html",
        stats=stats,
        popular_skills=popular_skills,
        leaderboard=leaderboard,
        active_chats=active_chats,
    )


@main_bp.route("/admin-entry", endpoint='admin_entry')
def admin_entry():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    if current_user.role in ["admin", "super_admin"]:
        return redirect(url_for("admin.dashboard"))

    flash("你沒有權限進入管理後台。", "error")
    return redirect(url_for("main.index"))
