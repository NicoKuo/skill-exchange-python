# routes/matches.py: 媒合中心路由
# 功能：建立技能交換申請、接受/拒絕/取消/完成媒合、查看媒合列表、檢舉媒合對象
# 媒合狀態流程：pending（待回應）→ accepted（進行中）→ completed（已完成）→ 互評
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, Match, Skill, Message, Notification, ActivityLog, Report
from utils import add_notification, exchange_candidate_skills, user_pending_review_count

matches_bp = Blueprint('matches', __name__)


@matches_bp.route("/match", methods=["GET", "POST"], endpoint='match_center')
@login_required
def match_center():
    """
    媒合中心主路由。需登入才可存取。

    GET：顯示媒合列表，若附帶 skill_id 參數則顯示申請面板。
    POST（action 類型）：
      - create：送出新的媒合申請
      - accepted / rejected / completed / cancelled：更新媒合狀態

    「完成」機制採雙方確認制：
    兩方都標記完成後，媒合狀態才會更新為 completed，並通知雙方可以互評。
    """
    # 檢查是否有未完成的評價（有的話需先去評分才能建立新媒合）
    pending_review_count = user_pending_review_count(current_user.id)

    if request.method == "POST":
        action = request.form.get("action")

        # 建立新媒合申請
        if action == "create":
            # 若有待評分的媒合，先導向評分頁
            if pending_review_count > 0:
                flash("請先完成上一筆媒合的評價，再開始下一次交換。", "error")
                return redirect(url_for("reviews.review"))

            skill = Skill.query.get_or_404(int(request.form.get("skill_id")))

            # 確認技能仍在上架狀態
            if not skill.is_active or skill.status != "open":
                flash("這個技能已下架，無法再送出媒合。", "error")
                return redirect(url_for("skills.skills"))

            # 不能媒合自己的技能
            if skill.user_id == current_user.id:
                flash("不能媒合自己的技能。", "error")
            else:
                # 檢查是否已對這個技能申請過媒合（防止重複申請）
                existing_match = Match.query.filter(
                    Match.skill_id == skill.id,
                    or_(
                        Match.requester_id == current_user.id,
                        Match.receiver_id == current_user.id,
                    )
                ).first()

                if existing_match:
                    flash('你已經對這個技能申請過媒合，不能重複申請', 'error')
                    return redirect(url_for("matches.match_center", skill_id=skill.id))
                else:
                    # 建立媒合記錄並通知對方
                    m = Match(
                        skill_id=skill.id,
                        requester_id=current_user.id,
                        receiver_id=skill.user_id,
                        message=request.form.get("message") or "想和你進一步交換技能。"
                    )
                    db.session.add(m)
                    db.session.commit()
                    # 記錄活動日誌
                    try:
                        log = ActivityLog(user_id=current_user.id, action='create_match', detail=f'match_id={m.id}|skill_id={skill.id}|to={skill.user_id}', ip_address=request.remote_addr)
                        db.session.add(log)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    # 通知技能擁有者有新的媒合邀請
                    add_notification(skill.user_id, "match_request", "你收到新的技能媒合邀請。", m.id)
                    flash("媒合邀請已送出。", "success")

            return redirect(url_for("matches.match_center", skill_id=skill.id))

        # 更新媒合狀態（接受、拒絕、完成、取消）
        if action in ["accepted", "rejected", "completed", "cancelled"]:
            m = Match.query.get_or_404(int(request.form.get("match_id")))

            # 只有媒合的雙方才能操作
            if current_user.id not in [m.requester_id, m.receiver_id]:
                abort(403)

            # 取得對方的使用者 ID（用於發送通知）
            other = m.requester_id if m.receiver_id == current_user.id else m.receiver_id

            # 「完成」採雙方確認制：先記錄目前使用者的確認，等雙方都確認才標記完成
            if action == 'completed':
                # 記錄目前使用者已確認完成
                add_notification(current_user.id, 'completion_ack', '你已標記此媒合為完成。', m.id)
                # 通知對方確認
                add_notification(other, 'system', f"{current_user.name} 已標記媒合完成，請確認。", m.id)

                # 查詢是否雙方都已確認（兩個 completion_ack 通知都存在）
                acks = [n.user_id for n in Notification.query.filter_by(type='completion_ack', related_id=m.id).all()]
                if m.requester_id in acks and m.receiver_id in acks:
                    # 雙方都確認，正式標記為完成
                    m.status = 'completed'
                    db.session.commit()
                    # 通知雙方可以互評
                    add_notification(m.requester_id, 'review', '媒合已完成，請進行互評。', m.id)
                    add_notification(m.receiver_id, 'review', '媒合已完成，請進行互評。', m.id)
                    flash("媒合雙方已確認完成，現在可以互評。", "success")
                    return redirect(url_for("reviews.review"))
                else:
                    # 只有一方確認，等待對方
                    flash("已記錄您的完成標記，等待對方也標記後即可互評。", "success")
                    return redirect(url_for("matches.match_center"))

            # 其他狀態變更（accepted / rejected / cancelled）直接更新
            m.status = action
            db.session.commit()

            # 通知對方媒合狀態已變更
            add_notification(other, "system", f"你的媒合狀態更新為：{action}", m.id)

            flash("媒合狀態已更新。", "success")
            return redirect(url_for("matches.match_center"))

    # GET 請求：準備媒合頁面所需資料
    selected_skill = None
    selected_skill_has_match = False
    user_exchange_skills = []
    other_exchange_skills = []

    # 若 URL 帶有 skill_id 參數，顯示該技能的申請面板
    if request.args.get("skill_id"):
        selected_skill = Skill.query.get_or_404(int(request.args.get("skill_id")))
        if not selected_skill.is_active or selected_skill.status != 'open':
            flash("這個技能已下架，無法進行媒合。", "error")
            return redirect(url_for("skills.skills"))

        # 檢查使用者是否已對此技能有過媒合申請
        selected_skill_has_match = Match.query.filter(
            Match.skill_id == selected_skill.id,
            or_(
                Match.requester_id == current_user.id,
                Match.receiver_id == current_user.id,
            )
        ).first() is not None

        # 找出雙方可以交換的技能清單（顯示於申請面板）
        if current_user.is_authenticated and current_user.id != selected_skill.user_id:
            user_exchange_skills, other_exchange_skills = exchange_candidate_skills(selected_skill, current_user)

    # 取得此使用者的所有媒合記錄（含申請方和被申請方），依更新時間倒序
    matches = Match.query.filter(
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).order_by(Match.updated_at.desc()).all()

    # 計算各媒合的未讀訊息數，建立 {match_id: 未讀數} 的對照表
    unread_rows = db.session.query(
        Message.match_id,
        db.func.count(Message.id)
    ).filter(
        Message.receiver_id == current_user.id,
        Message.is_read.is_(False)
    ).group_by(Message.match_id).all()

    unread_map = {match_id: unread_count for match_id, unread_count in unread_rows}

    return render_template(
        "match.html",
        selected_skill=selected_skill,
        selected_skill_has_match=selected_skill_has_match,
        user_exchange_skills=user_exchange_skills,
        other_exchange_skills=other_exchange_skills,
        matches=matches,
        pending_review_count=pending_review_count,
        unread_map=unread_map,
    )


@matches_bp.route("/report", methods=["POST"], endpoint='create_report')
@login_required
def create_report():
    """
    檢舉媒合對象路由。需登入且必須是媒合的其中一方才可使用。
    防止重複：同一媒合只能有一個 pending 的檢舉。
    驗證原因代碼並建立檢舉記錄，成功後記錄活動日誌。
    """
    match_id = request.form.get("match_id", type=int)
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()

    m = Match.query.get_or_404(match_id)

    # 只有媒合的雙方才能提交檢舉
    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    # 確定被檢舉的對象（對方）
    reported_user_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id

    # 防止對同一媒合重複送出檢舉
    existing = Report.query.filter_by(
        reporter_id=current_user.id,
        match_id=match_id,
        status='pending'
    ).first()

    if existing:
        flash("你已對此媒合送出檢舉，請等待審查。", "warning")
        return redirect(request.referrer or url_for("matches.match_center"))

    # 驗證檢舉原因代碼
    valid_reasons = ['inappropriate_language', 'harassment', 'no_show', 'scam', 'other']
    if reason not in valid_reasons:
        flash("檢舉原因無效。", "error")
        return redirect(request.referrer or url_for("matches.match_center"))

    # 建立檢舉記錄
    report = Report(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        match_id=match_id,
        report_type='match',
        reason=reason,
        description=description,
        status='pending'
    )
    db.session.add(report)
    db.session.commit()

    # 記錄活動日誌
    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='create_report',
            detail=f'report_id={report.id}|match_id={match_id}|reported_user_id={reported_user_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    flash("檢舉已送出，將由管理者審查。", "success")
    return redirect(request.referrer or url_for("matches.match_center"))
