# 媒合中心 - 管理技能交換配對與協商
# routes/matches.py: Blueprint for match creation and management (媒合中心)
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, Match, Skill, Message, Notification, ActivityLog, Report
from utils import add_notification, exchange_candidate_skills, user_pending_review_count

matches_bp = Blueprint('matches', __name__)


@matches_bp.route("/match", methods=["GET", "POST"], endpoint='match_center')
@login_required
def match_center():
    pending_review_count = user_pending_review_count(current_user.id)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            if pending_review_count > 0:
                flash("請先完成上一筆媒合的評價，再開始下一次交換。", "error")
                return redirect(url_for("reviews.review"))

            skill = Skill.query.get_or_404(int(request.form.get("skill_id")))

            if not skill.is_active or skill.status != "open":
                flash("這個技能已下架，無法再送出媒合。", "error")
                return redirect(url_for("skills.skills"))

            if skill.user_id == current_user.id:
                flash("不能媒合自己的技能。", "error")
            else:
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
                    m = Match(
                        skill_id=skill.id,
                        requester_id=current_user.id,
                        receiver_id=skill.user_id,
                        message=request.form.get("message") or "想和你進一步交換技能。"
                    )
                    db.session.add(m)
                    db.session.commit()
                    try:
                        log = ActivityLog(user_id=current_user.id, action='create_match', detail=f'match_id={m.id}|skill_id={skill.id}|to={skill.user_id}', ip_address=request.remote_addr)
                        db.session.add(log)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    add_notification(skill.user_id, "match_request", "你收到新的技能媒合邀請。", m.id)
                    flash("媒合邀請已送出。", "success")

            return redirect(url_for("matches.match_center", skill_id=skill.id))

        if action in ["accepted", "rejected", "completed", "cancelled"]:
            m = Match.query.get_or_404(int(request.form.get("match_id")))

            if current_user.id not in [m.requester_id, m.receiver_id]:
                abort(403)

            other = m.requester_id if m.receiver_id == current_user.id else m.receiver_id

            # If marking completed, record an acknowledgement for this user and notify the other.
            if action == 'completed':
                # record ack for current user
                add_notification(current_user.id, 'completion_ack', '你已標記此媒合為完成。', m.id)
                # notify other party
                add_notification(other, 'system', f"{current_user.name} 已標記媒合完成，請確認。", m.id)

                # check if both parties have acked
                acks = [n.user_id for n in Notification.query.filter_by(type='completion_ack', related_id=m.id).all()]
                if m.requester_id in acks and m.receiver_id in acks:
                    m.status = 'completed'
                    db.session.commit()
                    # notify both that review is now available
                    add_notification(m.requester_id, 'review', '媒合已完成，請進行互評。', m.id)
                    add_notification(m.receiver_id, 'review', '媒合已完成，請進行互評。', m.id)
                    flash("媒合雙方已確認完成，現在可以互評。", "success")
                    return redirect(url_for("reviews.review"))
                else:
                    flash("已記錄您的完成標記，等待對方也標記後即可互評。", "success")
                    return redirect(url_for("matches.match_center"))

            # other status transitions
            m.status = action
            db.session.commit()

            add_notification(other, "system", f"你的媒合狀態更新為：{action}", m.id)

            flash("媒合狀態已更新。", "success")
            return redirect(url_for("matches.match_center"))

    selected_skill = None
    selected_skill_has_match = False
    user_exchange_skills = []
    other_exchange_skills = []

    if request.args.get("skill_id"):
        selected_skill = Skill.query.get_or_404(int(request.args.get("skill_id")))
        if not selected_skill.is_active or selected_skill.status != 'open':
            flash("這個技能已下架，無法進行媒合。", "error")
            return redirect(url_for("skills.skills"))

        selected_skill_has_match = Match.query.filter(
            Match.skill_id == selected_skill.id,
            or_(
                Match.requester_id == current_user.id,
                Match.receiver_id == current_user.id,
            )
        ).first() is not None

        if current_user.is_authenticated and current_user.id != selected_skill.user_id:
            user_exchange_skills, other_exchange_skills = exchange_candidate_skills(selected_skill, current_user)

    matches = Match.query.filter(
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).order_by(Match.updated_at.desc()).all()

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
    match_id = request.form.get("match_id", type=int)
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    
    m = Match.query.get_or_404(match_id)
    
    # Check if current user is involved in the match
    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)
    
    # Determine reported user
    reported_user_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
    
    # Check for duplicate pending reports
    existing = Report.query.filter_by(
        reporter_id=current_user.id,
        match_id=match_id,
        status='pending'
    ).first()
    
    if existing:
        flash("你已對此媒合送出檢舉，請等待審查。", "warning")
        return redirect(request.referrer or url_for("matches.match_center"))
    
    # Validate reason
    valid_reasons = ['inappropriate_language', 'harassment', 'no_show', 'scam', 'other']
    if reason not in valid_reasons:
        flash("檢舉原因無效。", "error")
        return redirect(request.referrer or url_for("matches.match_center"))
    
    # Create report
    report = Report(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        match_id=match_id,
        reason=reason,
        description=description,
        status='pending'
    )
    db.session.add(report)
    db.session.commit()
    
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
