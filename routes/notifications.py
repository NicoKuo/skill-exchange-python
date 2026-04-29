from flask import Blueprint, render_template
from flask_login import login_required, current_user
from functools import wraps
from flask import abort

from models import Notification

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route("/notifications", endpoint='notifications')
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()

    for item in items:
        item.is_read = True

    from models import db
    db.session.commit()

    return render_template("notifications.html", items=items)
