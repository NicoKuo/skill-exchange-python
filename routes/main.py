# routes/main.py: 首頁與管理員入口路由
# 功能：顯示平台統計數字、熱門技能、排行榜、已登入使用者的活躍聊天室
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user

from models import db, User, Skill, Match, Message, Review
from utils import user_completed_matches, user_average_rating, user_points

main_bp = Blueprint('main', __name__)


@main_bp.route("/", endpoint='index')
def index():
    """
    首頁路由。
    收集並傳遞以下資料給模板：
    - stats: 平台整體統計（使用者數、技能數、媒合數、評價數）
    - popular_skills: 最新上架的熱門技能（最多 4 筆）
    - leaderboard: 排行榜（依積分、完成數、評分排序，取前 5 名）
    - active_chats: 已登入使用者的活躍聊天室清單（最多 4 個）
    """
    # 計算平台整體統計數字，顯示於首頁橫幅
    stats = {
        "users": User.query.count(),
        "skills": Skill.query.filter_by(status="open", is_active=True).count(),
        "matches": Match.query.filter(Match.status.in_(["accepted", "completed", "pending"])).count(),
        "reviews": Review.query.count(),
    }

    # 取得最新上架的技能（限 4 筆，顯示於首頁技能區塊）
    popular_skills = Skill.query.filter_by(status="open", is_active=True).order_by(Skill.created_at.desc()).limit(4).all()

    # 建立排行榜：計算每位使用者的積分、完成數、平均評分
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

    # 排序規則：積分 → 完成數 → 平均評分 → 較新帳號（id 越小越舊，所以用負號讓新帳號排後）
    leaderboard.sort(
        key=lambda item: (
            item["points"],
            item["completed_matches"],
            item["average_rating"],
            -item["user"].id,
        ),
        reverse=True,
    )
    # 只取前 5 名
    leaderboard = leaderboard[:5]

    # 取得已登入使用者的活躍聊天室（accepted 或 completed 的媒合），限制 4 個
    active_chats = []
    if current_user.is_authenticated:
        matches = Match.query.filter(
            db.or_(
                db.and_(Match.requester_id == current_user.id, Match.status.in_(["accepted", "completed"])),
                db.and_(Match.receiver_id == current_user.id, Match.status.in_(["accepted", "completed"]))
            )
        ).order_by(Match.updated_at.desc()).limit(4).all()

        for match in matches:
            # 判斷對方是申請方還是被申請方
            if match.requester_id == current_user.id:
                other_user = match.receiver
            else:
                other_user = match.requester

            # 取得此聊天室的最後一則訊息（用於預覽）
            last_message = Message.query.filter_by(match_id=match.id).order_by(Message.created_at.desc()).first()

            # 計算對方傳給我的未讀訊息數（用於顯示紅點提示）
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
    """
    管理員入口路由。
    若已登入且為管理員（admin / super_admin），導向管理後台；
    否則顯示無權限錯誤並導回首頁。
    """
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    if current_user.role in ["admin", "super_admin"]:
        return redirect(url_for("admin.dashboard"))

    flash("你沒有權限進入管理後台。", "error")
    return redirect(url_for("main.index"))
