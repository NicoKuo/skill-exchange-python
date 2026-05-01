# 聊天室 - 處理媒合對象之間的即時訊息交流
# routes/chat.py: Blueprint for chat/message views tied to matches

import os
from datetime import datetime
from uuid import uuid4

from flask import jsonify, current_app
from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import db, Match, Message
from utils import add_notification

chat_bp = Blueprint('chat', __name__)
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_FILE_EXTENSIONS = {'pdf', 'docx', 'pptx', 'xlsx', 'zip'}


def allowed_chat_upload(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in (ALLOWED_IMAGE_EXTENSIONS | ALLOWED_FILE_EXTENSIONS)


def chat_upload_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return 'image'
    if ext in ALLOWED_FILE_EXTENSIONS:
        return 'file'
    return None


def file_size(file_storage):
    stream = file_storage.stream
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


@chat_bp.route("/chat/<int:match_id>", methods=["GET", "POST"], endpoint='chat')
@login_required
def chat(match_id):
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    other_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        attachment = request.files.get("attachment")
        file_url = None
        file_name = None
        file_type = None

        if attachment and attachment.filename:
            if not allowed_chat_upload(attachment.filename):
                flash("聊天附件只支援 jpg、jpeg、png、gif、webp、pdf、docx、pptx、xlsx、zip。", "error")
                return redirect(url_for(".chat", match_id=m.id))

            if file_size(attachment) > current_app.config.get('CHAT_ATTACHMENT_MAX_SIZE', 10 * 1024 * 1024):
                flash("聊天附件不能超過 10MB。", "error")
                return redirect(url_for(".chat", match_id=m.id))

            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'chat')
            os.makedirs(upload_dir, exist_ok=True)
            original_name = secure_filename(attachment.filename)
            stored_name = f"{uuid4().hex}_{original_name}"
            attachment.save(os.path.join(upload_dir, stored_name))
            file_url = url_for('static', filename=f'uploads/chat/{stored_name}')
            file_name = original_name
            file_type = chat_upload_type(attachment.filename)

        if content or file_url:
            last_message = Message.query.filter_by(match_id=m.id, sender_id=current_user.id).order_by(Message.created_at.desc()).first()
            if not file_url and last_message and last_message.content == content:
                elapsed_seconds = (datetime.utcnow() - last_message.created_at).total_seconds()
                if elapsed_seconds < 2:
                    return redirect(url_for(".chat", match_id=m.id))

            db.session.add(
                Message(
                    match_id=m.id,
                    sender_id=current_user.id,
                    receiver_id=other_id,
                    content=content or '',
                    file_url=file_url,
                    file_name=file_name,
                    file_type=file_type,
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
                "file_url": msg.file_url,
                "file_name": msg.file_name,
                "file_type": msg.file_type,
                "created_at": msg.created_at.isoformat(),
                "is_read": msg.is_read,
            }
            for msg in messages
        ]
    })
