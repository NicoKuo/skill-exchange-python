# routes/notifications.py: 通知中心路由
# 功能：顯示使用者的所有通知，並在查看時自動標記為已讀
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from functools import wraps
from flask import abort

from models import Notification

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route("/notifications", endpoint='notifications')
@login_required
def notifications():
    """
    通知中心路由。需登入才可存取。
    取得目前使用者的所有通知（依建立時間倒序），
    顯示頁面的同時將所有未讀通知標記為已讀。
    """
    # 取得所有通知，新的在上
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()

    # 將所有通知標記為已讀（使用者進入頁面即視為已讀）
    for item in items:
        item.is_read = True

    from models import db
    db.session.commit()

    return render_template("notifications.html", items=items)
