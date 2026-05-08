# app.py: Flask application factory and blueprint registration (exposed as `app` for gunicorn)
import os
from dotenv import load_dotenv
from flask import Flask, url_for as flask_url_for, flash, redirect, request
from flask_login import LoginManager
from sqlalchemy import inspect, text

from config import Config
from models import db, User
from utils import (
    user_average_rating,
    user_completed_matches,
    user_points,
    user_badges,
    unread_notifications_count,
    skill_match_score,
    split_tags,
    detect_attachment_type,
    skill_attachment_url,
    normalize_skill_attachment_url,
    format_taiwan_time,
    render_skill_description,
    user_pending_review_count,
)
from routes import (
    main_bp,
    auth_bp,
    profile_bp,
    skills_bp,
    matches_bp,
    chat_bp,
    reviews_bp,
    notifications_bp,
    admin_bp
)

load_dotenv()

SKILL_LOCATION_TYPE_LABELS = {
    'online': '線上',
    'campus': '校內',
    'off_campus': '校外',
}

SKILL_AVAILABLE_DAY_LABELS = {
    'mon': '星期一',
    'tue': '星期二',
    'wed': '星期三',
    'thu': '星期四',
    'fri': '星期五',
    'sat': '星期六',
    'sun': '星期日',
    'weekend': '週末',
    'flexible': '彈性',
}


def skill_location_type_label(value):
    return SKILL_LOCATION_TYPE_LABELS.get(value, '未設定')


def skill_available_day_label(value):
    return SKILL_AVAILABLE_DAY_LABELS.get(value, '未設定')


def format_skill_time(value):
    return value.strftime('%H:%M') if value else '未設定'

# Endpoint mapping for backward compatibility
ENDPOINT_ALIASES = {
    'index': 'main.index',
    'register': 'auth.register',
    'login': 'auth.login',
    'logout': 'auth.logout',
    'dashboard': 'profile.dashboard',
    'profile': 'profile.profile',
    'skills': 'skills.skills',
    'add_skill': 'skills.add_skill',
    'match_center': 'matches.match_center',
    'chat': 'chat.chat',
    'chat_room': 'chat.chat',
    'chat.chat_room': 'chat.chat',
    'review': 'reviews.review',
    'notifications': 'notifications.notifications',
    'admin': 'admin.dashboard',
}


def url_for_compat(endpoint, **kwargs):
    """
    url_for wrapper for backward compatibility.
    Automatically converts old endpoint names to new blueprint.endpoint format.
    """
    if endpoint in ENDPOINT_ALIASES:
        endpoint = ENDPOINT_ALIASES[endpoint]
    return flask_url_for(endpoint, **kwargs)


def ensure_sqlite_compatibility(app):
    """Ensure older SQLite dev databases are migrated to the current schema."""
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        return

    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())

        def add_column_if_missing(table_name, column_name, column_sql):
            columns = {column['name'] for column in inspector.get_columns(table_name)}
            if column_name not in columns:
                db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_sql}'))
                return True
            return False

        if 'skills' in table_names:
            add_column_if_missing('skills', 'is_active', 'is_active BOOLEAN NOT NULL DEFAULT 1')
            add_column_if_missing('skills', 'tags', 'tags TEXT')
            add_column_if_missing('skills', 'location_type', 'location_type VARCHAR(20)')
            add_column_if_missing('skills', 'location_area', 'location_area VARCHAR(50)')
            add_column_if_missing('skills', 'location_detail', 'location_detail VARCHAR(100)')
            add_column_if_missing('skills', 'available_day', 'available_day VARCHAR(20)')
            add_column_if_missing('skills', 'start_time', 'start_time TIME')
            add_column_if_missing('skills', 'end_time', 'end_time TIME')
            add_column_if_missing('skills', 'attachment_data', 'attachment_data BLOB')
            add_column_if_missing('skills', 'attachment_name', 'attachment_name TEXT')
            add_column_if_missing('skills', 'attachment_mime', 'attachment_mime TEXT')
            add_column_if_missing('skills', 'attachment_type', 'attachment_type TEXT')
            add_column_if_missing('skills', 'attachment_url', 'attachment_url TEXT')
            db.session.execute(text("UPDATE skills SET is_active = 1 WHERE is_active IS NULL"))

        for message_table in ('messages', 'chat_messages'):
            if message_table in table_names:
                add_column_if_missing(message_table, 'file_url', 'file_url VARCHAR(255)')
                add_column_if_missing(message_table, 'file_name', 'file_name VARCHAR(255)')
                add_column_if_missing(message_table, 'file_type', 'file_type VARCHAR(30)')

        if 'users' in table_names:
            user_columns = {column['name'] for column in inspector.get_columns('users')}
            if 'role' not in user_columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"))
            if 'status' not in user_columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))

            db.session.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = '' OR role = 'student'"))
            db.session.execute(text("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''"))

        db.session.commit()

        verification_inspector = inspect(db.engine)
        verification_tables = set(verification_inspector.get_table_names())

        if 'skills' in verification_tables:
            skill_columns = {column['name'] for column in verification_inspector.get_columns('skills')}
            missing_skill_columns = {'is_active', 'tags', 'location_type', 'location_area', 'location_detail', 'available_day', 'start_time', 'end_time', 'attachment_data', 'attachment_name', 'attachment_mime', 'attachment_type', 'attachment_url'} - skill_columns
            if missing_skill_columns:
                raise RuntimeError(f'技能資料表仍缺少欄位: {", ".join(sorted(missing_skill_columns))}')

        for message_table in ('messages', 'chat_messages'):
            if message_table in verification_tables:
                message_columns = {column['name'] for column in verification_inspector.get_columns(message_table)}
                missing_message_columns = {'file_url', 'file_name', 'file_type'} - message_columns
                if missing_message_columns:
                    raise RuntimeError(f'{message_table} 資料表仍缺少欄位: {", ".join(sorted(missing_message_columns))}')

        if 'users' in verification_tables:
            user_columns = {column['name'] for column in verification_inspector.get_columns('users')}
            if 'role' not in user_columns:
                raise RuntimeError('users 資料表仍缺少 role 欄位')
            if 'status' not in user_columns:
                raise RuntimeError('users 資料表仍缺少 status 欄位')


def create_app():
    """Create and configure the Flask application."""
    # Use Flask defaults for template and static folders
    app = Flask(__name__)

    # Load configuration from Config class
    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    app.config['SKILL_ATTACHMENT_MAX_SIZE'] = 5 * 1024 * 1024
    app.config['CHAT_ATTACHMENT_MAX_SIZE'] = 10 * 1024 * 1024

    # Initialize extensions
    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Context processor for template helpers
    @app.context_processor
    def inject_helpers():
        return dict(
            user_average_rating=user_average_rating,
            user_completed_matches=user_completed_matches,
            user_points=user_points,
            user_badges=user_badges,
            unread_notifications_count=unread_notifications_count,
            skill_match_score=skill_match_score,
            split_tags=split_tags,
            detect_attachment_type=detect_attachment_type,
            skill_attachment_url=skill_attachment_url,
            normalize_skill_attachment_url=normalize_skill_attachment_url,
            format_taiwan_time=format_taiwan_time,
            render_skill_description=render_skill_description,
            user_pending_review_count=user_pending_review_count,
            skill_location_type_label=skill_location_type_label,
            skill_available_day_label=skill_available_day_label,
            format_skill_time=format_skill_time,
            url_for=url_for_compat  # Override url_for with compatibility wrapper
        )

    @app.errorhandler(413)
    def request_entity_too_large(error):
        flash("檔案大小超過限制，請上傳 5MB 以下的檔案。", "error")
        return redirect(request.referrer or flask_url_for("skills.add_skill"))

    ensure_sqlite_compatibility(app)

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)

    return app


# Create app instance for gunicorn: gunicorn app:app
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
