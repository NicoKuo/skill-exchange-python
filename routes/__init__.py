# Routes package
from .main import main_bp
from .auth import auth_bp
from .profile import profile_bp
from .skills import skills_bp
from .matches import matches_bp
from .chat import chat_bp
from .reviews import reviews_bp
from .notifications import notifications_bp
from .admin import admin_bp

__all__ = [
    'main_bp',
    'auth_bp',
    'profile_bp',
    'skills_bp',
    'matches_bp',
    'chat_bp',
    'reviews_bp',
    'notifications_bp',
    'admin_bp',
]
