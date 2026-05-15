# 管理後台 - 會員、技能、媒合與管理者管理
from collections import Counter
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, Match, Skill, User, ActivityLog, Notification, Report
from utils import format_taiwan_time

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


REPORT_FEEDBACK_MESSAGES = {
    'reviewed': '你的檢舉已被管理員受理，我們會進一步審查。',
    'rejected': '你的檢舉經審查後未發現明確違規。',
    'resolved': '你的檢舉已完成處理，感謝你的回報。',
    'punished': '你檢舉的內容已確認違規，系統已採取處置。',
}

ACCOUNT_ACTION_MESSAGES = {
    'active': '你的帳號限制已解除，目前可正常使用。',
    'suspended': '你的帳號因違反平台規範已被停權。',
    'banned': '你的帳號因嚴重違規已被封禁。',
}


def _normalize_user_status(status):
    status = (status or '').strip()
    return 'banned' if status == 'blocked' else status


def _append_feedback_text(base_text, feedback):
    feedback = (feedback or '').strip()
    if not feedback:
        return base_text

    suffix = f' 處理說明：{feedback}'
    max_content_length = 255
    if len(base_text) + len(suffix) <= max_content_length:
        return f'{base_text}{suffix}'

    available = max_content_length - len(base_text) - len(' 處理說明：') - 3
    if available <= 0:
        return f'{base_text[:max_content_length - 3]}...'

    return f'{base_text} 處理說明：{feedback[:available]}...'


def _build_report_feedback_message(status, feedback=''):
    base_text = REPORT_FEEDBACK_MESSAGES.get(status)
    if not base_text:
        return ''
    return _append_feedback_text(base_text, feedback)


def _build_account_action_message(status, feedback=''):
    base_text = ACCOUNT_ACTION_MESSAGES.get(status)
    if not base_text:
        return ''
    return _append_feedback_text(base_text, feedback)


def _can_manage_user_status(target_user):
    if not target_user:
        return False

    if current_user.role == 'super_admin':
        return True

    return current_user.role == 'admin' and target_user.role == 'user'


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
    new_status = _normalize_user_status(request.form.get('status', ''))
    allowed_statuses = {'active', 'suspended', 'banned'}

    if new_status not in allowed_statuses:
        abort(400)

    if target_user.id == current_user.id and new_status in {'suspended', 'banned'}:
        abort(403)

    if not _can_manage_user_status(target_user):
        abort(403)

    current_status = _normalize_user_status(target_user.status)
    if current_status == new_status:
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


@admin_bp.route('/skills/<int:skill_id>/deactivate', methods=['POST'], endpoint='deactivate_skill')
@login_required
@admin_required
def deactivate_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)

    if not skill.is_active:
        flash('這個技能已經是下架狀態。', 'warning')
        return redirect(url_for('admin.skills'))

    skill.is_active = False
    db.session.commit()
    flash('技能已下架。', 'success')

    return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/<int:skill_id>/delete', methods=['POST'], endpoint='delete_skill')
@login_required
@admin_required
def delete_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)

    has_matches = Match.query.filter_by(skill_id=skill.id).count() > 0
    has_reports = Report.query.filter_by(skill_id=skill.id).count() > 0

    if has_matches or has_reports:
        skill.is_active = False
        db.session.commit()
        flash('此技能已有關聯資料，已改為下架，無法直接刪除。', 'warning')
        return redirect(url_for('admin.skills'))

    db.session.delete(skill)
    db.session.commit()
    flash('技能已刪除。', 'success')

    return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/<int:skill_id>/action', methods=['POST'], endpoint='skill_action')
@login_required
@admin_required
def skill_action(skill_id):
    action = request.form.get('action')
    if action == 'take_down':
        return deactivate_skill(skill_id)
    if action == 'delete':
        return delete_skill(skill_id)
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

    old_status = report.status
    new_status = request.form.get('status', '').strip()
    admin_note = request.form.get('admin_note', '').strip()
    feedback = request.form.get('feedback', '').strip()

    if new_status not in ['pending', 'reviewed', 'rejected', 'resolved', 'punished']:
        abort(400)

    status_changed = old_status != new_status

    report.status = new_status
    report.admin_note = admin_note
    report.feedback = feedback
    report.reviewed_by = current_user.id
    report.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('檢舉更新失敗，請稍後再試。', 'error')
        return redirect(url_for('admin.report_detail', report_id=report_id))

    if status_changed:
        notifications = []
        reporter_message = _build_report_feedback_message(new_status, feedback)

        if reporter_message:
            notifications.append(
                Notification(
                    user_id=report.reporter_id,
                    type='report_feedback',
                    content=reporter_message,
                    related_id=report.id,
                )
            )

        if new_status == 'punished' and report.reported_user_id and report.reported_user_id != report.reporter_id:
            punished_target_message = _append_feedback_text(
                '你收到一則檢舉審核結果：經管理員審查確認違規，系統已對你的帳號或內容採取處置。',
                feedback,
            )
            notifications.append(
                Notification(
                    user_id=report.reported_user_id,
                    type='report_feedback',
                    content=punished_target_message,
                    related_id=report.id,
                )
            )

        if notifications:
            try:
                db.session.add_all(notifications)
                db.session.commit()
            except Exception:
                db.session.rollback()

    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='update_report',
            detail=f'report_id={report.id}|old_status={old_status}|new_status={new_status}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    flash('檢舉已更新。', 'success')
    return redirect(url_for('admin.report_detail', report_id=report_id))


@admin_bp.route('/reports/<int:report_id>/account-action', methods=['POST'], endpoint='account_action')
@login_required
@admin_required
def account_action(report_id):
    report = Report.query.get_or_404(report_id)
    reported_user = report.reported_user

    if not reported_user:
        abort(400)

    requested_account_status = _normalize_user_status(request.form.get('account_status', ''))
    action_reason = request.form.get('action_reason', '').strip()

    if requested_account_status not in {'active', 'suspended', 'banned'}:
        flash('帳號狀態值不正確。', 'error')
        return redirect(url_for('admin.report_detail', report_id=report_id))

    if not _can_manage_user_status(reported_user):
        abort(403)

    if reported_user.id == current_user.id and requested_account_status in {'suspended', 'banned'}:
        abort(403)

    current_account_status = _normalize_user_status(reported_user.status)
    if current_account_status == requested_account_status:
        flash('帳號狀態沒有變更。', 'warning')
        return redirect(url_for('admin.report_detail', report_id=report_id))

    reported_user.status = requested_account_status

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('帳號處置失敗，請稍後再試。', 'error')
        return redirect(url_for('admin.report_detail', report_id=report_id))

    account_message = _build_account_action_message(requested_account_status, action_reason)
    if account_message:
        try:
            db.session.add(
                Notification(
                    user_id=reported_user.id,
                    type='account_action',
                    content=account_message,
                    related_id=report.id,
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='account_action',
            detail=f'report_id={report.id}|target_user_id={reported_user.id}|new_status={requested_account_status}',
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    flash('帳號處置已更新。', 'success')
    return redirect(url_for('admin.report_detail', report_id=report_id))
