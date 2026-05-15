# routes/__init__.py: 路由套件初始化
# 統一匯出所有藍圖（Blueprint），讓 app.py 可用 from routes import xxx 取用
from .main import main_bp          # 首頁相關路由
from .auth import auth_bp          # 認證路由（登入/註冊/登出）
from .profile import profile_bp    # 個人資料與儀表板路由
from .skills import skills_bp      # 技能管理路由
from .matches import matches_bp    # 媒合中心路由
from .chat import chat_bp          # 聊天室路由
from .reviews import reviews_bp    # 互評系統路由
from .notifications import notifications_bp  # 通知中心路由
from .admin import admin_bp        # 管理後台路由

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
