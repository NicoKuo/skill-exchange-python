# app.py: Flask application factory and blueprint registration (exposed as `app` for gunicorn)
import os
from dotenv import load_dotenv
from flask import Flask, url_for as flask_url_for, flash, redirect, request
from flask_login import LoginManager

from config import Config
from models import db, User
from utils import (
    user_average_rating,
    user_completed_matches,
    user_points,
    user_badges,
    unread_notifications_count,
    skill_match_score,
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
    'admin': 'admin.admin',
}


def url_for_compat(endpoint, **kwargs):
    """
    url_for wrapper for backward compatibility.
    Automatically converts old endpoint names to new blueprint.endpoint format.
    """
    if endpoint in ENDPOINT_ALIASES:
        endpoint = ENDPOINT_ALIASES[endpoint]
    return flask_url_for(endpoint, **kwargs)


def create_app():
    """Create and configure the Flask application."""
    # Use Flask defaults for template and static folders
    app = Flask(__name__)

    # Load configuration from Config class
    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

    # Initialize extensions
    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "login"

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
            format_taiwan_time=format_taiwan_time,
            render_skill_description=render_skill_description,
            user_pending_review_count=user_pending_review_count,
            url_for=url_for_compat  # Override url_for with compatibility wrapper
        )

    @app.errorhandler(413)
    def request_entity_too_large(error):
        flash("檔案大小超過限制，請上傳 5MB 以下的檔案。", "error")
        return redirect(request.referrer or flask_url_for("skills.add_skill"))

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
