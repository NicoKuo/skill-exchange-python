from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from functools import wraps

from models import User, Skill

admin_bp = Blueprint('admin', __name__)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route("/admin", endpoint='admin')
@login_required
@admin_required
def admin():
    users = User.query.order_by(User.created_at.desc()).all()
    skills = Skill.query.order_by(Skill.created_at.desc()).all()

    return render_template("admin.html", users=users, skills=skills)
