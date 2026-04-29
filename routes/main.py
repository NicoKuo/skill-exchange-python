# routes/main.py: Blueprint for main public routes (homepage)
from flask import Blueprint, render_template
from flask_login import current_user

from models import db, User, Skill, Match, Message, Review

main_bp = Blueprint('main', __name__)


@main_bp.route("/", endpoint='index')
def index():
    stats = {
        "users": User.query.filter_by(role="student").count(),
        "skills": Skill.query.filter_by(status="open").count(),
        "matches": Match.query.filter(Match.status.in_(["accepted", "completed", "pending"])).count(),
        "reviews": Review.query.count(),
    }

    popular_skills = Skill.query.filter_by(status="open").order_by(Skill.created_at.desc()).limit(6).all()
    top_users = User.query.filter_by(role="student").limit(5).all()

    # 取得已登入用戶的活躍聊天室（accepted 或 completed 的媒合）
    active_chats = []
    if current_user.is_authenticated:
        matches = Match.query.filter(
            db.or_(
                db.and_(Match.requester_id == current_user.id, Match.status.in_(["accepted", "completed"])),
                db.and_(Match.receiver_id == current_user.id, Match.status.in_(["accepted", "completed"]))
            )
        ).order_by(Match.updated_at.desc()).limit(5).all()

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
        top_users=top_users,
        active_chats=active_chats
    )
