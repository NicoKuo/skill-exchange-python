# routes/skills.py: 技能管理路由
# 功能：瀏覽技能列表、上架技能、編輯技能、下架技能、檢舉技能、下載附件
import os
from datetime import datetime
from io import BytesIO
from uuid import uuid4

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, send_file, abort, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from models import db, Skill, SkillCategory, Match, ActivityLog, Report

skills_bp = Blueprint('skills', __name__)

# 技能附件允許的副檔名（含文件格式）
ALLOWED_ATTACHMENT_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'txt', 'doc', 'docx', 'ppt', 'pptx'}
# 圖片類型的副檔名（用於檢舉附件驗證）
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def file_size(file_storage):
    """
    取得 FileStorage 物件的檔案大小（位元組）。
    透過移動 stream 游標到結尾來計算大小，完成後恢復原始位置。
    """
    stream = file_storage.stream
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


def allowed_attachment(filename):
    """檢查附件副檔名是否在允許的清單中。"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS


def detect_attachment_type(filename_or_url):
    """
    判斷附件類型：'image'（圖片）/ 'pdf'（PDF）/ 'file'（其他文件）。
    支援從 MIME 類型字串或副檔名判斷。
    """
    if not filename_or_url:
        return 'file'

    value = str(filename_or_url).strip().lower()
    mime_value = value.split(';', 1)[0].strip()
    if mime_value in {'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'}:
        return 'image'
    if mime_value == 'application/pdf':
        return 'pdf'
    if mime_value.startswith('image/'):
        return 'image'

    base_value = value.split('?', 1)[0].split('#', 1)[0]
    ext = base_value.rsplit('.', 1)[-1] if '.' in base_value else ''
    if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        return 'image'
    if ext == 'pdf':
        return 'pdf'

    return 'file'


def parse_time_input(value):
    """
    將 HH:MM 格式的時間字串解析為 time 物件。
    若輸入為空則回傳 None，格式錯誤則拋出 ValueError。
    """
    value = (value or '').strip()
    if not value:
        return None

    return datetime.strptime(value, '%H:%M').time()


def build_skill_form_values(skill=None):
    """
    建立技能表單的欄位初始值字典。
    POST 請求時：從表單資料取值（用於驗證失敗後重新填入）。
    GET 請求時：從 skill 物件取值（用於編輯現有技能），若 skill 為 None 則使用預設值。
    """
    if request.method == 'POST':
        return {
            'title_value': request.form.get('title', '').strip(),
            'description_value': request.form.get('description', '').strip(),
            'type_value': request.form.get('type', 'offer'),
            'method_value': request.form.get('method', 'online'),
            'category_id_value': request.form.get('category_id', '').strip(),
            'location_type_value': request.form.get('location_type', '').strip(),
            'location_area_value': request.form.get('location_area', '').strip(),
            'location_detail_value': request.form.get('location_detail', '').strip(),
            'available_day_value': request.form.get('available_day', '').strip(),
            'start_time_value': request.form.get('start_time', '').strip(),
            'end_time_value': request.form.get('end_time', '').strip(),
        }

    # 從現有技能物件取值（編輯模式），或使用空字串預設值（新增模式）
    return {
        'title_value': skill.title if skill else '',
        'description_value': skill.description if skill else '',
        'type_value': skill.type if skill else 'offer',
        'method_value': skill.method if skill else 'online',
        'category_id_value': str(skill.category_id) if skill and skill.category_id else '',
        'location_type_value': skill.location_type if skill and skill.location_type else '',
        'location_area_value': skill.location_area if skill and skill.location_area else '',
        'location_detail_value': skill.location_detail if skill and skill.location_detail else '',
        'available_day_value': skill.available_day if skill and skill.available_day else '',
        'start_time_value': skill.start_time.strftime('%H:%M') if skill and skill.start_time else '',
        'end_time_value': skill.end_time.strftime('%H:%M') if skill and skill.end_time else '',
    }


@skills_bp.route('/skills/<int:skill_id>/attachment', endpoint='skill_attachment')
@skills_bp.route('/skill-attachments/<path:filename>', endpoint='skill_attachment')
def skill_attachment(skill_id=None, filename=None):
    """
    技能附件下載/預覽路由（支援兩種 URL 格式）。
    若提供 skill_id：從資料庫 BLOB 中讀取附件資料並串流回傳（不強制下載）。
    若提供 filename：從磁碟上的 skill_attachments 資料夾回傳檔案。
    附件不存在時回傳 404。
    """
    if skill_id is not None:
        skill = Skill.query.get_or_404(skill_id)
        if not skill.attachment_data:
            abort(404)

        # 將 BLOB 資料包裝成 BytesIO 串流回傳
        return send_file(
            BytesIO(skill.attachment_data),
            mimetype=skill.attachment_mime or 'application/octet-stream',
            download_name=skill.attachment_name or f'skill-{skill.id}',
            as_attachment=False,  # 在瀏覽器中預覽（非強制下載）
        )

    if filename:
        # 從 instance 資料夾的 skill_attachments 子目錄回傳檔案
        attachment_dir = os.path.join(current_app.instance_path, 'skill_attachments')
        return send_from_directory(attachment_dir, filename)

    abort(404)


@skills_bp.route("/skills", endpoint='skills')
def skills():
    """
    技能列表頁路由。
    支援多維度搜尋篩選：關鍵字、分類、類型（offer/learn）、教學方式、地點類型、地區、可配合星期。
    若已登入，同時標記使用者已申請媒合的技能（applied_skill_ids），讓介面可隱藏申請按鈕。
    """
    # 取得搜尋條件
    keyword = request.args.get("keyword", "").strip()
    category_id = request.args.get("category_id", "").strip()
    skill_type = request.args.get("type", "").strip()
    method = request.args.get("method", "").strip()
    location_type = request.args.get("location_type", "").strip()
    location_area = request.args.get("location_area", "").strip()
    available_day = request.args.get("available_day", "").strip()

    # 取得已登入使用者的所有媒合申請過的技能 ID（避免重複申請）
    applied_skill_ids = set()
    if current_user.is_authenticated:
        applied_skill_ids = {
            row[0]
            for row in db.session.query(Match.skill_id)
            .filter(
                or_(
                    Match.requester_id == current_user.id,
                    Match.receiver_id == current_user.id,
                )
            )
            .distinct()
            .all()
        }

    # 基礎查詢：只顯示上架中的技能（排除已下架和已刪除的技能）
    query = Skill.query.filter_by(is_active=True).filter(Skill.status == "open")

    # 套用各篩選條件
    if keyword:
        query = query.filter(
            or_(
                Skill.title.contains(keyword),
                Skill.description.contains(keyword)
            )
        )

    if category_id:
        query = query.filter(Skill.category_id == int(category_id))

    if skill_type:
        query = query.filter(Skill.type == skill_type)

    if method:
        query = query.filter_by(method=method)

    if location_type:
        query = query.filter(Skill.location_type == location_type)

    if location_area:
        query = query.filter(Skill.location_area == location_area)

    if available_day:
        query = query.filter(Skill.available_day == available_day)

    # 依建立時間倒序排列
    skills = query.order_by(Skill.created_at.desc()).all()
    categories = SkillCategory.query.order_by(SkillCategory.name.asc()).all()

    return render_template(
        "skills.html",
        skills=skills,
        categories=categories,
        keyword=keyword,
        category_id=category_id,
        type=skill_type,
        method=method,
        location_type=location_type,
        location_area=location_area,
        available_day=available_day,
        applied_skill_ids=applied_skill_ids,
    )


@skills_bp.route("/add-skill", methods=["GET", "POST"], endpoint='add_skill')
@login_required
def add_skill():
    """
    新增技能路由。需登入才可存取。
    GET：顯示新增技能表單，並確保預設分類存在。
    POST：驗證表單資料（含附件），建立技能並記錄活動日誌，成功後導向技能列表。
    附件限制：5MB 以下，支援 jpg/png/gif/webp/pdf/txt/doc/docx/ppt/pptx。
    """
    # 確保預設技能分類存在（首次使用時自動建立）
    default_names = [
        '學業課業', '語言學習', '科技與程式', '設計與創作', '藝術與音樂',
        '運動與健康', '生活技能', '社交與溝通', '商業與行銷', '其他'
    ]
    existing = {c.name for c in SkillCategory.query.all()}
    added_default_category = False
    for name in default_names:
        if name not in existing:
            db.session.add(SkillCategory(name=name))
            added_default_category = True

    if added_default_category or not existing:
        db.session.commit()

    categories = SkillCategory.query.order_by(SkillCategory.name.asc()).all()
    form_values = build_skill_form_values()

    if request.method == "POST":
        # 處理附件上傳
        attachment = request.files.get("attachment")
        attachment_data = None
        attachment_name = None
        attachment_mime = None
        attachment_type = None

        if attachment and attachment.filename:
            # 驗證副檔名
            if not allowed_attachment(attachment.filename):
                flash("只支援 jpg、jpeg、png、gif、webp、pdf、txt、doc、docx、ppt、pptx 檔案。", "error")
                return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

            # 驗證檔案大小
            if file_size(attachment) > current_app.config.get('SKILL_ATTACHMENT_MAX_SIZE', 5 * 1024 * 1024):
                flash("技能附件不能超過 5MB。", "error")
                return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

            # 讀取附件資料存入資料庫
            attachment_data = attachment.read()
            attachment_name = attachment.filename
            attachment_mime = attachment.mimetype or 'application/octet-stream'
            attachment_type = detect_attachment_type(attachment_name or attachment_mime)

        # 從表單取得欄位值
        title = form_values['title_value']
        description_text = form_values['description_value']
        category_id_raw = form_values['category_id_value']
        location_type = form_values['location_type_value']
        location_area = form_values['location_area_value']
        location_detail = form_values['location_detail_value']
        available_day = form_values['available_day_value']

        # 解析時間輸入
        try:
            start_time = parse_time_input(form_values['start_time_value'])
            end_time = parse_time_input(form_values['end_time_value'])
        except ValueError:
            flash("開始時間與結束時間格式不正確，請使用時間選擇器。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        # 必填欄位驗證
        if not title:
            flash("技能標題必填。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if not description_text:
            flash("技能描述必填。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if len(title) > 50:
            flash("技能標題最多 50 個字。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if not category_id_raw.isdigit():
            flash("請選擇分類。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if not location_type:
            flash("請選擇地點類型。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if not location_area:
            flash("請選擇地區。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        if not available_day:
            flash("請選擇可配合星期。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        # 時間邏輯驗證：結束時間不可早於開始時間
        if start_time and end_time and end_time < start_time:
            flash("結束時間不可早於開始時間。", "error")
            return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)

        # 建立技能物件並儲存
        skill = Skill(
            user_id=current_user.id,
            category_id=int(category_id_raw),
            title=title,
            description=description_text,
            type=form_values['type_value'],
            method=form_values['method_value'],
            location_type=location_type,
            location_area=location_area,
            location_detail=location_detail,
            available_day=available_day,
            start_time=start_time,
            end_time=end_time,
            status="open",
            is_active=True,
            attachment_data=attachment_data,
            attachment_name=attachment_name,
            attachment_mime=attachment_mime,
            attachment_type=attachment_type,
        )

        db.session.add(skill)
        db.session.commit()
        # 記錄上架技能的活動日誌
        try:
            log = ActivityLog(user_id=current_user.id, action='create_skill', detail=f'skill_id={skill.id}|title={skill.title}', ip_address=request.remote_addr)
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()
        flash("技能已上架。", "success")
        return redirect(url_for(".skills"))

    return render_template("add_skill.html", categories=categories, skill=None, form_action=url_for(".add_skill"), **form_values)


@skills_bp.route("/skills/<int:skill_id>/edit", methods=["GET", "POST"], endpoint='edit_skill')
@login_required
def edit_skill(skill_id):
    """
    編輯技能路由。需登入且只有技能擁有者才可存取。
    GET：顯示預填現有資料的編輯表單。
    POST：驗證並更新技能資料（含附件），成功後記錄日誌並導向技能列表。
    若上傳新附件則替換舊附件，否則保留原附件。
    """
    skill = Skill.query.get_or_404(skill_id)

    # 權限檢查：只有技能擁有者才能編輯
    if skill.user_id != current_user.id:
        abort(403)

    categories = SkillCategory.query.order_by(SkillCategory.name.asc()).all()
    form_values = build_skill_form_values(skill)

    if request.method == "POST":
        # 預設保留原有附件資料
        attachment = request.files.get("attachment")
        attachment_data = skill.attachment_data
        attachment_name = skill.attachment_name
        attachment_mime = skill.attachment_mime
        attachment_type = skill.attachment_type

        # 若上傳新附件則覆蓋原本的
        if attachment and attachment.filename:
            if not allowed_attachment(attachment.filename):
                flash("只支援 jpg、jpeg、png、gif、webp、pdf、txt、doc、docx、ppt、pptx 檔案。", "error")
                return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

            if file_size(attachment) > current_app.config.get('SKILL_ATTACHMENT_MAX_SIZE', 5 * 1024 * 1024):
                flash("技能附件不能超過 5MB。", "error")
                return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

            attachment_data = attachment.read()
            attachment_name = attachment.filename
            attachment_mime = attachment.mimetype or 'application/octet-stream'
            attachment_type = detect_attachment_type(attachment_name or attachment_mime)

        # 取得表單欄位值（與新增技能相同的驗證流程）
        title = form_values['title_value']
        description_text = form_values['description_value']
        category_id_raw = form_values['category_id_value']
        location_type = form_values['location_type_value']
        location_area = form_values['location_area_value']
        location_detail = form_values['location_detail_value']
        available_day = form_values['available_day_value']

        try:
            start_time = parse_time_input(form_values['start_time_value'])
            end_time = parse_time_input(form_values['end_time_value'])
        except ValueError:
            flash("開始時間與結束時間格式不正確，請使用時間選擇器。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        # 必填欄位驗證（同新增技能）
        if not title:
            flash("技能標題必填。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if not description_text:
            flash("技能描述必填。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if len(title) > 50:
            flash("技能標題最多 50 個字。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if not category_id_raw.isdigit():
            flash("請選擇分類。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if not location_type:
            flash("請選擇地點類型。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if not location_area:
            flash("請選擇地區。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if not available_day:
            flash("請選擇可配合星期。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        if start_time and end_time and end_time < start_time:
            flash("結束時間不可早於開始時間。", "error")
            return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)

        # 更新技能欄位
        skill.category_id = int(category_id_raw)
        skill.title = title
        skill.description = description_text
        skill.type = form_values['type_value']
        skill.method = form_values['method_value']
        skill.location_type = location_type
        skill.location_area = location_area
        skill.location_detail = location_detail
        skill.available_day = available_day
        skill.start_time = start_time
        skill.end_time = end_time
        skill.attachment_data = attachment_data
        skill.attachment_name = attachment_name
        skill.attachment_mime = attachment_mime
        skill.attachment_type = attachment_type

        db.session.commit()
        # 記錄編輯活動日誌
        try:
            log = ActivityLog(user_id=current_user.id, action='edit_skill', detail=f'skill_id={skill.id}|title={skill.title}', ip_address=request.remote_addr)
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash("技能已更新。", "success")
        return redirect(url_for(".skills"))

    return render_template("add_skill.html", categories=categories, skill=skill, form_action=url_for(".edit_skill", skill_id=skill.id), **form_values)


@skills_bp.route("/skills/<int:skill_id>/deactivate", methods=["POST"], endpoint='deactivate_skill')
@login_required
def deactivate_skill(skill_id):
    """
    技能下架路由。需登入且只有技能擁有者才可存取。
    將技能的 is_active 設為 False、status 設為 'closed'，使其不再顯示於列表。
    若技能已是下架狀態，顯示警告訊息。
    """
    skill = Skill.query.get_or_404(skill_id)

    # 權限檢查
    if skill.user_id != current_user.id:
        abort(403)

    if not skill.is_active:
        flash("這個技能已經下架。", "warning")
        return redirect(request.referrer or url_for("profile.dashboard"))

    skill.is_active = False
    skill.status = 'closed'
    db.session.commit()
    flash("技能已下架。", "success")
    return redirect(request.referrer or url_for("profile.dashboard"))


@skills_bp.route("/skills/<int:skill_id>/delete", methods=["POST"], endpoint='delete_skill')
@login_required
def delete_skill(skill_id):
    """
    技能刪除路由。需登入且只有技能擁有者才可存取。
    支援軟刪除和硬刪除：
    - 若技能有關聯的媒合記錄，使用軟刪除（status='deleted'）
    - 若技能無任何關聯資料，直接硬刪除
    已刪除或已下架的技能無法再次刪除。
    """
    skill = Skill.query.get_or_404(skill_id)

    # 權限檢查：只有技能發布者本人才能刪除
    if skill.user_id != current_user.id:
        abort(403)

    # 檢查技能是否已被刪除或下架
    if skill.status == 'deleted':
        flash("這個技能已經被刪除。", "warning")
        return redirect(request.referrer or url_for("profile.dashboard"))

    # 檢查是否有關聯的媒合記錄
    has_matches = Match.query.filter_by(skill_id=skill.id).count() > 0

    try:
        if has_matches:
            # 有媒合記錄：使用軟刪除
            skill.status = 'deleted'
            skill.is_active = False
            db.session.commit()
        else:
            # 無任何關聯資料：直接硬刪除
            db.session.delete(skill)
            db.session.commit()

        # 記錄刪除活動日誌
        try:
            log = ActivityLog(
                user_id=current_user.id,
                action='delete_skill',
                detail=f'skill_id={skill_id}|has_matches={has_matches}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash("技能已刪除。", "success")
    except Exception as e:
        db.session.rollback()
        flash("技能刪除失敗，請稍後再試。", "error")

    return redirect(request.referrer or url_for("profile.dashboard"))


@skills_bp.route("/skills/<int:skill_id>/report", methods=["POST"], endpoint='report_skill')
def report_skill(skill_id):
    """
    技能檢舉 API 路由（回傳 JSON）。
    需登入才可使用，且不能檢舉自己的技能。
    防止重複：同一使用者對同一技能只能有一個 pending 檢舉。
    支援上傳圖片附件作為證據（限 5MB 以下的圖片格式）。
    """
    if not current_user.is_authenticated:
        return jsonify({
            "success": False,
            "message": "請先登入後再檢舉。"
        }), 401

    skill = Skill.query.get(skill_id)
    if not skill:
        return jsonify({
            "success": False,
            "message": "找不到要檢舉的技能。"
        }), 404

    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    evidence = request.files.get("evidence")

    # 不能檢舉自己的技能
    if skill.user_id == current_user.id:
        return jsonify({
            "success": False,
            "message": "你不能檢舉自己的技能。"
        }), 400

    # 檢查是否已有待審的檢舉（防止重複送出）
    existing = Report.query.filter_by(
        reporter_id=current_user.id,
        skill_id=skill_id,
        status='pending'
    ).first()

    if existing:
        return jsonify({
            "success": False,
            "message": "你已檢舉過這個技能，請等待審核。"
        }), 400

    # 驗證檢舉原因代碼
    valid_reasons = ['inappropriate_content', 'spam', 'scam', 'copyright', 'other']
    if reason not in valid_reasons:
        return jsonify({
            "success": False,
            "message": "檢舉原因無效。"
        }), 400

    # 處理檢舉附件（證據圖片）
    evidence_url = None
    evidence_name = None
    evidence_type = None

    if evidence and evidence.filename:
        # 只允許圖片格式
        ext = evidence.filename.rsplit('.', 1)[1].lower() if '.' in evidence.filename else ''
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({
                "success": False,
                "message": "只支援圖片檔案（jpg、jpeg、png、gif、webp）。"
            }), 400

        # 檢查檔案大小（5MB 上限）
        if file_size(evidence) > 5 * 1024 * 1024:
            return jsonify({
                "success": False,
                "message": "檢舉附件不能超過 5MB。"
            }), 400

        # 用 UUID 前綴避免檔名衝突，儲存到 static/uploads/report/
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
        reported_user_id=skill.user_id,
        skill_id=skill_id,
        reason=reason,
        description=description,
        evidence_file_url=evidence_url,
        evidence_file_name=evidence_name,
        evidence_file_type=evidence_type,
        status='pending'
    )
    try:
        db.session.add(report)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "檢舉送出失敗，請稍後再試。"
        }), 500

    # 記錄活動日誌
    try:
        log = ActivityLog(
            user_id=current_user.id,
            action='report_skill',
            detail=f'report_id={report.id}|skill_id={skill_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        "success": True,
        "message": "檢舉已送出，將由管理者審查。"
    })


@skills_bp.route("/skills/announcement", methods=["GET", "POST"], endpoint='announcement')
@login_required
def skill_announcement():
    """
    技能上架提醒頁面。
    使用者可選擇是否要前往新增技能頁面。
    GET：顯示選擇頁面。
    POST：根據使用者的選擇進行導向。
    """
    if request.method == "POST":
        choice = request.form.get("choice", "").strip()
        
        if choice == "add_skill":
            # 使用者選擇上架技能
            return redirect(url_for("skills.add_skill"))
        else:
            # 使用者選擇暫時不要，清除 session 標記
            session.pop('show_skill_announcement', None)
            return redirect(url_for("profile.dashboard"))
    
    return render_template("skill_announcement.html")
