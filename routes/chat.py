# 聊天室 - 處理媒合對象之間的即時訊息交流
# routes/chat.py: Blueprint for chat/message views tied to matches

from datetime import datetime
from flask import jsonify
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
            last_message = Message.query.filter_by(match_id=m.id, sender_id=current_user.id).order_by(Message.created_at.desc()).first()
            if last_message and last_message.content == content:
                elapsed_seconds = (datetime.utcnow() - last_message.created_at).total_seconds()
                if elapsed_seconds < 2:
                    return redirect(url_for(".chat", match_id=m.id))

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

    unread_messages = Message.query.filter_by(
        match_id=m.id,
        receiver_id=current_user.id,
        is_read=False
    ).all()

    if unread_messages:
        for message in unread_messages:
            message.is_read = True
        db.session.commit()

    messages = Message.query.filter_by(match_id=m.id).order_by(Message.created_at.asc()).all()

    return render_template("chat.html", match=m, messages=messages, other_id=other_id)


@chat_bp.route("/chat/<int:match_id>/messages", methods=["GET"], endpoint='get_messages')
@login_required
def get_messages(match_id):
    """API endpoint: 取得指定媒合的所有訊息（JSON 格式）"""
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    messages = Message.query.filter_by(match_id=m.id).order_by(Message.created_at.asc()).all()

    return jsonify({
        "match_id": m.id,
        "messages": [
            {
                "id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender.name,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "is_read": msg.is_read,
            }
            for msg in messages
        ]
    })
