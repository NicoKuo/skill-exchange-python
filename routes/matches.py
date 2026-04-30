# routes/matches.py: Blueprint for match creation and management (媒合中心)
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, Match, Skill, Notification
from utils import add_notification, user_pending_review_count

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

            if skill.user_id == current_user.id:
                flash("不能媒合自己的技能。", "error")
            else:
                exists = Match.query.filter(
                    Match.skill_id == skill.id,
                    Match.requester_id == current_user.id,
                    Match.status.in_(["pending", "accepted"])
                ).first()

                if exists:
                    flash("你已送出過這筆媒合邀請。", "error")
                else:
                    m = Match(
                        skill_id=skill.id,
                        requester_id=current_user.id,
                        receiver_id=skill.user_id,
                        message=request.form.get("message") or "想和你進一步交換技能。"
                    )
                    db.session.add(m)
                    db.session.commit()
                    add_notification(skill.user_id, "match_request", "你收到新的技能媒合邀請。", m.id)
                    flash("媒合邀請已送出。", "success")

            return redirect(url_for("matches.match_center"))

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

    selected_skill = Skill.query.get(request.args.get("skill_id")) if request.args.get("skill_id") else None

    matches = Match.query.filter(
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).order_by(Match.updated_at.desc()).all()

    return render_template(
        "match.html",
        selected_skill=selected_skill,
        matches=matches,
        pending_review_count=pending_review_count,
    )
