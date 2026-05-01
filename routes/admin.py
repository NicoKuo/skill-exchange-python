# 管理後台 - 會員、技能、媒合與管理者管理
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from models import db, Match, Skill, User

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def super_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
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


@admin_bp.route('/entry', endpoint='entry')
def entry():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    if current_user.role in ['admin', 'super_admin']:
        return redirect(url_for('admin.dashboard'))

    flash('你沒有權限進入管理後台。', 'error')
    return redirect(url_for('main.index'))


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


@admin_bp.route('/managers', methods=['GET', 'POST'], endpoint='managers')
@login_required
@admin_required
@super_admin_required
def managers():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not name or not email or len(password) < 6:
            flash('姓名、Email 與密碼必填，且密碼至少 6 碼。', 'error')
        elif User.query.filter_by(email=email).first():
            flash('這個 Email 已存在。', 'error')
        else:
            manager = User(name=name, email=email, role='admin', bio='')
            manager.password_hash = generate_password_hash(password)
            db.session.add(manager)
            db.session.commit()
            flash('已新增管理者。', 'success')
            return redirect(url_for('admin.managers'))

    managers = User.query.filter(User.role.in_(['admin', 'super_admin'])).order_by(User.created_at.desc()).all()
    return render_template('admin/managers.html', managers=managers, stats=_admin_counts())


@admin_bp.route('/managers/<int:user_id>/delete', methods=['POST'], endpoint='delete_manager')
@login_required
@admin_required
@super_admin_required
def delete_manager(user_id):
    manager = User.query.get_or_404(user_id)

    if manager.id == current_user.id:
        flash('不能刪除自己。', 'error')
        return redirect(url_for('admin.managers'))

    if manager.role != 'admin':
        flash('只能刪除一般管理者，不能刪除 super_admin。', 'error')
        return redirect(url_for('admin.managers'))

    db.session.delete(manager)
    db.session.commit()
    flash('已刪除管理者。', 'success')
    return redirect(url_for('admin.managers'))
