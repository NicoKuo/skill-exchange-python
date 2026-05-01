# 管理後台 - 會員、技能與媒合管理
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, Match, Skill, User

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def _admin_counts():
    return {
        'users': User.query.count(),
        'skills': Skill.query.count(),
        'matches': Match.query.count(),
        'chats': Match.query.filter(Match.status.in_(['accepted', 'completed'])).count(),
    }


@admin_bp.route('/', endpoint='dashboard')
@login_required
@admin_required
def dashboard():
    return render_template('admin/dashboard.html', stats=_admin_counts())


@admin_bp.route('/users', endpoint='users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, stats=_admin_counts())


@admin_bp.route('/skills', endpoint='skills')
@login_required
@admin_required
def skills():
    skills = Skill.query.order_by(Skill.created_at.desc()).all()
    return render_template('admin/skills.html', skills=skills, stats=_admin_counts())


@admin_bp.route('/skills/<int:skill_id>/action', methods=['POST'], endpoint='skill_action')
@login_required
@admin_required
def skill_action(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    action = request.form.get('action')

    if action == 'take_down':
        skill.status = 'closed'
        db.session.commit()
        flash('技能已下架。', 'success')
    elif action == 'delete':
        if Match.query.filter_by(skill_id=skill.id).count() == 0:
            db.session.delete(skill)
            db.session.commit()
            flash('技能已刪除。', 'success')
        else:
            skill.status = 'closed'
            db.session.commit()
            flash('此技能已有媒合紀錄，已改為下架。', 'warning')
    else:
        flash('未知的技能操作。', 'error')

    return redirect(url_for('admin.skills'))


@admin_bp.route('/matches', endpoint='matches')
@login_required
@admin_required
def matches():
    matches = Match.query.order_by(Match.updated_at.desc()).all()
    return render_template('admin/matches.html', matches=matches, stats=_admin_counts())
