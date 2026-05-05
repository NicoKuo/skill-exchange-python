# 聊天室 - 處理媒合對象之間的即時訊息交流
# routes/chat.py: Blueprint for chat/message views tied to matches

import os
from datetime import datetime
from uuid import uuid4

from flask import jsonify, current_app
from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import db, Match, Message, Report, ActivityLog
from utils import add_notification

chat_bp = Blueprint('chat', __name__)
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_FILE_EXTENSIONS = {'pdf', 'docx', 'pptx', 'xlsx', 'zip'}


@chat_bp.route("/chat", methods=["GET"], endpoint='chat_list')
@login_required
def chat_list():
    return redirect(url_for('matches.match_center'))


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
                    is_read=False,
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


@chat_bp.route("/chat/<int:match_id>/send-message", methods=["POST"], endpoint='send_message_ajax')
@login_required
def send_message_ajax(match_id):
    """API endpoint: 用 AJAX 送出訊息，回傳 JSON"""
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    other_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
    content = request.form.get("content", "").strip()

    if not content:
        return jsonify({"error": "訊息不能為空"}), 400

    # 防止重複訊息
    last_message = Message.query.filter_by(match_id=m.id, sender_id=current_user.id).order_by(Message.created_at.desc()).first()
    if last_message and last_message.content == content:
        elapsed_seconds = (datetime.utcnow() - last_message.created_at).total_seconds()
        if elapsed_seconds < 2:
            return jsonify({"error": "訊息發送過於頻繁"}), 429

    msg = Message(
        match_id=m.id,
        sender_id=current_user.id,
        receiver_id=other_id,
        content=content,
        is_read=False
    )
    db.session.add(msg)
    db.session.commit()

    add_notification(other_id, "message", "你收到一則新訊息。", m.id)

    return jsonify({
        "id": msg.id,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender.name,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
        "is_read": msg.is_read,
    })


@chat_bp.route("/chat/unread-count", methods=["GET"], endpoint='unread_count')
@login_required
def unread_count():
    """API endpoint: 取得目前登入者的未讀訊息數"""
    count = Message.query.filter_by(
        receiver_id=current_user.id,
        is_read=False
    ).count()
    return jsonify({"count": count})


@chat_bp.route("/chat/<int:match_id>/report-message", methods=["POST"], endpoint='report_message')
@login_required
def report_message(match_id):
    """API endpoint: 檢舉訊息"""
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    message_id = request.form.get("message_id", type=int)
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    evidence = request.files.get("evidence")

    msg = Message.query.get_or_404(message_id)

    # 訊息必須屬於這個媒合
    if msg.match_id != match_id:
        abort(400)

    # 不能檢舉自己的訊息
    if msg.sender_id == current_user.id:
        return jsonify({"error": "你不能檢舉自己的訊息"}), 400

    # 檢查是否已有 pending 檢舉
    existing = Report.query.filter_by(
        reporter_id=current_user.id,
        message_id=message_id,
        status='pending'
    ).first()

    if existing:
        return jsonify({"error": "你已檢舉過這則訊息"}), 400

    valid_reasons = ['inappropriate_language', 'harassment', 'no_show', 'scam', 'other']
    if reason not in valid_reasons:
        return jsonify({"error": "檢舉原因無效"}), 400

    # 處理檢舉附件
    evidence_url = None
    evidence_name = None
    evidence_type = None
    
    if evidence and evidence.filename:
        # 只允許圖片格式
        ext = evidence.filename.rsplit('.', 1)[1].lower() if '.' in evidence.filename else ''
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({"error": "只支援圖片檔案（jpg、jpeg、png、gif、webp）"}), 400
        
        # 檢查檔案大小（5MB）
        if file_size(evidence) > 5 * 1024 * 1024:
            return jsonify({"error": "檢舉附件不能超過 5MB"}), 400
        
        # 保存檔案
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'report')
        os.makedirs(upload_dir, exist_ok=True)
        original_name = secure_filename(evidence.filename)
        stored_name = f"{uuid4().hex}_{original_name}"
        evidence.save(os.path.join(upload_dir, stored_name))
        evidence_url = url_for('static', filename=f'uploads/report/{stored_name}')
        evidence_name = original_name
        evidence_type = 'image'

    report = Report(
        reporter_id=current_user.id,
        reported_user_id=msg.sender_id,
        match_id=match_id,
        message_id=message_id,
        reason=reason,
        description=description,
        evidence_file_url=evidence_url,
        evidence_file_name=evidence_name,
        evidence_file_type=evidence_type,
        status='pending'
    )
    db.session.add(report)
    db.session.commit()

    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='report_message',
            detail=f'report_id={report.id}|message_id={message_id}|match_id={match_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({"message": "檢舉已送出，將由管理者審查"})
