# routes/skills.py: Blueprint for skill listing and creation routes
import os
from uuid import uuid4

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from models import db, Skill, SkillCategory

skills_bp = Blueprint('skills', __name__)
ALLOWED_ATTACHMENT_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}


def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS


@skills_bp.route('/skill-attachments/<path:filename>', endpoint='skill_attachment')
def skill_attachment(filename):
    attachment_dir = os.path.join(current_app.instance_path, 'skill_attachments')
    return send_from_directory(attachment_dir, filename, as_attachment=True)


@skills_bp.route("/skills", endpoint='skills')
def skills():
    keyword = request.args.get("keyword", "").strip()
    category_id = request.args.get("category_id", "").strip()
    method = request.args.get("method", "").strip()

    query = Skill.query.filter_by(status="open")

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
        method=method
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
        attachment_marker = ""

        if attachment and attachment.filename:
            if not allowed_attachment(attachment.filename):
                flash("只支援 pdf、doc、docx、png、jpg、jpeg 檔案。", "error")
                return render_template("add_skill.html", categories=categories)

            attachment_dir = os.path.join(current_app.instance_path, 'skill_attachments')
            os.makedirs(attachment_dir, exist_ok=True)

            original_name = secure_filename(attachment.filename)
            stored_name = f"{uuid4().hex}_{original_name}"
            attachment.save(os.path.join(attachment_dir, stored_name))
            attachment_marker = f"\n<!--attachment:{stored_name}|{original_name}-->"

        # handle multiple category checkboxes
        selected = request.form.getlist('categories')
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
            description=description_text + attachment_marker,
            type=request.form.get("type", "offer"),
            method=request.form.get("method", "online"),
            location=request.form.get("location", "").strip(),
            available_time=request.form.get("available_time", "").strip(),
            status="open"
        )

        if not skill.title or not skill.description:
            flash("技能標題與描述必填。", "error")
        else:
            db.session.add(skill)
            db.session.commit()
            flash("技能已上架。", "success")
            return redirect(url_for(".skills"))

    return render_template("add_skill.html", categories=categories)
