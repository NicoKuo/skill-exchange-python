# routes/admin.py: 管理後台路由
# 功能：使用者管理、技能審核、媒合監督、管理員管理、活動日誌、檢舉處理
# 存取控制：admin（一般管理員）可管理一般使用者；super_admin 可管理管理員
from collections import Counter
from datetime import datetime
from sqlalchemy import and_, or_
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, Match, Skill, User, ActivityLog, Notification, Report, Message, Review
from utils import format_taiwan_time
from utils.helpers import user_active_skill_count, can_user_add_skill

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# 檢舉狀態對應的回饋通知文字（發送給檢舉人）
REPORT_FEEDBACK_MESSAGES = {
    'reviewed': '你的檢舉已被管理員受理，我們會進一步審查。',
    'rejected': '你的檢舉經審查後未發現明確違規。',
    'resolved': '你的檢舉已完成處理，感謝你的回報。',
    'punished': '你檢舉的內容已確認違規，系統已採取處置。',
}

# 帳號處置狀態對應的通知文字（發送給被處置的使用者）
ACCOUNT_ACTION_MESSAGES = {
    'active': '你的帳號限制已解除，目前可正常使用。',
    'suspended': '你的帳號因違反平台規範已被停權。',
    'banned': '你的帳號因嚴重違規已被封禁。',
}


def _normalize_user_status(status):
    """將帳號狀態規範化：將舊版的 'blocked' 統一轉換為 'banned'。"""
    status = (status or '').strip()
    return 'banned' if status == 'blocked' else status


def _append_feedback_text(base_text, feedback):
    """
    將管理員的補充說明（feedback）附加到通知文字後方。
    若總長度超過 255 字元上限，自動截斷並加上省略號。
    """
    feedback = (feedback or '').strip()
    if not feedback:
        return base_text

    suffix = f' 處理說明：{feedback}'
    max_content_length = 255
    if len(base_text) + len(suffix) <= max_content_length:
        return f'{base_text}{suffix}'

    # 計算 feedback 可用的最大長度
    available = max_content_length - len(base_text) - len(' 處理說明：') - 3
    if available <= 0:
        return f'{base_text[:max_content_length - 3]}...'

    return f'{base_text} 處理說明：{feedback[:available]}...'


def _build_report_feedback_message(status, feedback=''):
    """
    建立要發送給檢舉人的通知訊息。
    根據檢舉狀態取得對應文字，並附加管理員說明。
    """
    base_text = REPORT_FEEDBACK_MESSAGES.get(status)
    if not base_text:
        return ''
    return _append_feedback_text(base_text, feedback)


def _build_account_action_message(status, feedback=''):
    """
    建立要發送給被處置使用者的通知訊息。
    根據新帳號狀態取得對應文字，並附加處置說明。
    """
    base_text = ACCOUNT_ACTION_MESSAGES.get(status)
    if not base_text:
        return ''
    return _append_feedback_text(base_text, feedback)


def _can_manage_user_status(target_user):
    """
    判斷目前管理員是否有權限修改指定使用者的帳號狀態。
    規則：
    - super_admin 可以管理所有人
    - admin 只能管理一般 user（無法管理 admin 或 super_admin）
    """
    if not target_user:
        return False

    if current_user.role == 'super_admin':
        return True

    return current_user.role == 'admin' and target_user.role == 'user'


def super_admin_required(fn):
    """
    裝飾器：限制只有 super_admin 才能存取的路由。
    非 super_admin 存取時回傳 403 Forbidden。
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    """
    裝飾器：限制只有 admin 或 super_admin 才能存取的路由。
    一般使用者存取時回傳 403 Forbidden。
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def _admin_counts():
    """取得後台統計數字：使用者總數、技能總數、媒合總數。"""
    return {
        'users': User.query.count(),
        'skills': Skill.query.count(),
        'matches': Match.query.count(),
    }


def _completed_exchange_counts():
    """
    計算每位使用者的已完成交換次數。
    申請方和被申請方都各計一次，回傳 {user_id: 次數} 的 Counter 物件。
    """
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
    """
    取得最近的平台活動列表（用於後台儀表板）。
    混合新會員、新技能、新媒合三種類型的記錄，依時間倒序排列後取前 limit 筆。
    """
    activities = []

    # 新會員記錄
    for user in User.query.order_by(User.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '新會員',
            'tag_class': 'tag-green',
            'title': user.name,
            'description': user.email,
            'created_at': user.created_at,
        })

    # 新技能記錄
    for skill in Skill.query.order_by(Skill.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '新技能',
            'tag_class': 'tag-teal',
            'title': skill.title,
            'description': f'{skill.user.name} 已上架技能',
            'created_at': skill.created_at,
        })

    # 新媒合記錄
    for match in Match.query.order_by(Match.created_at.desc()).limit(limit).all():
        activities.append({
            'kind': '交換申請',
            'tag_class': 'tag-yellow',
            'title': match.skill.title,
            'description': f'{match.requester.name} → {match.receiver.name} · {match.status}',
            'created_at': match.created_at,
        })

    # 依時間倒序排列（None 時間排最後）
    activities.sort(
        key=lambda item: item['created_at'] or datetime.min,
        reverse=True,
    )

    # 將時間格式化為台灣時區字串
    for item in activities:
        item['created_at_text'] = format_taiwan_time(item['created_at'], '%Y-%m-%d %H:%M')

    return activities[:limit]


@admin_bp.route('/entry', endpoint='entry')
def entry():
    """
    管理後台入口路由。
    已登入的管理員自動導向後台儀表板，
    非管理員顯示無權限錯誤並導回首頁。
    """
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
    """
    後台儀表板路由。需管理員以上權限。
    顯示平台統計數字和最近的活動記錄。
    """
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
    """
    使用者管理列表路由。需管理員以上權限。
    顯示所有使用者，並計算各使用者的已完成交換次數。
    manageable_user_ids：目前管理員有權限修改狀態的使用者 ID 集合
    （super_admin 可管理 user 和 admin；admin 只能管理 user）。
    """
    users = User.query.order_by(User.created_at.desc()).all()
    completed_counts = _completed_exchange_counts()
    manageable_user_ids = set()

    for user in users:
        # 不能管理自己，也不能管理 super_admin
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
    """
    更新使用者帳號狀態路由（POST）。需管理員以上權限。
    允許的狀態：active（正常）/ suspended（停權）/ banned（封禁）。
    安全限制：
    - 不能將自己停權或封禁
    - admin 不能修改 admin 或 super_admin 的狀態
    - 若狀態未變更，顯示警告訊息
    操作記錄會寫入活動日誌。
    """
    target_user = User.query.get_or_404(user_id)
    new_status = _normalize_user_status(request.form.get('status', ''))
    allowed_statuses = {'active', 'suspended', 'banned'}

    # 驗證狀態值
    if new_status not in allowed_statuses:
        abort(400)

    # 不能將自己的帳號停權或封禁
    if target_user.id == current_user.id and new_status in {'suspended', 'banned'}:
        abort(403)

    # 權限檢查
    if not _can_manage_user_status(target_user):
        abort(403)

    # 若狀態沒有變更，不需要更新
    current_status = _normalize_user_status(target_user.status)
    if current_status == new_status:
        flash('帳號狀態沒有變更。', 'warning')
        return redirect(url_for('admin.users'))

    target_user.status = new_status
    db.session.commit()
    # 記錄管理員操作日誌
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
    """
    技能審核列表路由。需管理員以上權限。
    
    顯示內容：
    - 所有技能：活躍、已下架、已刪除（軟刪除）
    - 前台使用者只能搜尋到「活躍」技能（is_active=True 且 status='open'）
    - 已下架的技能（is_active=False）前台搜尋不到
    
    操作：
    - 下架：將技能標記為已下架（is_active=False），前台看不到，但資料保留
    - 刪除：若無關聯資料則永久刪除；若有關聯資料則改為下架
    """
    skills_list = Skill.query.order_by(Skill.created_at.desc()).all()
    
    # 為每個技能計算發布者的上架技能數量（用於判斷是否可重新上架）
    skill_owner_active_counts = {}
    for skill in skills_list:
        if skill.user_id not in skill_owner_active_counts:
            skill_owner_active_counts[skill.user_id] = user_active_skill_count(skill.user_id)
    
    return render_template(
        'admin/skills.html',
        current_page='skills',
        skills=skills_list,
        stats=_admin_counts(),
        skill_owner_active_counts=skill_owner_active_counts
    )


@admin_bp.route('/skills/<int:skill_id>/deactivate', methods=['POST'], endpoint='deactivate_skill')
@login_required
@admin_required
def deactivate_skill(skill_id):
    """
    技能下架路由（管理員操作）。需管理員以上權限。
    將技能標記為下架（is_active=False），已下架的技能不允許重複操作。
    """
    skill = Skill.query.get_or_404(skill_id)

    if not skill.is_active:
        flash('這個技能已經是下架狀態。', 'warning')
        return redirect(url_for('admin.skills'))

    skill.is_active = False
    db.session.commit()
    flash('技能已下架。', 'success')

    return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/<int:skill_id>/restore', methods=['POST'], endpoint='restore_skill')
@login_required
@admin_required
def restore_skill(skill_id):
    """
    技能重新上架路由（管理員操作）。需管理員以上權限。
    將已下架的技能重新上架（is_active=True）。
    會檢查該技能發布者是否已達上架數量上限。
    """
    try:
        skill = Skill.query.get_or_404(skill_id)

        # 如果已經是上架狀態，提示使用者但不報錯
        if skill.is_active:
            flash('此技能已經是上架狀態。', 'warning')
            return redirect(url_for('admin.skills'))

        # 檢查技能發布者是否已達上架上限
        if not can_user_add_skill(skill.user_id):
            flash('此使用者目前已有 3 個上架技能，無法重新上架。', 'error')
            return redirect(url_for('admin.skills'))

        # 重新上架（恢復 is_active 為 True）
        skill.is_active = True
        db.session.commit()
        flash('技能已重新上架。', 'success')

        return redirect(url_for('admin.skills'))

    except Exception as e:
        db.session.rollback()
        flash(f'重新上架技能時發生錯誤：{str(e)}', 'error')
        return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/<int:skill_id>/delete', methods=['POST'], endpoint='delete_skill')
@login_required
@admin_required
def delete_skill(skill_id):
    """
    技能刪除路由（管理員操作）。需管理員以上權限。
    
    刪除邏輯：
    1. 若技能有關聯的媒合或檢舉記錄，不可直接刪除（改為下架）
    2. 若技能無關聯資料，執行硬刪除（從資料庫永久刪除）
    3. 被下架的技能前台搜尋不到（is_active=False）
    
    已下架技能仍會在後台顯示供管理員檢查。
    """
    skill = Skill.query.get_or_404(skill_id)

    try:
        # 檢查是否有關聯資料（有則軟刪除，不可硬刪除）
        has_matches = Match.query.filter_by(skill_id=skill.id).count() > 0
        has_reports = Report.query.filter_by(skill_id=skill.id).count() > 0
        
        # 統計關聯數量，用於反饋訊息
        match_count = Match.query.filter_by(skill_id=skill.id).count()
        report_count = Report.query.filter_by(skill_id=skill.id).count()

        if has_matches or has_reports:
            # 有關聯資料 → 軟刪除（改為下架）
            skill.is_active = False
            db.session.commit()
            
            # 構建詳細訊息
            details = []
            if match_count > 0:
                details.append(f'{match_count} 筆媒合')
            if report_count > 0:
                details.append(f'{report_count} 筆檢舉')
            detail_msg = '、'.join(details) if details else '相關'
            
            flash(f'此技能已有 {detail_msg} 紀錄，已改為下架。前台使用者搜尋不到，後台仍可查看。', 'warning')
            return redirect(url_for('admin.skills'))

        # 無關聯資料 → 硬刪除
        skill_title = skill.title  # 保存技能名稱用於 flash
        db.session.delete(skill)
        db.session.commit()
        flash(f'技能「{skill_title}」已永久刪除。', 'success')

        return redirect(url_for('admin.skills'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'刪除技能時發生錯誤：{str(e)}', 'error')
        return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/<int:skill_id>/action', methods=['POST'], endpoint='skill_action')
@login_required
@admin_required
def skill_action(skill_id):
    """
    技能操作路由：根據 action 參數分派到對應的操作。
    action='take_down'：下架技能
    action='delete'：刪除技能
    """
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
    """
    媒合監督列表路由。需管理員以上權限。
    支援篩選：狀態、技能關鍵字、使用者名稱/email、時間區間。
    顯示統計卡片和媒合記錄表，避免 N+1 查詢。
    """
    # 取得篩選參數
    status_filter = request.args.get('status', 'all').strip()
    skill_keyword = request.args.get('skill_keyword', '').strip()
    user_keyword = request.args.get('user_keyword', '').strip()
    date_from_str = request.args.get('date_from', '').strip()
    date_to_str = request.args.get('date_to', '').strip()
    
    # 構建查詢
    query = Match.query.outerjoin(Skill).outerjoin(User, Match.requester_id == User.id)
    
    # 狀態篩選
    if status_filter != 'all':
        query = query.filter(Match.status == status_filter)
    
    # 技能關鍵字篩選
    if skill_keyword:
        query = query.filter(Skill.title.ilike(f'%{skill_keyword}%'))
    
    # 使用者名稱或 Email 篩選
    if user_keyword:
        query = query.filter(
            or_(
                User.name.ilike(f'%{user_keyword}%'),
                User.email.ilike(f'%{user_keyword}%')
            )
        )
    
    # 時間區間篩選
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            query = query.filter(Match.created_at >= date_from)
        except ValueError:
            pass
    
    if date_to_str:
        try:
            from datetime import timedelta
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Match.created_at < date_to)
        except ValueError:
            pass
    
    # 排序並執行查詢
    matches_list = query.order_by(Match.updated_at.desc()).all()
    
    # 計算統計數字
    all_matches_count = Match.query.count()
    pending_count = Match.query.filter_by(status='pending').count()
    accepted_count = Match.query.filter_by(status='accepted').count()
    completed_count = Match.query.filter_by(status='completed').count()
    cancelled_rejected_count = Match.query.filter(
        Match.status.in_(['cancelled', 'rejected'])
    ).count()
    
    stats_data = {
        'all': all_matches_count,
        'pending': pending_count,
        'accepted': accepted_count,
        'completed': completed_count,
        'cancelled_rejected': cancelled_rejected_count,
    }
    
    return render_template(
        'admin/matches.html',
        current_page='matches',
        matches=matches_list,
        stats=_admin_counts(),
        match_stats=stats_data,
        status_filter=status_filter,
        skill_keyword=skill_keyword,
        user_keyword=user_keyword,
        date_from=date_from_str,
        date_to=date_to_str,
    )


@admin_bp.route('/matches/<int:match_id>', endpoint='match_detail')
@login_required
@admin_required
def match_detail(match_id):
    """
    媒合詳情路由。需管理員以上權限。
    顯示媒合的完整資訊，包含技能、雙方使用者、聊天記錄、評價、檢舉等相關資料。
    """
    match = Match.query.get_or_404(match_id)
    
    # 取得相關資料
    skill = match.skill
    requester = match.requester
    receiver = match.receiver
    
    # 取得該媒合的所有聊天訊息
    messages = Message.query.filter_by(match_id=match.id).order_by(Message.created_at.asc()).all()
    
    # 取得該媒合的所有評價
    reviews = Review.query.filter_by(match_id=match.id).all()
    
    # 取得該媒合的所有檢舉
    reports = Report.query.filter_by(match_id=match.id).all()
    
    return render_template(
        'admin/match_detail.html',
        match=match,
        skill=skill,
        requester=requester,
        receiver=receiver,
        messages=messages,
        reviews=reviews,
        reports=reports,
        stats=_admin_counts(),
    )


@admin_bp.route('/managers', methods=['GET', 'POST'], endpoint='managers')
@login_required
@admin_required
@super_admin_required
def managers():
    """
    管理員管理列表路由。只有 super_admin 才可存取。
    顯示所有管理員和一般使用者的清單，支援姓名和 Email 搜尋。
    從此頁面可以升級使用者為管理員或刪除管理員。
    """
    search_query = request.args.get('search', '').strip()

    if search_query:
        # 模糊搜尋姓名或 Email
        users = User.query.filter(
            db.or_(
                User.name.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        ).order_by(User.created_at.desc()).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()

    # 分離管理員和一般使用者以分區顯示
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
    """
    活動日誌路由。需管理員以上權限。
    顯示最近 200 筆活動記錄，並預先載入相關使用者資料（避免 N+1 查詢）。
    """
    # 取得最近 200 筆日誌，依時間倒序
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    # 批次載入相關使用者，減少資料庫查詢次數
    user_ids = [l.user_id for l in logs]
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return render_template('admin/activity.html', logs=logs, users=users, stats=_admin_counts())


@admin_bp.route('/users/<int:user_id>/activity', endpoint='user_activity')
@login_required
@admin_required
def user_activity(user_id):
    """
    個別使用者活動日誌路由。需管理員以上權限。
    顯示指定使用者的所有活動記錄（登入、上架技能、建立媒合等），依時間倒序。
    """
    user = User.query.get_or_404(user_id)
    logs = ActivityLog.query.filter_by(user_id=user.id).order_by(ActivityLog.created_at.desc()).all()
    return render_template('admin/user_activity.html', user=user, logs=logs, stats=_admin_counts())


@admin_bp.route('/managers/<int:user_id>/delete', methods=['POST'], endpoint='delete_manager')
@login_required
@admin_required
@super_admin_required
def delete_manager(user_id):
    """
    刪除管理員路由。只有 super_admin 才可存取。
    安全限制：
    - 不能刪除自己
    - 只能刪除一般 admin，不能刪除 super_admin
    """
    manager = User.query.get_or_404(user_id)

    # 不能刪除自己
    if manager.id == current_user.id:
        flash('不能刪除自己。', 'error')
        return redirect(url_for('admin.managers'))

    # 只能刪除 admin，不能刪除 super_admin
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
    """
    升級使用者為管理員路由。只有 super_admin 才可存取。
    安全限制：
    - 不能修改自己的角色
    - 只能升級狀態正常（active）的使用者
    - 已是管理員的使用者無需再升級
    操作記錄會寫入活動日誌。
    """
    user = User.query.get_or_404(user_id)

    # 不能修改自己的角色
    if user.id == current_user.id:
        flash('不能修改自己的角色。', 'error')
        return redirect(url_for('admin.managers'))

    # 停權或封禁中的使用者不能設為管理員
    if user.status != 'active':
        flash('停權或封鎖中的使用者不能設為管理者。', 'error')
        return redirect(url_for('admin.managers'))

    # 已是管理員則不需要升級
    if user.role in ['admin', 'super_admin']:
        flash('此使用者已經是管理者。', 'warning')
        return redirect(url_for('admin.managers'))

    user.role = 'admin'
    db.session.commit()

    # 記錄升級操作日誌
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
    """
    檢舉列表路由。需管理員以上權限。
    支援依狀態篩選（all / pending / reviewed / rejected / resolved / punished）。
    """
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
    """
    檢舉詳情路由。需管理員以上權限。
    顯示單筆檢舉的完整資訊（包含被檢舉內容、附件、管理員備註等）。
    """
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
    """
    更新檢舉狀態路由（POST）。需管理員以上權限。
    可更新：狀態、管理員備註（admin_note）、回饋給使用者的說明（feedback）。
    若狀態有變更，自動發送通知給檢舉人；
    若狀態為 'punished'，另外通知被檢舉的使用者。
    操作記錄會寫入活動日誌。
    """
    report = Report.query.get_or_404(report_id)

    old_status = report.status
    new_status = request.form.get('status', '').strip()
    admin_note = request.form.get('admin_note', '').strip()
    feedback = request.form.get('feedback', '').strip()

    # 驗證狀態值
    if new_status not in ['pending', 'reviewed', 'rejected', 'resolved', 'punished']:
        abort(400)

    status_changed = old_status != new_status

    # 更新檢舉記錄
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

    # 狀態有變更時，發送通知給相關使用者
    if status_changed:
        notifications = []
        # 發送通知給檢舉人
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

        # 若狀態為 punished，另外通知被檢舉的使用者
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

    # 記錄管理員操作日誌
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
    """
    從檢舉詳情頁直接對被檢舉使用者採取帳號處置路由（POST）。需管理員以上權限。
    允許的狀態：active（解除限制）/ suspended（停權）/ banned（封禁）。
    安全限制：
    - 遵循 _can_manage_user_status 的權限規則
    - 不能對自己採取停權或封禁
    - 狀態未變更時顯示警告
    處置後自動通知被處置的使用者，並記錄活動日誌。
    """
    report = Report.query.get_or_404(report_id)
    reported_user = report.reported_user

    if not reported_user:
        abort(400)

    requested_account_status = _normalize_user_status(request.form.get('account_status', ''))
    action_reason = request.form.get('action_reason', '').strip()

    # 驗證狀態值
    if requested_account_status not in {'active', 'suspended', 'banned'}:
        flash('帳號狀態值不正確。', 'error')
        return redirect(url_for('admin.report_detail', report_id=report_id))

    # 權限檢查
    if not _can_manage_user_status(reported_user):
        abort(403)

    # 不能對自己停權或封禁
    if reported_user.id == current_user.id and requested_account_status in {'suspended', 'banned'}:
        abort(403)

    # 若狀態沒有變更，不需要更新
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

    # 發送通知給被處置的使用者
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

    # 記錄帳號處置的活動日誌
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
