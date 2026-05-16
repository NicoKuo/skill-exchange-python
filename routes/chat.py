# routes/chat.py: 聊天室路由
# 功能：媒合雙方的即時訊息、附件上傳、未讀計數、檢舉訊息
# 所有路由都需要是媒合的其中一方才有權限存取
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

# 聊天室允許上傳的圖片副檔名
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
# 聊天室允許上傳的文件副檔名
ALLOWED_FILE_EXTENSIONS = {'pdf', 'docx', 'pptx', 'xlsx', 'zip'}


@chat_bp.route("/chat", methods=["GET"], endpoint='chat_list')
@login_required
def chat_list():
    """
    聊天列表路由（導向媒合中心）。
    聊天室是依附在媒合下的，所以 /chat 直接導向 /match。
    """
    return redirect(url_for('matches.match_center'))


def allowed_chat_upload(filename):
    """檢查聊天附件副檔名是否合法（圖片或文件類型）。"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in (ALLOWED_IMAGE_EXTENSIONS | ALLOWED_FILE_EXTENSIONS)


def chat_upload_type(filename):
    """
    判斷上傳檔案的類型。
    回傳：'image'（圖片）/ 'file'（文件）/ None（不支援的格式）。
    """
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return 'image'
    if ext in ALLOWED_FILE_EXTENSIONS:
        return 'file'
    return None


def file_size(file_storage):
    """
    取得 FileStorage 物件的檔案大小（位元組）。
    透過移動 stream 游標計算，完成後恢復原始位置。
    """
    stream = file_storage.stream
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


@chat_bp.route("/chat/<int:match_id>", methods=["GET", "POST"], endpoint='chat')
@login_required
def chat(match_id):
    """
    聊天室路由。需登入且必須是媒合的其中一方才可存取。

    GET：顯示此媒合的所有訊息，並將目前使用者的未讀訊息全部標記為已讀。
    POST：發送訊息（可附帶檔案）。
      附件限制：10MB 以下，圖片（jpg/png/gif/webp）或文件（pdf/docx/pptx/xlsx/zip）。
      防重複：若與最後一則訊息內容相同且間隔小於 2 秒，則忽略此次發送。
    """
    m = Match.query.get_or_404(match_id)

    # 只有媒合的雙方才能進入聊天室
    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    # 判斷對方是申請方還是被申請方
    if current_user.id == m.requester_id:
        other_user = m.receiver
    else:
        other_user = m.requester
    other_id = other_user.id

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        attachment = request.files.get("attachment")
        file_url = None
        file_name = None
        file_type = None

        # 處理聊天附件上傳
        if attachment and attachment.filename:
            if not allowed_chat_upload(attachment.filename):
                flash("聊天附件只支援 jpg、jpeg、png、gif、webp、pdf、docx、pptx、xlsx、zip。", "error")
                return redirect(url_for(".chat", match_id=m.id))

            if file_size(attachment) > current_app.config.get('CHAT_ATTACHMENT_MAX_SIZE', 10 * 1024 * 1024):
                flash("聊天附件不能超過 10MB。", "error")
                return redirect(url_for(".chat", match_id=m.id))

            # 使用 UUID 前綴避免檔名衝突，儲存到 static/uploads/chat/
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'chat')
            os.makedirs(upload_dir, exist_ok=True)
            original_name = secure_filename(attachment.filename)
            stored_name = f"{uuid4().hex}_{original_name}"
            attachment.save(os.path.join(upload_dir, stored_name))
            file_url = url_for('static', filename=f'uploads/chat/{stored_name}')
            file_name = original_name
            file_type = chat_upload_type(attachment.filename)

        # 有訊息內容或附件才儲存
        if content or file_url:
            # 防止重複訊息：若與最後一則訊息完全相同且 2 秒內，忽略此次
            last_message = Message.query.filter_by(match_id=m.id, sender_id=current_user.id).order_by(Message.created_at.desc()).first()
            if not file_url and last_message and last_message.content == content:
                elapsed_seconds = (datetime.utcnow() - last_message.created_at).total_seconds()
                if elapsed_seconds < 2:
                    return redirect(url_for(".chat", match_id=m.id))

            # 儲存訊息到資料庫
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
            # 通知對方有新訊息
            add_notification(other_id, "message", "你收到一則新訊息。", m.id)
            return redirect(url_for(".chat", match_id=m.id))

    # GET：將未讀訊息全部標記為已讀
    unread_messages = Message.query.filter_by(
        match_id=m.id,
        receiver_id=current_user.id,
        is_read=False
    ).all()

    if unread_messages:
        for message in unread_messages:
            message.is_read = True
        db.session.commit()

    # 取得此媒合的所有訊息，依時間正序排列（舊的在上）
    messages = Message.query.filter_by(match_id=m.id).order_by(Message.created_at.asc()).all()

    return render_template("chat.html", match=m, messages=messages, other_id=other_id, other_user=other_user)


@chat_bp.route("/chat/<int:match_id>/messages", methods=["GET"], endpoint='get_messages')
@login_required
def get_messages(match_id):
    """
    取得訊息列表 API（回傳 JSON）。
    回傳指定媒合的所有訊息，含發送者姓名、內容、附件資訊、時間等。
    需是媒合的其中一方才有權限。
    """
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
    """
    AJAX 發送訊息 API（回傳 JSON）。
    用於前端即時更新聊天介面，不重新載入頁面。
    防重複：若與最後一則訊息完全相同且 2 秒內，回傳錯誤。
    成功後通知對方並回傳新訊息的 JSON 資料。
    """
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    other_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
    content = request.form.get("content", "").strip()

    # 訊息內容不能為空
    if not content:
        return jsonify({"error": "訊息不能為空"}), 400

    # 防止重複發送相同訊息（2 秒內）
    last_message = Message.query.filter_by(match_id=m.id, sender_id=current_user.id).order_by(Message.created_at.desc()).first()
    if last_message and last_message.content == content:
        elapsed_seconds = (datetime.utcnow() - last_message.created_at).total_seconds()
        if elapsed_seconds < 2:
            return jsonify({"error": "訊息發送過於頻繁"}), 429

    # 儲存新訊息
    msg = Message(
        match_id=m.id,
        sender_id=current_user.id,
        receiver_id=other_id,
        content=content,
        is_read=False
    )
    db.session.add(msg)
    db.session.commit()

    # 通知對方有新訊息
    add_notification(other_id, "message", "你收到一則新訊息。", m.id)

    # 回傳新訊息的資料（前端用於動態插入訊息泡泡）
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
    """
    未讀訊息計數 API（回傳 JSON）。
    回傳目前登入使用者在所有聊天室中的未讀訊息總數。
    用於導覽列顯示未讀訊息提示徽章。
    """
    count = Message.query.filter_by(
        receiver_id=current_user.id,
        is_read=False
    ).count()
    return jsonify({"count": count})


@chat_bp.route("/chat/<int:match_id>/report-message", methods=["POST"], endpoint='report_message')
def report_message(match_id):
    """
    檢舉訊息 API（回傳 JSON）。
    需是媒合的其中一方，且只能檢舉對方的訊息，不能檢舉自己。
    防止重複：同一則訊息只能有一個 pending 檢舉。
    支援上傳圖片附件作為證據（限 5MB 以下的圖片格式）。
    未登入時回傳 403 JSON（非 HTML 重定向，避免 AJAX 請求失敗）。
    """
    # 未登入時回傳 JSON 格式的錯誤（而非 Flask-Login 的 HTML 登入頁重定向）
    if not current_user.is_authenticated:
        return jsonify({"success": False, "message": "沒有權限"}), 403

    m = Match.query.get(match_id)
    if not m:
        return jsonify({"success": False, "message": "找不到檢舉對象"}), 404

    # 只有媒合雙方才能檢舉
    if current_user.id not in [m.requester_id, m.receiver_id]:
        return jsonify({"success": False, "message": "沒有權限"}), 403

    message_id = request.form.get("message_id", type=int)
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    evidence = request.files.get("evidence")

    if not message_id:
        return jsonify({"success": False, "message": "找不到檢舉對象"}), 404

    msg = Message.query.get(message_id)
    if not msg:
        return jsonify({"success": False, "message": "找不到檢舉對象"}), 404

    # 確認訊息屬於這個媒合（防止跨媒合檢舉）
    if msg.match_id != match_id:
        return jsonify({"success": False, "message": "找不到檢舉對象"}), 404

    # 不能檢舉自己的訊息
    if msg.sender_id == current_user.id:
        return jsonify({"success": False, "message": "你不能檢舉自己的訊息"}), 400

    # 防止重複檢舉同一則訊息
    existing = Report.query.filter_by(
        reporter_id=current_user.id,
        message_id=message_id,
        status='pending'
    ).first()

    if existing:
        return jsonify({"success": False, "message": "你已檢舉過這則訊息"}), 400

    # 驗證檢舉原因代碼
    valid_reasons = ['inappropriate_language', 'harassment', 'no_show', 'scam', 'other']
    if reason not in valid_reasons:
        return jsonify({"success": False, "message": "檢舉原因無效"}), 400

    # 處理檢舉附件（證據圖片）
    evidence_url = None
    evidence_name = None
    evidence_type = None

    if evidence and evidence.filename:
        # 只允許圖片格式
        ext = evidence.filename.rsplit('.', 1)[1].lower() if '.' in evidence.filename else ''
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({"success": False, "message": "只支援圖片檔案（jpg、jpeg、png、gif、webp）"}), 400

        # 檢查檔案大小（5MB 上限）
        if file_size(evidence) > 5 * 1024 * 1024:
            return jsonify({"success": False, "message": "檢舉附件不能超過 5MB"}), 400

        # 儲存證據圖片
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'report')
        os.makedirs(upload_dir, exist_ok=True)
        original_name = secure_filename(evidence.filename)
        stored_name = f"{uuid4().hex}_{original_name}"
        evidence.save(os.path.join(upload_dir, stored_name))
        evidence_url = url_for('static', filename=f'uploads/report/{stored_name}')
        evidence_name = original_name
        evidence_type = 'image'

    # 建立檢舉記錄
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

    # 記錄活動日誌
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

    return jsonify({"success": True, "message": "檢舉已送出"})
