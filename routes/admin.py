# 管理後台 - 會員、技能、媒合與管理者管理
from collections import Counter
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, Match, Skill, User, ActivityLog, Report
from utils import format_taiwan_time

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
    }


def _completed_exchange_counts():
    counts = Counter()
    completed_matches = Match.query.filter(Match.status == 'completed').with_entities(
        Match.requester_id,
        Match.receiver_id,
    ).all()

    for requester_id, receiver_id in completed_matches:
        counts[requester_id] += 1
        counts[receiver_id] += 1

    return counts


def _recent_activities(limit=8):
    activities = []

    for user in User.query.order_by(User.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '新會員',
            'tag_class': 'tag-green',
            'title': user.name,
            'description': user.email,
            'created_at': user.created_at,
        })

    for skill in Skill.query.order_by(Skill.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '新技能',
            'tag_class': 'tag-teal',
            'title': skill.title,
            'description': f'{skill.user.name} 已上架技能',
            'created_at': skill.created_at,
        })

    for match in Match.query.order_by(Match.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '交換申請',
            'tag_class': 'tag-yellow',
            'title': match.skill.title,
            'description': f'{match.requester.name} → {match.receiver.name} · {match.status}',
            'created_at': match.created_at,
        })

    activities.sort(
        key=lambda item: item['created_at'] or datetime.min,
        reverse=True,
    )

    for item in activities:
        item['created_at_text'] = format_taiwan_time(item['created_at'], '%Y-%m-%d %H:%M')

    return activities[:limit]


@admin_bp.route('/entry', endpoint='entry')
def entry():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    if current_user.role in ['admin', 'super_admin']:
        return redirect(url_for('admin.dashboard'))

    flash('你沒有權限進入管理後台。', 'error')
    return redirect(url_for('main.index'))


@admin_bp.route('/', endpoint='dashboard')
@login_required
@admin_required
def dashboard():
    return render_template(
        'admin/dashboard.html',
        current_page='dashboard',
        stats=_admin_counts(),
        recent_activities=_recent_activities(),
    )


@admin_bp.route('/users', endpoint='users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    completed_counts = _completed_exchange_counts()
    manageable_user_ids = set()

    for user in users:
        if user.id == current_user.id or user.role == 'super_admin':
            continue

        if current_user.role == 'super_admin' and user.role in {'user', 'admin'}:
            manageable_user_ids.add(user.id)
        elif current_user.role == 'admin' and user.role == 'user':
            manageable_user_ids.add(user.id)

    return render_template(
        'admin/users.html',
        current_page='users',
        users=users,
        stats=_admin_counts(),
        completed_counts=completed_counts,
        manageable_user_ids=manageable_user_ids,
    )


@admin_bp.route('/users/<int:user_id>/status', methods=['POST'], endpoint='update_user_status')
@login_required
@admin_required
def update_user_status(user_id):
    target_user = User.query.get_or_404(user_id)
    new_status = request.form.get('status', '').strip()
    allowed_statuses = {'active', 'suspended', 'blocked'}

    if new_status not in allowed_statuses:
        abort(400)

    if target_user.id == current_user.id:
        abort(403)

    if target_user.role == 'super_admin':
        abort(403)

    if current_user.role == 'admin' and target_user.role != 'user':
        abort(403)

    if current_user.role == 'super_admin' and target_user.role not in {'user', 'admin'}:
        abort(403)

    if target_user.status == new_status:
        flash('帳號狀態沒有變更。', 'warning')
        return redirect(url_for('admin.users'))

    target_user.status = new_status
    db.session.commit()
    # record admin action
    try:
        log = ActivityLog(user_id=current_user.id, action='admin_update_user_status', detail=f'target_user_id={target_user.id}|new_status={new_status}', ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    flash('使用者狀態已更新。', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/skills', endpoint='skills')
@login_required
@admin_required
def skills():
    skills = Skill.query.order_by(Skill.created_at.desc()).all()
    return render_template('admin/skills.html', current_page='skills', skills=skills, stats=_admin_counts())


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
    return render_template('admin/matches.html', current_page='matches', matches=matches, stats=_admin_counts())


@admin_bp.route('/managers', methods=['GET', 'POST'], endpoint='managers')
@login_required
@admin_required
@super_admin_required
def managers():
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        users = User.query.filter(
            db.or_(
                User.name.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        ).order_by(User.created_at.desc()).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()
    
    # Separate managers and regular users for display
    managers_list = [u for u in users if u.role in ['admin', 'super_admin']]
    regular_users = [u for u in users if u.role == 'user']

    return render_template(
        'admin/managers.html',
        current_page='managers',
        managers=managers_list,
        users=regular_users,
        search_query=search_query,
        stats=_admin_counts()
    )


@admin_bp.route('/activity', endpoint='activity')
@login_required
@admin_required
def activity():
    # show all activity logs
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    # eager load users
    user_ids = [l.user_id for l in logs]
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return render_template('admin/activity.html', logs=logs, users=users, stats=_admin_counts())


@admin_bp.route('/users/<int:user_id>/activity', endpoint='user_activity')
@login_required
@admin_required
def user_activity(user_id):
    user = User.query.get_or_404(user_id)
    logs = ActivityLog.query.filter_by(user_id=user.id).order_by(ActivityLog.created_at.desc()).all()
    return render_template('admin/user_activity.html', user=user, logs=logs, stats=_admin_counts())


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


@admin_bp.route('/managers/<int:user_id>/promote', methods=['POST'], endpoint='promote_manager')
@login_required
@admin_required
@super_admin_required
def promote_manager(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('不能修改自己的角色。', 'error')
        return redirect(url_for('admin.managers'))
    
    if user.status != 'active':
        flash('停權或封鎖中的使用者不能設為管理者。', 'error')
        return redirect(url_for('admin.managers'))
    
    if user.role in ['admin', 'super_admin']:
        flash('此使用者已經是管理者。', 'warning')
        return redirect(url_for('admin.managers'))
    
    user.role = 'admin'
    db.session.commit()
    
    try:
        log = ActivityLog(user_id=current_user.id, action='promote_user_to_admin', detail=f'target_user_id={user.id}', ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    flash(f'已將 {user.name} 升級為管理者。', 'success')
    return redirect(url_for('admin.managers'))


@admin_bp.route('/reports', endpoint='reports')
@login_required
@admin_required
def reports():
    status_filter = request.args.get('status', 'all')
    
    query = Report.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    reports_list = query.order_by(Report.created_at.desc()).all()
    
    return render_template(
        'admin/reports.html',
        current_page='reports',
        reports=reports_list,
        status_filter=status_filter,
        stats=_admin_counts()
    )


@admin_bp.route('/reports/<int:report_id>', endpoint='report_detail')
@login_required
@admin_required
def report_detail(report_id):
    report = Report.query.get_or_404(report_id)
    return render_template(
        'admin/report_detail.html',
        report=report,
        stats=_admin_counts()
    )


@admin_bp.route('/reports/<int:report_id>/update', methods=['POST'], endpoint='update_report')
@login_required
@admin_required
def update_report(report_id):
    report = Report.query.get_or_404(report_id)
    
    new_status = request.form.get('status', '').strip()
    admin_note = request.form.get('admin_note', '').strip()
    
    if new_status not in ['pending', 'reviewed', 'rejected', 'resolved']:
        abort(400)
    
    report.status = new_status
    report.admin_note = admin_note
    report.reviewed_by = current_user.id
    report.updated_at = datetime.utcnow()
    db.session.commit()
    
    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='update_report',
            detail=f'report_id={report.id}|new_status={new_status}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    flash('檢舉已更新。', 'success')
    return redirect(url_for('admin.report_detail', report_id=report_id))
