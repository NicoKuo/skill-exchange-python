# routes/chat.py: Blueprint for chat/message views tied to matches
from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user

from models import db, Match, Message
from utils import add_notification

chat_bp = Blueprint('chat', __name__)


@chat_bp.route("/chat/<int:match_id>", methods=["GET", "POST"], endpoint='chat')
@login_required
def chat(match_id):
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    other_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id

    if request.method == "POST":
        content = request.form.get("content", "").strip()

        if content:
            db.session.add(
                Message(
                    match_id=m.id,
                    sender_id=current_user.id,
                    receiver_id=other_id,
                    content=content
                )
            )
            db.session.commit()
            add_notification(other_id, "message", "你收到一則新訊息。", m.id)
            return redirect(url_for(".chat", match_id=m.id))

    messages = Message.query.filter_by(match_id=m.id).order_by(Message.created_at.asc()).all()

    return render_template("chat.html", match=m, messages=messages, other_id=other_id)
