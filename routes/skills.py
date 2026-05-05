# 技能頁面 - 瀏覽與上架技能，支援多選類別和檔案附件
# routes/skills.py: Blueprint for skill listing and creation routes
import os
from io import BytesIO
from uuid import uuid4

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, send_file, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from models import db, Skill, SkillCategory, Match, ActivityLog, Report

skills_bp = Blueprint('skills', __name__)
ALLOWED_ATTACHMENT_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'txt', 'doc', 'docx', 'ppt', 'pptx'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def file_size(file_storage):
    stream = file_storage.stream
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS


def detect_attachment_type(filename_or_url):
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


@skills_bp.route('/skills/<int:skill_id>/attachment', endpoint='skill_attachment')
@skills_bp.route('/skill-attachments/<path:filename>', endpoint='skill_attachment')
def skill_attachment(skill_id=None, filename=None):
    if skill_id is not None:
        skill = Skill.query.get_or_404(skill_id)
        if not skill.attachment_data:
            abort(404)

        return send_file(
            BytesIO(skill.attachment_data),
            mimetype=skill.attachment_mime or 'application/octet-stream',
            download_name=skill.attachment_name or f'skill-{skill.id}',
            as_attachment=False,
        )

    if filename:
        attachment_dir = os.path.join(current_app.instance_path, 'skill_attachments')
        return send_from_directory(attachment_dir, filename)

    abort(404)


@skills_bp.route("/skills", endpoint='skills')
def skills():
    keyword = request.args.get("keyword", "").strip()
    category_id = request.args.get("category_id", "").strip()
    method = request.args.get("method", "").strip()
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

    query = Skill.query.filter_by(status="open", is_active=True)

    if keyword:
        query = query.filter(
            or_(
                Skill.title.contains(keyword),
                Skill.description.contains(keyword)
            )
        )

    if category_id:
        query = query.filter_by(category_id=int(category_id))

    if method:
        query = query.filter_by(method=method)

    skills = query.order_by(Skill.created_at.desc()).all()
    categories = SkillCategory.query.all()

    return render_template(
        "skills.html",
        skills=skills,
        categories=categories,
        keyword=keyword,
        category_id=category_id,
        method=method,
        applied_skill_ids=applied_skill_ids,
    )


@skills_bp.route("/add-skill", methods=["GET", "POST"], endpoint='add_skill')
@login_required
def add_skill():
    # ensure default categories exist
    default_names = [
        '學業課業', '語言學習', '科技與程式', '設計與創作', '藝術與音樂',
        '運動與健康', '生活技能', '社交與溝通', '商業與行銷', '其他'
    ]
    existing = {c.name for c in SkillCategory.query.all()}
    for name in default_names:
        if name not in existing:
            db.session.add(SkillCategory(name=name))
    if not existing:
        db.session.commit()

    categories = SkillCategory.query.all()

    if request.method == "POST":
        attachment = request.files.get("attachment")
        attachment_data = None
        attachment_name = None
        attachment_mime = None
        attachment_type = None

        if attachment and attachment.filename:
            if not allowed_attachment(attachment.filename):
                flash("只支援 jpg、jpeg、png、gif、webp、pdf、txt、doc、docx、ppt、pptx 檔案。", "error")
                return render_template("add_skill.html", categories=categories)

            if file_size(attachment) > current_app.config.get('SKILL_ATTACHMENT_MAX_SIZE', 5 * 1024 * 1024):
                flash("技能附件不能超過 5MB。", "error")
                return render_template("add_skill.html", categories=categories)

            attachment_data = attachment.read()
            attachment_name = attachment.filename
            attachment_mime = attachment.mimetype or 'application/octet-stream'
            attachment_type = detect_attachment_type(attachment_name or attachment_mime)

        # handle multiple category checkboxes
        selected = request.form.getlist('categories')
        if len(selected) > 4:
            flash("分類最多只能選擇 4 個", "error")
            return render_template("add_skill.html", categories=categories)
        
        primary_category = int(selected[0]) if selected else None
        # append chosen category names as a prefix tag in description to preserve multi-select
        category_names = []
        if selected:
            cats = SkillCategory.query.filter(SkillCategory.id.in_([int(x) for x in selected])).all()
            category_names = [c.name for c in cats]

        description_text = request.form.get("description", "").strip()
        if category_names:
            description_text = f"[分類] {', '.join(category_names)}\n" + description_text

        skill = Skill(
            user_id=current_user.id,
            category_id=primary_category,
            title=request.form.get("title", "").strip(),
            description=description_text,
            type=request.form.get("type", "offer"),
            method=request.form.get("method", "online"),
            location=request.form.get("location", "").strip(),
            available_time=request.form.get("available_time", "").strip(),
            status="open",
            is_active=True,
            attachment_data=attachment_data,
            attachment_name=attachment_name,
            attachment_mime=attachment_mime,
            attachment_type=attachment_type,
        )

        if not skill.title or not skill.description:
            flash("技能標題與描述必填。", "error")
        else:
            db.session.add(skill)
            db.session.commit()
            try:
                log = ActivityLog(user_id=current_user.id, action='create_skill', detail=f'skill_id={skill.id}|title={skill.title}', ip_address=request.remote_addr)
                db.session.add(log)
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash("技能已上架。", "success")
            return redirect(url_for(".skills"))

    return render_template("add_skill.html", categories=categories)


@skills_bp.route("/skills/<int:skill_id>/deactivate", methods=["POST"], endpoint='deactivate_skill')
@login_required
def deactivate_skill(skill_id):
    skill = Skill.query.get_or_404(skill_id)

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


@skills_bp.route("/skills/<int:skill_id>/report", methods=["POST"], endpoint='report_skill')
def report_skill(skill_id):
    """API endpoint: 檢舉技能"""

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

    # 檢查是否已有 pending 檢舉
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

    valid_reasons = ['inappropriate_content', 'spam', 'scam', 'copyright', 'other']
    if reason not in valid_reasons:
        return jsonify({
            "success": False,
            "message": "檢舉原因無效。"
        }), 400

    # 處理檢舉附件
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
        
        # 檢查檔案大小（5MB）
        if file_size(evidence) > 5 * 1024 * 1024:
            return jsonify({
                "success": False,
                "message": "檢舉附件不能超過 5MB。"
            }), 400
        
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
